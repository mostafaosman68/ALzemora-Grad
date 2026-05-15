"""
ORB feature-matching detector.
Returns ALL medicines detected above threshold (not just the best one),
enabling simultaneous multi-medicine detection.

Rotation invariance: each reference image is stored at 0°, 90°, 180°, and
270°. All four orientations are matched every frame; results are grouped by
base medicine key and only the highest-confidence rotation is returned.
"""

import logging
import os
from dataclasses import dataclass, field

import cv2
import numpy as np

logger = logging.getLogger(__name__)

REFERENCE_DIR = os.path.join(os.path.dirname(__file__), "reference_images")

ORB_FEATURES        = 1500
MIN_GOOD_MATCHES    = 14
LOWE_RATIO          = 0.70
CONFIDENCE_SCALE    = 30
RANSAC_INLIER_RATIO = 0.60
MIN_RANSAC_INLIERS  = 10
CONFIDENCE_THRESHOLD = 0.40

# Suffix appended to internal reference keys for rotated copies.
_ROT_SEP = "__r"
_ROTATIONS = (90, 180, 270)  # degrees; 0° is stored under the plain key


def _rotate_image(img: np.ndarray, angle: int) -> np.ndarray:
    """Rotate *img* by *angle* degrees (must be 90, 180, or 270)."""
    if angle == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(img, cv2.ROTATE_180)
    return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)  # 270


@dataclass
class OrbResult:
    medicine_key: str
    confidence: float
    good_match_count: int
    inlier_ratio: float
    bbox: tuple[int, int, int, int] | None


@dataclass
class DebugScores:
    orb: dict[str, float] = field(default_factory=dict)


class MedicineDetector:
    def __init__(self) -> None:
        self._orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self._references: dict[str, tuple[np.ndarray, list, np.ndarray]] = {}
        self._load_references()

    def detect(self, frame: np.ndarray) -> tuple[list[OrbResult], DebugScores]:
        """
        Returns ALL detections above threshold for this frame (may be multiple).
        Each medicine key appears at most once — the highest-confidence rotation
        variant wins.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        kp_frame, des_frame = self._orb.detectAndCompute(gray, None)

        debug = DebugScores()

        if des_frame is None or len(des_frame) < MIN_GOOD_MATCHES:
            return [], debug

        # Match all stored orientations, then keep the best per base key.
        best: dict[str, OrbResult] = {}

        for ref_key, (ref_img, kp_ref, des_ref) in self._references.items():
            base_key = ref_key.split(_ROT_SEP)[0]
            r = self._match_one(ref_key, kp_frame, des_frame, kp_ref, des_ref, frame.shape, ref_img.shape)
            conf = r.confidence if r else 0.0
            debug.orb[base_key] = max(debug.orb.get(base_key, 0.0), conf)

            if r and (base_key not in best or conf > best[base_key].confidence):
                r.medicine_key = base_key
                best[base_key] = r

        return list(best.values()), debug

    def reference_count(self) -> int:
        return len(self.loaded_keys())

    def loaded_keys(self) -> list[str]:
        """Return unique base medicine keys (rotation variants excluded)."""
        seen: set[str] = set()
        keys: list[str] = []
        for k in self._references:
            base = k.split(_ROT_SEP)[0]
            if base not in seen:
                seen.add(base)
                keys.append(base)
        return keys

    def _load_references(self) -> None:
        if not os.path.isdir(REFERENCE_DIR):
            logger.warning("reference_images/ not found at %s", REFERENCE_DIR)
            return
        loaded = 0
        for fname in os.listdir(REFERENCE_DIR):
            if not fname.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                continue
            key = os.path.splitext(fname)[0].lower()
            img = cv2.imread(os.path.join(REFERENCE_DIR, fname), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue

            # Store the original orientation plus three 90°-step rotations so
            # the detector is robust to any cardinal rotation of the packaging.
            stored = 0
            for angle, src in [(0, img)] + [(a, _rotate_image(img, a)) for a in _ROTATIONS]:
                ref_key = key if angle == 0 else f"{key}{_ROT_SEP}{angle}"
                kp, des = self._orb.detectAndCompute(src, None)
                if des is None or len(kp) < MIN_GOOD_MATCHES:
                    if angle == 0:
                        logger.warning("Too few features in '%s' (%d kp)", fname, len(kp) if kp else 0)
                    continue
                self._references[ref_key] = (src, kp, des)
                stored += 1

            if stored > 0:
                loaded += 1
                logger.info("Loaded '%s' — %d orientation(s)", key, stored)

        logger.info("References loaded: %d medicine(s), %d total variants", loaded, len(self._references))

    def _match_one(
        self,
        key: str,
        kp_frame: list,
        des_frame: np.ndarray,
        kp_ref: list,
        des_ref: np.ndarray,
        frame_shape: tuple[int, ...],
        ref_shape: tuple[int, ...],
    ) -> OrbResult | None:
        try:
            raw = self._matcher.knnMatch(des_ref, des_frame, k=2)
        except cv2.error:
            return None

        good: list[cv2.DMatch] = []
        for pair in raw:
            if len(pair) == 2:
                m, n = pair
                if m.distance < LOWE_RATIO * n.distance:
                    good.append(m)

        if len(good) < MIN_GOOD_MATCHES:
            return None

        src_pts = np.float32([kp_ref[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp_frame[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if H is None or mask is None:
            return None

        inlier_count = int(mask.sum())
        inlier_ratio = inlier_count / max(len(good), 1)

        if inlier_ratio < RANSAC_INLIER_RATIO or inlier_count < MIN_RANSAC_INLIERS:
            return None

        confidence = min(len(good) / CONFIDENCE_SCALE, 1.0) * inlier_ratio

        if confidence < CONFIDENCE_THRESHOLD:
            return None

        bbox = self._compute_bbox(H, ref_shape, frame_shape)
        return OrbResult(
            medicine_key=key,
            confidence=confidence,
            good_match_count=len(good),
            inlier_ratio=inlier_ratio,
            bbox=bbox,
        )

    def _compute_bbox(
        self,
        H: np.ndarray,
        ref_shape: tuple[int, ...],
        frame_shape: tuple[int, ...],
    ) -> tuple[int, int, int, int] | None:
        h_ref, w_ref = ref_shape[:2]
        corners = np.float32([[0, 0], [w_ref, 0], [w_ref, h_ref], [0, h_ref]]).reshape(-1, 1, 2)
        try:
            projected = cv2.perspectiveTransform(corners, H)
        except cv2.error:
            return None
        pts = projected.reshape(4, 2)
        x_min = max(0, int(pts[:, 0].min()))
        y_min = max(0, int(pts[:, 1].min()))
        x_max = min(frame_shape[1], int(pts[:, 0].max()))
        y_max = min(frame_shape[0], int(pts[:, 1].max()))
        w, h = x_max - x_min, y_max - y_min
        if w < 30 or h < 30:
            return None
        return (x_min, y_min, w, h)
