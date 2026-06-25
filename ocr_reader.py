"""
EasyOCR-based text recognition running in a background thread.

How it works:
- Main loop submits frames via submit_frame() (non-blocking, drops old frames).
- Background thread runs OCR and matches extracted text against medicine names.
- Main loop retrieves results via get_result() (non-blocking).
- Medicine list comes from the DB via update_medicines() — no hardcoded list.
"""

import logging
import queue
import threading
from difflib import SequenceMatcher

import cv2
import numpy as np

logger = logging.getLogger(__name__)

OCR_WORD_CONFIDENCE = 0.4
NAME_MATCH_RATIO    = 0.72


class OcrResult:
    __slots__ = ("medicine_key", "confidence", "raw_text")

    def __init__(self, medicine_key: str, confidence: float, raw_text: str) -> None:
        self.medicine_key = medicine_key
        self.confidence   = confidence
        self.raw_text     = raw_text


class OcrReader:
    def __init__(self) -> None:
        self._frame_q:  queue.Queue[np.ndarray]       = queue.Queue(maxsize=1)
        self._result_q: queue.Queue[OcrResult | None]  = queue.Queue(maxsize=1)
        self._ready     = threading.Event()
        # Medicine lookup used for text matching — updated by update_medicines()
        self._medicines: dict[str, dict] = {}
        self._med_lock  = threading.Lock()
        self._thread    = threading.Thread(target=self._run, daemon=True, name="ocr-worker")
        self._thread.start()

    # ── Public API ────────────────────────────────────────────────────────

    def is_ready(self) -> bool:
        return self._ready.is_set()

    def update_medicines(self, med_lookup: dict[str, dict]) -> None:
        """Replace the medicine list used for OCR matching.

        med_lookup is the key→DB-doc dict from fetch_patient_medications().
        Called after DB fetch so OCR matches against actual patient medicines.
        """
        with self._med_lock:
            self._medicines = dict(med_lookup)
        logger.info("OCR medicine list updated: %d entries", len(med_lookup))

    def submit_frame(self, frame: np.ndarray) -> None:
        try:
            self._frame_q.get_nowait()
        except queue.Empty:
            pass
        self._frame_q.put(frame.copy())

    def get_result(self) -> OcrResult | None:
        try:
            return self._result_q.get_nowait()
        except queue.Empty:
            return None

    # ── Background thread ─────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            import ssl
            ssl._create_default_https_context = ssl._create_unverified_context
            import easyocr  # type: ignore[import-untyped]
            reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            logger.info("EasyOCR ready")
        except Exception as exc:
            logger.error("EasyOCR failed to load: %s — OCR disabled.", exc)
            self._ready.set()
            return

        self._ready.set()

        while True:
            try:
                frame = self._frame_q.get(timeout=1.0)
            except queue.Empty:
                continue

            with self._med_lock:
                medicines = dict(self._medicines)

            result = self._process(frame, reader, medicines)

            try:
                self._result_q.get_nowait()
            except queue.Empty:
                pass
            self._result_q.put(result)

    def _process(
        self,
        frame: np.ndarray,
        reader: object,
        medicines: dict[str, dict],
    ) -> OcrResult | None:
        h, w = frame.shape[:2]
        scale = min(1.0, 800 / max(w, h))
        if scale < 1.0:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

        try:
            detections: list[tuple[list, str, float]] = reader.readtext(  # type: ignore[union-attr]
                frame, detail=1, paragraph=False, rotation_info=[90, 180, 270]
            )
        except Exception as exc:
            logger.error("OCR inference error: %s", exc)
            return None

        words = [
            text.lower()
            for (_, text, conf) in detections
            if conf >= OCR_WORD_CONFIDENCE and len(text.strip()) >= 3
        ]
        if not words:
            return None

        full_text = " ".join(words)
        logger.info("OCR raw text: %s", full_text)

        result = _match_text(full_text, medicines)
        if result:
            logger.info("OCR matched: %s (conf=%.2f)", result.medicine_key, result.confidence)
        else:
            logger.info("OCR: no medicine match in detected text")
        return result


# ── Text → medicine matching ──────────────────────────────────────────────

def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _best_window_similarity(haystack: str, needle: str) -> float:
    n    = len(needle)
    best = 0.0
    for i in range(max(1, len(haystack) - n + 1)):
        ratio = _similarity(haystack[i: i + n], needle)
        if ratio > best:
            best = ratio
    return best


def _match_text(text: str, medicines: dict[str, dict]) -> OcrResult | None:
    if not medicines:
        return None

    best_key:   str | None = None
    best_score: float      = 0.0

    for key, doc in medicines.items():
        # Check the brand name, generic name (if present), and the key itself
        candidates = [
            doc.get("name") or "",
            doc.get("generic_name") or "",
            key.replace("_", " "),
        ]
        for term in candidates:
            term_lower = term.lower().strip()
            if not term_lower:
                continue
            score = 0.95 if term_lower in text else _best_window_similarity(text, term_lower)
            if score > best_score:
                best_score = score
                best_key   = key

    if best_key and best_score >= NAME_MATCH_RATIO:
        return OcrResult(medicine_key=best_key, confidence=best_score, raw_text=text)
    return None
