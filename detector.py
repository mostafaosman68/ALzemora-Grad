"""
ORB feature-matching detector.
References are loaded from DB medication documents via load_from_medications().

Optimisations:
- Descriptor cache: ORB keypoints/descriptors are serialised to disk on first
  load and read back on every subsequent run — startup goes from seconds to
  milliseconds when images haven't changed.
- Aspect-ratio-preserving resize: portrait reference photos are no longer
  squished into a landscape 320x240 box.
- Two reference scales (256 px and 400 px longest dim) for near/far robustness.
- Shared _preprocess() helper applied identically to references and live frames.
"""

import hashlib
import logging
import os
import pickle
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".descriptor_cache")

ORB_FEATURES           = 2000
ORB_DISTANCE_THRESHOLD = 50
MIN_GOOD_MATCHES       = 6
CONFIDENCE_SCALE       = 8
RANSAC_INLIER_RATIO    = 0.40
MIN_RANSAC_INLIERS     = 5
CONFIDENCE_THRESHOLD   = 0.25
MIN_SPATIAL_SPREAD     = 0.20

_SCALE_DIMS = (256, 400)   # longest dimension in px per scale
_ROT_SEP    = "__r"
_ROTATIONS  = (90, 180, 270)


# ── Image helpers ─────────────────────────────────────────────────────────

def _resize_keep_aspect(img: np.ndarray, max_dim: int) -> np.ndarray:
    h, w = img.shape[:2]
    scale = max_dim / max(h, w)
    if scale >= 1.0:
        return img
    return cv2.resize(
        img,
        (max(1, int(w * scale)), max(1, int(h * scale))),
        interpolation=cv2.INTER_AREA,
    )


def _preprocess(gray: np.ndarray, clahe: cv2.CLAHE) -> np.ndarray:
    """Identical pipeline applied to both reference images and live frames."""
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    gray = clahe.apply(gray)
    blurred = cv2.GaussianBlur(gray, (0, 0), 2.0)
    return cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)


def _rotate_image(img: np.ndarray, angle: int) -> np.ndarray:
    if angle == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(img, cv2.ROTATE_180)
    return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)


# ── Descriptor cache helpers ──────────────────────────────────────────────

def _cache_key(path: str) -> str:
    mtime = os.path.getmtime(path)
    return hashlib.md5(f"{path}:{mtime}".encode()).hexdigest()


def _kp_to_tuple(kp: cv2.KeyPoint) -> tuple:
    return (kp.pt[0], kp.pt[1], kp.size, kp.angle, kp.response, kp.octave, kp.class_id)


def _tuple_to_kp(t: tuple) -> cv2.KeyPoint:
    return cv2.KeyPoint(
        x=t[0], y=t[1], size=t[2], angle=t[3],
        response=t[4], octave=int(t[5]), class_id=int(t[6]),
    )


def _load_cache(cache_path: str) -> dict | None:
    try:
        with open(cache_path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _save_cache(cache_path: str, data: dict) -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        logger.warning("Could not write descriptor cache: %s", e)


# ── Data classes ──────────────────────────────────────────────────────────

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


# ── Detector ──────────────────────────────────────────────────────────────

class MedicineDetector:
    def __init__(self) -> None:
        self._orb     = cv2.ORB_create(nfeatures=ORB_FEATURES, scaleFactor=1.2, nlevels=8)
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        self._clahe   = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self._references: dict[str, tuple[np.ndarray, list, np.ndarray]] = {}

    # ── Public API ────────────────────────────────────────────────────────

    def load_from_medications(self, medications: list[dict]) -> None:
        """Build ORB reference bank from DB medication documents.

        Descriptors are cached to .descriptor_cache/ so subsequent runs
        skip all image processing and load in milliseconds.
        """
        self._references.clear()
        loaded = 0

        for med in medications:
            name = (med.get("name") or "").strip()
            if not name:
                continue
            key = re.sub(r'[^a-z0-9]', '_', name.lower()).strip('_')

            paths = [p for p in (med.get("photo_urls") or []) if p and os.path.exists(p)]
            if not paths:
                single = med.get("photo_url")
                if single and os.path.exists(single):
                    paths = [single]

            if not paths:
                logger.warning("No image on disk for '%s'", name)
                continue

            stored = 0
            for img_idx, path in enumerate(paths):
                img_suffix  = f"__i{img_idx}" if img_idx > 0 else ""
                cache_path  = os.path.join(CACHE_DIR, f"{_cache_key(path)}.pkl")
                cached      = _load_cache(cache_path)

                if cached is not None:
                    # Fast path: load pre-computed descriptors from disk
                    for ref_key, (img, kp_tuples, des) in cached.items():
                        full_key = f"{key}{img_suffix}__{ref_key}"
                        kp = [_tuple_to_kp(t) for t in kp_tuples]
                        self._references[full_key] = (img, kp, des)
                        stored += 1
                    logger.info("Cache hit for '%s' img#%d — %d variant(s)", name, img_idx, stored)
                    loaded += 1
                    continue

                # Slow path: compute ORB descriptors, then save to cache
                img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                if img is None:
                    logger.warning("Could not read image: %s", path)
                    continue

                h_raw, w_raw = img.shape[:2]
                logger.info("Computing descriptors for '%s' img#%d — %dx%d", name, img_idx, w_raw, h_raw)

                cache_data: dict[str, tuple] = {}

                for max_dim in _SCALE_DIMS:
                    scaled     = _resize_keep_aspect(img, max_dim)
                    scaled     = _preprocess(scaled, self._clahe)
                    dim_suffix = f"d{max_dim}"

                    for angle, src in [(0, scaled)] + [(a, _rotate_image(scaled, a)) for a in _ROTATIONS]:
                        rot_suffix = f"r{angle}" if angle != 0 else "r0"
                        variant_key = f"{dim_suffix}_{rot_suffix}"
                        kp, des = self._orb.detectAndCompute(src, None)
                        if des is None or len(kp) < MIN_GOOD_MATCHES:
                            continue
                        cache_data[variant_key] = (src, [_kp_to_tuple(k) for k in kp], des)
                        full_key = f"{key}{img_suffix}__{variant_key}"
                        self._references[full_key] = (src, kp, des)
                        stored += 1

                if stored > 0:
                    _save_cache(cache_path, cache_data)
                    loaded += 1
                    logger.info("Computed and cached '%s' — %d variant(s)", name, stored)
                else:
                    logger.warning("No usable features found for '%s'", name)

        logger.info("DB references: %d medicine(s), %d total variants", loaded, len(self._references))

    def detect(self, frame: np.ndarray) -> tuple[list[OrbResult], DebugScores]:
        """Return all medicines detected above threshold in this frame."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = _preprocess(gray, self._clahe)
        kp_frame, des_frame = self._orb.detectAndCompute(gray, None)

        debug = DebugScores()
        if des_frame is None or len(des_frame) < MIN_GOOD_MATCHES:
            return [], debug

        best: dict[str, OrbResult] = {}
        for ref_key, (ref_img, kp_ref, des_ref) in self._references.items():
            base_key = ref_key.split('__')[0]
            r = self._match_one(ref_key, kp_frame, des_frame, kp_ref, des_ref,
                                frame.shape, ref_img.shape)
            conf = r.confidence if r else 0.0
            debug.orb[base_key] = max(debug.orb.get(base_key, 0.0), conf)
            if r and (base_key not in best or conf > best[base_key].confidence):
                r.medicine_key = base_key
                best[base_key] = r

        return list(best.values()), debug

    def reference_count(self) -> int:
        return len(self.loaded_keys())

    def loaded_keys(self) -> list[str]:
        seen: set[str] = set()
        keys: list[str] = []
        for k in self._references:
            base = k.split('__')[0]
            if base not in seen:
                seen.add(base)
                keys.append(base)
        return keys

    # ── Internal matching ─────────────────────────────────────────────────

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
            matches = self._matcher.match(des_ref, des_frame)
        except cv2.error:
            return None

        good = [m for m in matches if m.distance < ORB_DISTANCE_THRESHOLD]
        if len(good) < MIN_GOOD_MATCHES:
            return None

        src_pts = np.float32([kp_ref[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp_frame[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 4.0)
        if H is None or mask is None:
            return None

        inlier_mask  = mask.ravel().astype(bool)
        inlier_count = int(inlier_mask.sum())
        inlier_ratio = inlier_count / max(len(good), 1)

        if inlier_ratio < RANSAC_INLIER_RATIO or inlier_count < MIN_RANSAC_INLIERS:
            return None

        inlier_src = src_pts[inlier_mask].reshape(-1, 2)
        h_ref, w_ref = ref_shape[:2]
        x_spread = (inlier_src[:, 0].max() - inlier_src[:, 0].min()) / max(w_ref, 1)
        y_spread = (inlier_src[:, 1].max() - inlier_src[:, 1].min()) / max(h_ref, 1)
        if x_spread < MIN_SPATIAL_SPREAD or y_spread < MIN_SPATIAL_SPREAD:
            return None

        inlier_distances = [good[i].distance for i in range(len(good)) if inlier_mask[i]]
        mean_dist  = float(np.mean(inlier_distances))
        quality    = max(0.0, 1.0 - mean_dist / ORB_DISTANCE_THRESHOLD)
        confidence = quality * min(inlier_count / CONFIDENCE_SCALE, 1.0)

        if confidence < CONFIDENCE_THRESHOLD:
            return None

        if not self._validate_homography(H, ref_shape, frame_shape):
            return None

        bbox = self._compute_bbox(H, ref_shape, frame_shape)
        logger.info(
            "ORB match: %s  conf=%.3f  inliers=%d  dist=%.1f  spread=(%.2f,%.2f)",
            key.split("__")[0], confidence, inlier_count, mean_dist, x_spread, y_spread,
        )
        return OrbResult(
            medicine_key=key,
            confidence=confidence,
            good_match_count=len(good),
            inlier_ratio=inlier_ratio,
            bbox=bbox,
        )

    def _validate_homography(
        self,
        H: np.ndarray,
        ref_shape: tuple[int, ...],
        frame_shape: tuple[int, ...],
    ) -> bool:
        h_ref, w_ref     = ref_shape[:2]
        h_frame, w_frame = frame_shape[:2]
        corners = np.float32([[0, 0], [w_ref, 0], [w_ref, h_ref], [0, h_ref]]).reshape(-1, 1, 2)
        try:
            projected = cv2.perspectiveTransform(corners, H).reshape(4, 2)
        except cv2.error:
            return False

        if (
            projected[:, 0].min() < -w_frame * 0.5
            or projected[:, 0].max() > w_frame * 1.5
            or projected[:, 1].min() < -h_frame * 0.5
            or projected[:, 1].max() > h_frame * 1.5
        ):
            return False

        hull = cv2.convexHull(projected.astype(np.float32))
        if len(hull) < 4:
            return False

        area = cv2.contourArea(hull)
        if area < h_frame * w_frame * 0.01:
            return False

        if np.linalg.det(H[:2, :2]) <= 0:
            return False

        return True

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
        pts   = projected.reshape(4, 2)
        x_min = max(0, int(pts[:, 0].min()))
        y_min = max(0, int(pts[:, 1].min()))
        x_max = min(frame_shape[1], int(pts[:, 0].max()))
        y_max = min(frame_shape[0], int(pts[:, 1].max()))
        w, h  = x_max - x_min, y_max - y_min
        if w < 15 or h < 15:
            return None
        return (x_min, y_min, w, h)
