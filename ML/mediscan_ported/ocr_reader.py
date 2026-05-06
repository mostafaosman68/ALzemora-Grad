"""
EasyOCR-based text recognition running in a background thread.

How it works:
- Main loop submits frames via submit_frame() (non-blocking, drops old frames).
- Background thread runs OCR and matches extracted text against medicine names.
- Main loop retrieves results via get_result() (non-blocking).

First run downloads ~400MB EasyOCR models — subsequent runs use cache.
"""

import logging
import queue
import threading
from difflib import SequenceMatcher

import cv2
import numpy as np

from ML.mediscan_ported.medicines import MEDICINES, Medicine

logger = logging.getLogger(__name__)

# Minimum OCR text confidence from EasyOCR per word
OCR_WORD_CONFIDENCE = 0.4
# Minimum similarity ratio to accept a medicine name match
NAME_MATCH_RATIO = 0.72


class OcrResult:
    __slots__ = ("medicine_key", "confidence", "raw_text")

    def __init__(self, medicine_key: str, confidence: float, raw_text: str) -> None:
        self.medicine_key = medicine_key
        self.confidence = confidence
        self.raw_text = raw_text


class OcrReader:
    def __init__(self) -> None:
        self._frame_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=1)
        self._result_q: queue.Queue[OcrResult | None] = queue.Queue(maxsize=1)
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="ocr-worker"
        )
        self._thread.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_ready(self) -> bool:
        """True once EasyOCR models have finished loading."""
        return self._ready.is_set()

    def submit_frame(self, frame: np.ndarray) -> None:
        """Queue a frame for OCR. Drops the previous queued frame if not yet processed."""
        try:
            self._frame_q.get_nowait()
        except queue.Empty:
            pass
        self._frame_q.put(frame.copy())

    def get_result(self) -> OcrResult | None:
        """Non-blocking. Returns the latest OCR result, or None if none ready."""
        try:
            return self._result_q.get_nowait()
        except queue.Empty:
            return None

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def _run(self) -> None:
        try:
            import ssl
            ssl._create_default_https_context = ssl._create_unverified_context
            import easyocr  # type: ignore[import-untyped]
            reader = easyocr.Reader(["en"], gpu=True, verbose=False)
            logger.info("EasyOCR ready")
        except Exception as exc:
            logger.error("EasyOCR failed to load: %s — OCR will be disabled.", exc)
            self._ready.set()
            return

        self._ready.set()

        while True:
            try:
                frame = self._frame_q.get(timeout=1.0)
            except queue.Empty:
                continue

            result = self._process(frame, reader)

            # Replace stale result
            try:
                self._result_q.get_nowait()
            except queue.Empty:
                pass
            self._result_q.put(result)

    def _process(self, frame: np.ndarray, reader: object) -> OcrResult | None:
        # Resize to speed up OCR (still readable for medicine boxes)
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

        # Collect high-confidence words into a single string
        words = [
            text.lower()
            for (_, text, conf) in detections
            if conf >= OCR_WORD_CONFIDENCE and len(text.strip()) >= 3
        ]
        if not words:
            return None

        full_text = " ".join(words)
        logger.debug("OCR text: %s", full_text)

        return _match_text_to_medicine(full_text)


# ------------------------------------------------------------------
# Text → medicine matching
# ------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _match_text_to_medicine(text: str) -> OcrResult | None:
    best_key: str | None = None
    best_score = 0.0

    for key, med in MEDICINES.items():
        candidates = [
            med["name"],
            med["generic_name"],
            key,
        ]
        for term in candidates:
            term_lower = term.lower()

            # Exact substring match → high score
            if term_lower in text:
                score = 0.95
            else:
                # Fuzzy match: slide a window over detected text words
                score = _best_window_similarity(text, term_lower)

            if score > best_score:
                best_score = score
                best_key = key

    if best_key and best_score >= NAME_MATCH_RATIO:
        return OcrResult(
            medicine_key=best_key,
            confidence=best_score,
            raw_text=text,
        )
    return None


def _best_window_similarity(haystack: str, needle: str) -> float:
    """Slide a character window of len(needle) over haystack, return best ratio."""
    n = len(needle)
    best = 0.0
    for i in range(max(1, len(haystack) - n + 1)):
        window = haystack[i : i + n]
        ratio = _similarity(window, needle)
        if ratio > best:
            best = ratio
    return best
