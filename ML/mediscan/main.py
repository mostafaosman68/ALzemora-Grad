"""
MediScan — Medicine Detection System
Supports simultaneous detection of multiple medicines.

Controls:
  Q / Esc  — quit
  R        — reload reference images
  S        — toggle speech
  D        — toggle debug overlay
"""

import logging
import time
from dataclasses import dataclass, field

import cv2

from detector import MedicineDetector, OrbResult
from medicines import get_medicine
from ocr_reader import OcrReader, OcrResult
from overlay import (
    draw_bounding_box,
    draw_debug_scores,
    draw_medicine_panels,
    draw_no_references_warning,
    draw_scanning_indicator,
    draw_status_bar,
)
from tts import SpeechEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mediscan")

# ── Tuning ────────────────────────────────────────────────────────────────
CAMERA_INDEX       = 0
CONFIRM_FRAMES     = 5     # consecutive ORB hits to confirm a medicine
UNCONFIRM_FRAMES   = 8     # consecutive ORB misses to clear a medicine
DETECTION_HOLD_S   = 2.0   # keep panel visible this long after last ORB hit
SPEECH_REPEAT_S    = 5.0   # repeat medicine name every N seconds while in view
OCR_EVERY_N_FRAMES = 8
OCR_RESULT_TTL_S   = 3.0
ORB_SOLO_THRESHOLD = 0.45  # confirm via ORB alone if confidence >= this
# ──────────────────────────────────────────────────────────────────────────

WINDOW_TITLE = "MediScan — Medicine Detection"


@dataclass
class MedState:
    """Per-medicine tracking state."""
    hits: int = 0                  # consecutive ORB frames matching this key
    misses: int = 0                # consecutive frames NOT matching (while confirmed)
    confirmed: bool = False
    last_confirmed_time: float = 0.0
    last_spoke_time: float = 0.0
    orb_result: OrbResult | None = None      # latest live ORB result (may be absent)
    stable_bbox: tuple[int, int, int, int] | None = None   # last known good bbox — held while confirmed


def main() -> None:
    logger.info("Starting MediScan")

    detector = MedicineDetector()
    ocr = OcrReader()
    speech = SpeechEngine()

    speech_enabled = True
    debug_mode = False

    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        logger.error("Cannot open camera (index %d)", CAMERA_INDEX)
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_TITLE, 1280, 720)

    # One MedState per medicine key
    states: dict[str, MedState] = {k: MedState() for k in detector.loaded_keys()}

    ocr_result: OcrResult | None = None
    ocr_result_time = 0.0

    fps_counter = 0
    fps_display = 0.0
    fps_timer = time.time()
    tick = 0
    debug_scores_cache: dict[str, float] = {}

    logger.info("Camera ready. ORB refs: %s", detector.loaded_keys())

    while True:
        ret, frame = cap.read()
        if not ret:
            logger.error("Frame read failed")
            break

        now = time.time()
        tick += 1
        fps_counter += 1
        if now - fps_timer >= 1.0:
            fps_display = fps_counter / (now - fps_timer)
            fps_counter = 0
            fps_timer = now

        # ── OCR ───────────────────────────────────────────────────────────
        if ocr.is_ready() and tick % OCR_EVERY_N_FRAMES == 0:
            ocr.submit_frame(frame)

        fresh = ocr.get_result()
        if fresh is not None:
            ocr_result = fresh
            ocr_result_time = now

        if ocr_result is not None and (now - ocr_result_time) > OCR_RESULT_TTL_S:
            ocr_result = None

        # ── ORB — get all detections this frame ───────────────────────────
        orb_results, debug_info = detector.detect(frame)
        if debug_info.orb:
            debug_scores_cache = debug_info.orb

        matched_keys = {r.medicine_key for r in orb_results}
        orb_by_key = {r.medicine_key: r for r in orb_results}

        # ── Update per-medicine state ─────────────────────────────────────
        for key, state in states.items():
            orb = orb_by_key.get(key)

            if orb is not None:
                state.hits += 1
                state.misses = 0
                state.orb_result = orb
                if orb.bbox is not None:
                    state.stable_bbox = orb.bbox   # lock in latest good bbox
            else:
                state.hits = 0
                if state.confirmed:
                    state.misses += 1

            # ── Confirm ───────────────────────────────────────────────────
            if not state.confirmed and state.hits >= CONFIRM_FRAMES:
                ocr_fresh = ocr_result is not None and (now - ocr_result_time) <= OCR_RESULT_TTL_S
                ocr_agrees = ocr_fresh and ocr_result is not None and ocr_result.medicine_key == key
                orb_strong = orb is not None and orb.confidence >= ORB_SOLO_THRESHOLD

                if ocr_agrees or orb_strong:
                    state.confirmed = True
                    state.last_spoke_time = 0.0  # speak immediately on first confirm
                    logger.info("Confirmed: %s", key)

            # ── Refresh hold timer while ORB is actively matching ─────────
            if state.confirmed and orb is not None:
                state.last_confirmed_time = now

            # ── Unconfirm ─────────────────────────────────────────────────
            if state.confirmed:
                hold_expired = (now - state.last_confirmed_time) > DETECTION_HOLD_S
                too_many_misses = state.misses >= UNCONFIRM_FRAMES
                if hold_expired or too_many_misses:
                    logger.info("Cleared: %s (hold=%.1fs misses=%d)",
                                key, now - state.last_confirmed_time, state.misses)
                    state.confirmed = False
                    state.hits = 0
                    state.misses = 0
                    state.last_spoke_time = 0.0
                    state.stable_bbox = None

        # ── Speech — collected AFTER per-medicine loop ────────────────────
        # Must be outside the loop: calling speech.speak() twice in the same
        # loop iteration kills the first utterance before it plays.
        if speech_enabled:
            pending: list[str] = []
            for key, state in states.items():
                if state.confirmed and (now - state.last_spoke_time) >= SPEECH_REPEAT_S:
                    med = get_medicine(key)
                    pending.append(med["name"] if med else key.replace("_", " ").title())
                    state.last_spoke_time = now

            if pending:
                combined = ". ".join(pending)
                logger.info("Speaking: '%s'", combined)
                speech.speak(combined)

        # ── Rendering ─────────────────────────────────────────────────────
        confirmed_keys = [k for k, s in states.items() if s.confirmed]

        if detector.reference_count() == 0:
            draw_no_references_warning(frame)
        elif confirmed_keys:
            # Draw bounding boxes using stable_bbox so the box doesn't flicker
            # when ORB misses a frame mid-hold.
            for idx, key in enumerate(confirmed_keys):
                st = states[key]
                if st.stable_bbox is not None:
                    conf = st.orb_result.confidence if st.orb_result else 0.0
                    draw_bounding_box(frame, st.stable_bbox, conf, key, idx)

            # Draw stacked info panels for all confirmed medicines
            medicines = [(key, get_medicine(key)) for key in confirmed_keys]
            draw_medicine_panels(frame, medicines)
        else:
            draw_scanning_indicator(frame, tick)

        if debug_mode:
            draw_debug_scores(frame, debug_scores_cache, 0, None, ocr_result)

        confirmed_str = ", ".join(confirmed_keys) if confirmed_keys else "—"
        ocr_status = (
            " | OCR: loading..." if not ocr.is_ready()
            else (f" | OCR: {ocr_result.medicine_key} ({ocr_result.confidence:.2f})" if ocr_result else "")
        )
        status = f"Detected: {confirmed_str}{ocr_status}   Speech: {'ON' if speech_enabled else 'OFF'}"
        draw_status_bar(frame, fps_display, status, detector.reference_count())

        cv2.imshow(WINDOW_TITLE, frame)

        key_press = cv2.waitKey(1) & 0xFF
        if key_press in (ord("q"), 27):
            break
        elif key_press == ord("r"):
            detector = MedicineDetector()
            states = {k: MedState() for k in detector.loaded_keys()}
            logger.info("Reloaded: %s", detector.loaded_keys())
        elif key_press == ord("s"):
            speech_enabled = not speech_enabled
            logger.info("Speech %s", "ON" if speech_enabled else "OFF")
        elif key_press == ord("d"):
            debug_mode = not debug_mode

    cap.release()
    cv2.destroyAllWindows()
    speech.stop()
    logger.info("Stopped")


if __name__ == "__main__":
    main()
