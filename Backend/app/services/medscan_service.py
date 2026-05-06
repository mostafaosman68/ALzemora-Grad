from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXTERNAL_REFERENCE_DIR = PROJECT_ROOT.parent / "mediscan" / "mediscan" / "mediscan" / "reference_images"
LOCAL_REFERENCE_DIR = PROJECT_ROOT / "data" / "medscan_reference_images"

ORB_FEATURES = 1500
MIN_GOOD_MATCHES = 14
LOWE_RATIO = 0.70
CONFIDENCE_SCALE = 30
RANSAC_INLIER_RATIO = 0.60
MIN_RANSAC_INLIERS = 10
CONFIDENCE_THRESHOLD = 0.40
OCR_WORD_CONFIDENCE = 0.40
NAME_MATCH_RATIO = 0.72

MEDICINES: dict[str, dict[str, str]] = {
    "paracetamol": {
        "name": "Paracetamol",
        "generic_name": "Acetaminophen",
        "category": "Analgesic / Antipyretic",
        "dosage_form": "Tablet",
        "strength": "500 mg",
        "manufacturer": "Generic",
        "description": "Used to treat pain and reduce fever.",
        "warnings": "Do not exceed 4g/day. Avoid alcohol.",
    },
    "amoxicillin": {
        "name": "Amoxicillin",
        "generic_name": "Amoxicillin",
        "category": "Antibiotic",
        "dosage_form": "Capsule",
        "strength": "500 mg",
        "manufacturer": "Generic",
        "description": "Broad-spectrum penicillin antibiotic.",
        "warnings": "Check for penicillin allergy before use.",
    },
    "ibuprofen": {
        "name": "Ibuprofen",
        "generic_name": "Ibuprofen",
        "category": "NSAID / Anti-inflammatory",
        "dosage_form": "Tablet",
        "strength": "400 mg",
        "manufacturer": "Generic",
        "description": "Reduces inflammation, pain, and fever.",
        "warnings": "Take with food. Avoid if history of ulcers.",
    },
    "metformin": {
        "name": "Metformin",
        "generic_name": "Metformin HCl",
        "category": "Antidiabetic",
        "dosage_form": "Tablet",
        "strength": "850 mg",
        "manufacturer": "Generic",
        "description": "First-line treatment for type 2 diabetes.",
        "warnings": "Monitor renal function. Avoid with contrast dye.",
    },
    "omeprazole": {
        "name": "Omeprazole",
        "generic_name": "Omeprazole",
        "category": "Proton Pump Inhibitor",
        "dosage_form": "Capsule",
        "strength": "20 mg",
        "manufacturer": "Generic",
        "description": "Reduces stomach acid. Used for GERD and ulcers.",
        "warnings": "Long-term use may reduce magnesium levels.",
    },
    "atorvastatin": {
        "name": "Atorvastatin",
        "generic_name": "Atorvastatin Calcium",
        "category": "Statin / Lipid-lowering",
        "dosage_form": "Tablet",
        "strength": "20 mg",
        "manufacturer": "Generic",
        "description": "Lowers LDL cholesterol and triglycerides.",
        "warnings": "Report muscle pain immediately. Avoid grapefruit.",
    },
    "amlodipine": {
        "name": "Amlodipine",
        "generic_name": "Amlodipine Besylate",
        "category": "Calcium Channel Blocker",
        "dosage_form": "Tablet",
        "strength": "5 mg",
        "manufacturer": "Generic",
        "description": "Treats hypertension and angina.",
        "warnings": "May cause ankle swelling and facial flushing.",
    },
    "azithromycin": {
        "name": "Azithromycin",
        "generic_name": "Azithromycin",
        "category": "Antibiotic (Macrolide)",
        "dosage_form": "Tablet",
        "strength": "500 mg",
        "manufacturer": "Generic",
        "description": "Treats respiratory, skin, and ear infections.",
        "warnings": "Risk of cardiac arrhythmia in susceptible patients.",
    },
    "lisinopril": {
        "name": "Lisinopril",
        "generic_name": "Lisinopril",
        "category": "ACE Inhibitor",
        "dosage_form": "Tablet",
        "strength": "10 mg",
        "manufacturer": "Generic",
        "description": "Treats hypertension and heart failure.",
        "warnings": "Avoid in pregnancy. Monitor potassium levels.",
    },
    "cetirizine": {
        "name": "Cetirizine",
        "generic_name": "Cetirizine HCl",
        "category": "Antihistamine",
        "dosage_form": "Tablet",
        "strength": "10 mg",
        "manufacturer": "Generic",
        "description": "Relieves allergy symptoms and urticaria.",
        "warnings": "May cause drowsiness. Avoid driving if affected.",
    },
    "cataflam": {
        "name": "Cataflam",
        "generic_name": "Diclofenac Potassium",
        "category": "NSAID / Anti-inflammatory",
        "dosage_form": "Tablet",
        "strength": "50 mg",
        "manufacturer": "Novartis",
        "description": "Relieves pain and inflammation. Used for arthritis, dysmenorrhea, and acute injuries.",
        "warnings": "Avoid in peptic ulcer disease. Monitor renal function with long-term use.",
    },
    "levoxin": {
        "name": "Levoxin",
        "generic_name": "Levofloxacin",
        "category": "Antibiotic (Fluoroquinolone)",
        "dosage_form": "Tablet",
        "strength": "500 mg",
        "manufacturer": "Generic",
        "description": "Broad-spectrum antibiotic for respiratory, urinary tract, and skin infections.",
        "warnings": "Risk of tendon rupture. Avoid in children and pregnant women.",
    },
    "mebo": {
        "name": "MEBO",
        "generic_name": "Moist Exposed Burn Ointment",
        "category": "Dermatological / Wound Care",
        "dosage_form": "Ointment",
        "strength": "Topical",
        "manufacturer": "Shantou MEBO Pharmaceutical",
        "description": "Treats burns, wounds, and skin ulcers. Promotes moist wound healing.",
        "warnings": "For external use only. Do not apply to deep puncture wounds without medical advice.",
    },
    "coxritor": {
        "name": "Coxritor",
        "generic_name": "Moist Exposed Burn Ointment",
        "category": "Dermatological / Wound Care",
        "dosage_form": "Ointment",
        "strength": "Topical",
        "manufacturer": "Shantou MEBO Pharmaceutical",
        "description": "Treats burns, wounds, and skin ulcers. Promotes moist wound healing.",
        "warnings": "For external use only. Do not apply to deep puncture wounds without medical advice.",
    },
    "brufen": {
        "name": "Brufen",
        "generic_name": "Ibuprofen",
        "category": "NSAID / Anti-inflammatory",
        "dosage_form": "Tablet",
        "strength": "200 mg",
        "manufacturer": "Generic",
        "description": "Relieves pain and reduces inflammation.",
        "warnings": "Avoid in peptic ulcer disease. Monitor renal function with long-term use.",
    },
}


@dataclass
class ReferenceVariant:
    key: str
    base_key: str
    image: np.ndarray
    keypoints: list
    descriptors: np.ndarray


class MedScanAnalyzer:
    def __init__(
        self,
        reference_dir: Optional[Path] = None,
        reference_images: Optional[list[tuple[str, str | Path]]] = None,
    ) -> None:
        self._orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self._references: list[ReferenceVariant] = []
        self._ocr_reader = None
        self._ocr_ready = False
        self._reference_dir = reference_dir
        self._reference_images = reference_images
        self._load_references()

    def catalog(self) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for key, medicine in MEDICINES.items():
            items.append({"key": key, **medicine})
        return items

    def analyze(self, image_path: str) -> dict:
        frame = cv2.imread(image_path)
        if frame is None:
            return {"status": "error", "error": "Uploaded image is not valid"}

        detections, debug_scores = self._detect(frame)
        ocr_text = self._extract_ocr_text(frame)
        ocr_text_normalized = (ocr_text or "").lower()

        enriched: list[dict[str, object]] = []
        for detection in detections:
            medicine = MEDICINES.get(detection["medicine_key"], {})
            ocr_matched = False
            if ocr_text_normalized and medicine:
                ocr_matched = any(
                    term.lower() in ocr_text_normalized
                    for term in (medicine.get("name", ""), medicine.get("generic_name", ""), detection["medicine_key"])
                    if term
                )

            enriched.append({
                **detection,
                **medicine,
                "ocr_matched": ocr_matched,
            })

        enriched.sort(key=lambda item: float(item.get("confidence", 0.0)), reverse=True)

        primary = enriched[0] if enriched else None
        summary_text = None
        if primary:
            summary_text = f"{primary['name']} detected with {float(primary['confidence']) * 100:.0f}% confidence"
            if primary.get("warnings"):
                summary_text = f"{summary_text}. Warning: {primary['warnings']}"

        return {
            "status": "detected" if enriched else "no_match",
            "ocr_text": ocr_text,
            "ocr_ready": self._ocr_ready,
            "debug_scores": debug_scores,
            "detections": enriched,
            "primary_detection": primary,
            "summary_text": summary_text,
        }

    def _load_references(self) -> None:
        if self._reference_images:
            loaded = 0
            for base_key, image_path in self._reference_images:
                image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
                if image is None:
                    continue

                for angle, variant in [(0, image), (90, self._rotate_image(image, 90)), (180, self._rotate_image(image, 180)), (270, self._rotate_image(image, 270))]:
                    variant_key = base_key if angle == 0 else f"{base_key}__r{angle}"
                    keypoints, descriptors = self._orb.detectAndCompute(variant, None)
                    if descriptors is None or len(keypoints) < MIN_GOOD_MATCHES:
                        continue

                    self._references.append(
                        ReferenceVariant(
                            key=variant_key,
                            base_key=base_key,
                            image=variant,
                            keypoints=keypoints,
                            descriptors=descriptors,
                        )
                    )

                loaded += 1

            logger.info("MedScan loaded %d database reference image(s) (%d variants)", loaded, len(self._references))
            if loaded == 0:
                logger.warning("MedScan received database references but none were usable")
            return

        reference_dir = self._resolve_reference_dir()
        if reference_dir is None:
            logger.warning("MedScan reference_images folder not found")
            return

        loaded = 0
        for entry in sorted(reference_dir.rglob("*")):
            if entry.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp"}:
                continue

            relative_parts = entry.relative_to(reference_dir).parts
            key = relative_parts[0].lower() if len(relative_parts) > 1 else entry.stem.lower()
            image = cv2.imread(str(entry), cv2.IMREAD_GRAYSCALE)
            if image is None:
                continue

            for angle, variant in [(0, image), (90, self._rotate_image(image, 90)), (180, self._rotate_image(image, 180)), (270, self._rotate_image(image, 270))]:
                variant_key = key if angle == 0 else f"{key}__r{angle}"
                keypoints, descriptors = self._orb.detectAndCompute(variant, None)
                if descriptors is None or len(keypoints) < MIN_GOOD_MATCHES:
                    continue

                self._references.append(
                    ReferenceVariant(
                        key=variant_key,
                        base_key=key,
                        image=variant,
                        keypoints=keypoints,
                        descriptors=descriptors,
                    )
                )

            loaded += 1

        logger.info("MedScan loaded %d reference medicines (%d variants)", loaded, len(self._references))
        if loaded == 0:
            logger.warning("MedScan found no usable reference images under %s", reference_dir)

    def _resolve_reference_dir(self) -> Optional[Path]:
        if self._reference_dir is not None:
            return self._reference_dir if self._reference_dir.exists() and self._reference_dir.is_dir() else None

        candidates = [
            Path(os.environ.get("MEDISCAN_REFERENCE_DIR", "")),
            EXTERNAL_REFERENCE_DIR,
            LOCAL_REFERENCE_DIR,
        ]
        for candidate in candidates:
            if candidate and candidate.exists() and candidate.is_dir():
                return candidate
        return None

    def _detect(self, frame: np.ndarray) -> tuple[list[dict[str, object]], dict[str, float]]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frame_keypoints, frame_descriptors = self._orb.detectAndCompute(gray, None)
        if frame_descriptors is None or len(frame_keypoints) < MIN_GOOD_MATCHES:
            return [], {}

        best_by_key: dict[str, dict[str, object]] = {}
        debug_scores: dict[str, float] = {}

        for reference in self._references:
            result = self._match_one(reference, frame_keypoints, frame_descriptors, frame.shape)
            if result is None:
                continue

            debug_scores[result["medicine_key"]] = max(debug_scores.get(result["medicine_key"], 0.0), float(result["confidence"]))
            current = best_by_key.get(result["medicine_key"])
            if current is None or float(result["confidence"]) > float(current["confidence"]):
                best_by_key[result["medicine_key"]] = result

        return list(best_by_key.values()), debug_scores

    def _match_one(
        self,
        reference: ReferenceVariant,
        frame_keypoints: list,
        frame_descriptors: np.ndarray,
        frame_shape: tuple[int, ...],
    ) -> Optional[dict[str, object]]:
        try:
            raw_matches = self._matcher.knnMatch(reference.descriptors, frame_descriptors, k=2)
        except cv2.error:
            return None

        good: list[cv2.DMatch] = []
        for pair in raw_matches:
            if len(pair) == 2:
                first, second = pair
                if first.distance < LOWE_RATIO * second.distance:
                    good.append(first)

        if len(good) < MIN_GOOD_MATCHES:
            return None

        src_pts = np.float32([reference.keypoints[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([frame_keypoints[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

        homography, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if homography is None or mask is None:
            return None

        inlier_count = int(mask.sum())
        inlier_ratio = inlier_count / max(len(good), 1)
        if inlier_ratio < RANSAC_INLIER_RATIO or inlier_count < MIN_RANSAC_INLIERS:
            return None

        confidence = min(len(good) / CONFIDENCE_SCALE, 1.0) * inlier_ratio
        if confidence < CONFIDENCE_THRESHOLD:
            return None

        bbox = self._compute_bbox(homography, reference.image.shape, frame_shape)
        return {
            "medicine_key": reference.base_key,
            "confidence": round(float(confidence), 4),
            "good_match_count": len(good),
            "inlier_ratio": round(float(inlier_ratio), 4),
            "bbox": list(bbox) if bbox is not None else None,
        }

    def _compute_bbox(
        self,
        homography: np.ndarray,
        ref_shape: tuple[int, ...],
        frame_shape: tuple[int, ...],
    ) -> Optional[tuple[int, int, int, int]]:
        h_ref, w_ref = ref_shape[:2]
        corners = np.float32([[0, 0], [w_ref, 0], [w_ref, h_ref], [0, h_ref]]).reshape(-1, 1, 2)
        try:
            projected = cv2.perspectiveTransform(corners, homography)
        except cv2.error:
            return None

        points = projected.reshape(4, 2)
        x_min = max(0, int(points[:, 0].min()))
        y_min = max(0, int(points[:, 1].min()))
        x_max = min(frame_shape[1], int(points[:, 0].max()))
        y_max = min(frame_shape[0], int(points[:, 1].max()))
        width = x_max - x_min
        height = y_max - y_min
        if width < 30 or height < 30:
            return None
        return (x_min, y_min, width, height)

    def _extract_ocr_text(self, frame: np.ndarray) -> Optional[str]:
        try:
            reader = self._get_ocr_reader()
            if reader is None:
                return None

            height, width = frame.shape[:2]
            scale = min(1.0, 800 / max(width, height))
            if scale < 1.0:
                frame = cv2.resize(frame, (int(width * scale), int(height * scale)))

            detections = reader.readtext(frame, detail=1, paragraph=False, rotation_info=[90, 180, 270])
            words = [
                text.lower()
                for (_, text, confidence) in detections
                if confidence >= OCR_WORD_CONFIDENCE and len(text.strip()) >= 3
            ]
            if not words:
                return None
            return " ".join(words)
        except Exception as exc:
            logger.info("OCR disabled or failed: %s", exc)
            return None

    def _get_ocr_reader(self):
        if self._ocr_ready:
            return self._ocr_reader

        try:
            import easyocr  # type: ignore[import-untyped]

            self._ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            self._ocr_ready = True
        except Exception as exc:
            logger.info("EasyOCR unavailable: %s", exc)
            self._ocr_reader = None
            self._ocr_ready = True

        return self._ocr_reader

    @staticmethod
    def _rotate_image(image: np.ndarray, angle: int) -> np.ndarray:
        if angle == 90:
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        if angle == 180:
            return cv2.rotate(image, cv2.ROTATE_180)
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)


_analyzers: dict[str, MedScanAnalyzer] = {}


def get_medscan_analyzer(
    reference_dir: Optional[str | Path] = None,
    reference_images: Optional[list[tuple[str, str | Path]]] = None,
) -> MedScanAnalyzer:
    if reference_images:
        cache_key = "images:" + "|".join(f"{key}:{Path(path).resolve()}" for key, path in reference_images)
        if cache_key not in _analyzers:
            _analyzers[cache_key] = MedScanAnalyzer(reference_images=reference_images)
        return _analyzers[cache_key]

    if reference_dir is None:
        cache_key = "default"
        if cache_key not in _analyzers:
            _analyzers[cache_key] = MedScanAnalyzer()
        return _analyzers[cache_key]

    reference_path = Path(reference_dir)
    cache_key = str(reference_path.resolve())
    if cache_key not in _analyzers:
        _analyzers[cache_key] = MedScanAnalyzer(reference_path)
    return _analyzers[cache_key]


def analyze_medscan_image(
    image_path: str,
    reference_dir: Optional[str | Path] = None,
    reference_images: Optional[list[tuple[str, str | Path]]] = None,
) -> dict:
    return get_medscan_analyzer(reference_dir, reference_images=reference_images).analyze(image_path)


def get_medicine_catalog() -> list[dict[str, str]]:
    return get_medscan_analyzer().catalog()