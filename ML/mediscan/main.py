"""
MediScan — Medicine Detection System

Controls:
  Q / Esc  — quit
  R        — reload from DB
  S        — toggle speech
  D        — toggle debug overlay

CLI args (coordinator mode):
  --medication-id   <id>
  --medication-name <name>
  --patient-id      <id>
"""

import argparse
import logging
import os
import queue
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import cv2
import numpy as np
import requests
from detector import MedicineDetector, OrbResult
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

_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mediscan")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

# ── Tuning ────────────────────────────────────────────────────────────────
CAMERA_WIDTH       = 640
CAMERA_HEIGHT      = 480
DETECT_WIDTH       = 480
DETECT_HEIGHT      = 360
CONFIRM_FRAMES     = 1     # single confident ORB hit confirms immediately
UNCONFIRM_FRAMES   = 10
DETECTION_HOLD_S   = 2.0
SPEECH_REPEAT_S    = 120.0
OCR_EVERY_N_FRAMES = 10
OCR_RESULT_TTL_S   = 3.0
ORB_SOLO_THRESHOLD = 0.22  # confidence needed for solo-ORB confirmation
# ──────────────────────────────────────────────────────────────────────────

PREFERRED_CAMERA = '/dev/video0'
WINDOW_TITLE     = "MediScan — Medicine Detection"


# ── Camera stream ─────────────────────────────────────────────────────────

class CameraStream:
    """Background thread that always provides the most recent camera frame.
    Eliminates the OpenCV buffer lag that causes visible delay."""

    def __init__(self, src: str, width: int, height: int) -> None:
        self._cap = cv2.VideoCapture(src)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open camera: {src}")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._frame: Optional[np.ndarray] = None
        self._lock  = threading.Lock()
        self._stop  = False
        threading.Thread(target=self._run, daemon=True, name="cam").start()

    def _run(self) -> None:
        while not self._stop:
            ok, frame = self._cap.read()
            if ok and frame is not None:
                with self._lock:
                    self._frame = frame

    def read(self) -> tuple[bool, Optional[np.ndarray]]:
        with self._lock:
            if self._frame is None:
                return False, None
            return True, self._frame.copy()

    def release(self) -> None:
        self._stop = True
        self._cap.release()


# ── ORB worker ────────────────────────────────────────────────────────────

class OrbWorker:
    """Runs detector.detect() in a background thread so the display loop
    is never blocked by ORB computation. submit() and get() are both
    non-blocking — the worker always processes the newest frame."""

    def __init__(self, detector: MedicineDetector) -> None:
        self._detector = detector
        self._frame_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=1)
        self._lock   = threading.Lock()
        self._result: tuple[list[OrbResult], Any] = ([], None)
        threading.Thread(target=self._run, daemon=True, name="orb").start()

    def submit(self, frame: np.ndarray) -> None:
        try:
            self._frame_q.get_nowait()
        except queue.Empty:
            pass
        self._frame_q.put(frame)

    def get(self) -> tuple[list[OrbResult], Any]:
        with self._lock:
            return self._result

    def _run(self) -> None:
        while True:
            try:
                frame = self._frame_q.get(timeout=1.0)
            except queue.Empty:
                continue
            results, debug = self._detector.detect(frame)
            with self._lock:
                self._result = (results, debug)


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_key(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '_', name.lower()).strip('_')


def _med_to_display(doc: dict | None, key: str) -> dict | None:
    if doc is None:
        return None
    schedule_str = "—"
    sched = doc.get("schedule")
    if isinstance(sched, str) and sched:
        schedule_str = sched
    elif isinstance(sched, dict):
        parts = []
        if isinstance(sched.get("days"), list):
            parts.append(", ".join(sched["days"]))
        for t_key in ("time", "hour"):
            if sched.get(t_key):
                parts.append(str(sched[t_key]))
                break
        schedule_str = " · ".join(parts) or "—"
    return {
        "name":         doc.get("name") or key.replace("_", " ").title(),
        "generic_name": f"Schedule: {schedule_str}",
        "category":     doc.get("category") or "Medication",
        "dosage_form":  doc.get("dosage_form") or "—",
        "strength":     doc.get("strength") or "—",
        "manufacturer": doc.get("manufacturer") or "—",
        "description":  doc.get("description") or "No description.",
        "warnings":     doc.get("warnings") or "Take as prescribed by your doctor.",
    }


def _build_speech(doc: dict | None, key: str) -> str:
    if doc is None:
        name = key.replace("_", " ").title()
        return f"This is {name}. {name}."
    name = doc.get("name") or key.replace("_", " ").title()
    sched = doc.get("schedule")
    time_str = days_str = ""
    if isinstance(sched, dict):
        days = sched.get("days") or []
        if days:
            days_str = ", ".join(days)
        time_str = sched.get("time") or ""
        if not time_str and sched.get("hour"):
            time_str = f"{sched['hour']} {sched.get('period', '')}".strip()
    elif isinstance(sched, str) and sched:
        time_str = sched
    parts = [f"This is {name}. {name}"]
    if days_str and time_str:
        parts.append(f"Take it on {days_str} at {time_str}")
    elif days_str:
        parts.append(f"Take it on {days_str}")
    elif time_str:
        parts.append(f"Take it at {time_str}")
    return ". ".join(parts) + "."


def fetch_patient_medications() -> tuple[list[dict], dict[str, dict]]:
    try:
        resp = requests.get(f"{API_BASE_URL}/users/active-patient", timeout=5)
        resp.raise_for_status()
        patient    = resp.json()
        patient_id = patient.get("user_id")
        if not patient_id:
            logger.error("active-patient missing user_id")
            return [], {}
        logger.info("Active patient: %s (ID: %s)", patient.get("full_name"), patient_id)
    except Exception as e:
        logger.warning("Could not reach backend: %s", e)
        return [], {}
    try:
        resp   = requests.get(f"{API_BASE_URL}/medications/{patient_id}", timeout=10)
        resp.raise_for_status()
        items  = resp.json().get("items", [])
        lookup = {_make_key(m["name"]): m for m in items if m.get("name")}
        logger.info("Fetched %d medication(s) from DB", len(items))
        return items, lookup
    except Exception as e:
        logger.warning("Could not fetch medications: %s", e)
        return [], {}


def report_medication_detected(
    patient_id: str,
    medication_id: Optional[str],
    medication_name: Optional[str],
    confidence: float,
) -> None:
    try:
        resp = requests.post(
            f"{API_BASE_URL}/medscan/detected",
            json={
                "patient_id":      patient_id,
                "medication_id":   medication_id,
                "medication_name": medication_name,
                "confidence":      confidence,
            },
            timeout=5,
        )
        resp.raise_for_status()
        logger.info("Reported to backend: %s (conf=%.2f)", medication_name, confidence)
    except Exception as exc:
        logger.error("Failed to report: %s", exc)


# ── Per-medicine tracking state ───────────────────────────────────────────

@dataclass
class MedState:
    hits: int = 0
    misses: int = 0
    confirmed: bool = False
    last_confirmed_time: float = 0.0
    last_spoke_time: float = 0.0
    orb_result: OrbResult | None = None
    stable_bbox: tuple[int, int, int, int] | None = None


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--medication-id",   default=None)
    parser.add_argument("--medication-name", default=None)
    parser.add_argument("--patient-id",      default=None)
    args, _ = parser.parse_known_args()

    target_med_id:   Optional[str] = args.medication_id
    target_med_name: Optional[str] = args.medication_name
    patient_id:      Optional[str] = args.patient_id
    targeted_mode = target_med_id is not None or target_med_name is not None

    if targeted_mode:
        logger.info("TARGETED mode — %s (%s)", target_med_name, target_med_id)
    else:
        logger.info("FULL mode — detecting all medications")

    medications, med_lookup = fetch_patient_medications()

    if targeted_mode and target_med_id:
        medications = [m for m in medications if str(m.get("_id", "")) == target_med_id]
        if not medications and target_med_name:
            medications = [m for m in med_lookup.values()
                           if m.get("name", "").lower() == target_med_name.lower()]
        if medications:
            logger.info("Loaded target: %s", medications[0].get("name"))
        else:
            logger.warning("Target not found — falling back to all medications")
            medications, med_lookup = fetch_patient_medications()

    # Build detector — descriptors load from disk cache if image hasn't changed
    detector = MedicineDetector()
    detector.load_from_medications(medications)
    if not medications:
        logger.warning("No medications from DB — nothing to detect.")

    ocr    = OcrReader()
    speech = SpeechEngine()

    # Give OCR the actual DB medicine names so "Telfast" etc. match correctly
    ocr.update_medicines(med_lookup)

    speech_enabled = True
    debug_mode     = False

    try:
        cam = CameraStream(PREFERRED_CAMERA, CAMERA_WIDTH, CAMERA_HEIGHT)
    except RuntimeError as e:
        logger.error("%s", e)
        return
    logger.info("Camera opened: %s", PREFERRED_CAMERA)

    orb_worker = OrbWorker(detector)

    gui_available = False
    try:
        cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_TITLE, CAMERA_WIDTH, CAMERA_HEIGHT)
        gui_available = True
        logger.info("GUI mode enabled")
    except Exception as e:
        logger.warning("GUI not available (%s) — headless mode", e)

    states: dict[str, MedState] = {k: MedState() for k in detector.loaded_keys()}

    ocr_result:      OcrResult | None = None
    ocr_result_time: float            = 0.0

    fps_counter = 0
    fps_display = 0.0
    fps_timer   = time.time()
    tick        = 0
    debug_scores_cache: dict[str, float] = {}
    _orb_log_timer = 0.0

    logger.info("Ready. ORB refs: %s", detector.loaded_keys())

    while True:
        ok, frame = cam.read()
        if not ok or frame is None:
            time.sleep(0.005)
            continue

        now = time.time()
        tick += 1
        fps_counter += 1
        if now - fps_timer >= 1.0:
            fps_display = fps_counter / (now - fps_timer)
            fps_counter = 0
            fps_timer   = now

        # ── Submit every frame to background ORB worker (non-blocking) ────
        small = cv2.resize(frame, (DETECT_WIDTH, DETECT_HEIGHT))
        orb_worker.submit(small)

        # ── Retrieve latest ORB result (non-blocking) ─────────────────────
        orb_results, debug_info = orb_worker.get()

        if orb_results:
            scale_x = frame.shape[1] / DETECT_WIDTH
            scale_y = frame.shape[0] / DETECT_HEIGHT
            for r in orb_results:
                if r.bbox is not None:
                    x, y, w, h = r.bbox
                    r.bbox = (int(x * scale_x), int(y * scale_y),
                              int(w * scale_x), int(h * scale_y))

        if debug_info and getattr(debug_info, "orb", None):
            debug_scores_cache = debug_info.orb
            # Log ORB scores every 2 seconds so CV activity is visible
            if now - _orb_log_timer >= 2.0:
                scores_str = "  ".join(
                    f"{k}={v:.3f}" for k, v in debug_info.orb.items()
                )
                logger.info("ORB scores: %s  (threshold=%.2f)", scores_str, ORB_SOLO_THRESHOLD)
                _orb_log_timer = now

        # ── OCR ───────────────────────────────────────────────────────────
        if ocr.is_ready() and tick % OCR_EVERY_N_FRAMES == 0:
            ocr.submit_frame(frame)

        fresh = ocr.get_result()
        if fresh is not None:
            ocr_result      = fresh
            ocr_result_time = now

        if ocr_result is not None and (now - ocr_result_time) > OCR_RESULT_TTL_S:
            ocr_result = None

        orb_by_key = {r.medicine_key: r for r in orb_results}

        # ── Update per-medicine state ─────────────────────────────────────
        for key, state in states.items():
            orb = orb_by_key.get(key)

            if orb is not None:
                state.hits  += 1
                state.misses = 0
                state.orb_result = orb
                if orb.bbox is not None:
                    state.stable_bbox = orb.bbox
            else:
                if state.confirmed:
                    state.misses += 1
                else:
                    state.hits = max(0, state.hits - 1)

            # ── Confirm (CONFIRM_FRAMES=1: first confident hit confirms) ──
            if not state.confirmed and state.hits >= CONFIRM_FRAMES:
                ocr_fresh  = ocr_result is not None and (now - ocr_result_time) <= OCR_RESULT_TTL_S
                ocr_agrees = ocr_fresh and ocr_result is not None and ocr_result.medicine_key == key
                orb_strong = orb is not None and orb.confidence >= ORB_SOLO_THRESHOLD

                if ocr_agrees or orb_strong:
                    state.confirmed           = True
                    state.last_spoke_time     = 0.0
                    state.last_confirmed_time = now
                    logger.info("Confirmed: %s (conf=%.2f)", key,
                                orb.confidence if orb else 0.0)

            if state.confirmed and orb is not None:
                state.last_confirmed_time = now

            if state.confirmed:
                hold_expired    = (now - state.last_confirmed_time) > DETECTION_HOLD_S
                too_many_misses = state.misses >= UNCONFIRM_FRAMES
                if hold_expired or too_many_misses:
                    logger.info("Cleared: %s", key)
                    state.confirmed   = False
                    state.hits        = 0
                    state.misses      = 0
                    state.stable_bbox = None

        # ── Speech (full mode only — targeted mode speech handled by med_timing) ─
        if speech_enabled and not targeted_mode:
            pending: list[str] = []
            for key, state in states.items():
                if state.confirmed and (now - state.last_spoke_time) >= SPEECH_REPEAT_S:
                    pending.append(_build_speech(med_lookup.get(key), key))
                    state.last_spoke_time = now
            if pending:
                speech.speak(". ".join(pending))

        # ── Targeted mode exit ────────────────────────────────────────────
        if targeted_mode:
            target_key = _make_key(target_med_name or "")
            for key, state in states.items():
                if state.confirmed and (key == target_key or len(states) == 1):
                    conf = state.orb_result.confidence if state.orb_result else 0.0
                    logger.info("Target confirmed — reporting (conf=%.2f)", conf)
                    if patient_id:
                        report_medication_detected(patient_id, target_med_id, target_med_name, conf)
                    cam.release()
                    if gui_available:
                        cv2.destroyAllWindows()
                    speech.stop()
                    return

        # ── Rendering ─────────────────────────────────────────────────────
        confirmed_keys = [k for k, s in states.items() if s.confirmed]

        if gui_available:
            if detector.reference_count() == 0:
                draw_no_references_warning(frame)
            elif confirmed_keys:
                for idx, key in enumerate(confirmed_keys):
                    st = states[key]
                    if st.stable_bbox is not None:
                        conf = st.orb_result.confidence if st.orb_result else 0.0
                        draw_bounding_box(frame, st.stable_bbox, conf, key, idx)
                medicines = [(key, _med_to_display(med_lookup.get(key), key))
                             for key in confirmed_keys]
                draw_medicine_panels(frame, medicines)
            else:
                draw_scanning_indicator(frame, tick)

            if debug_mode:
                draw_debug_scores(frame, debug_scores_cache, 0, None, ocr_result)

            confirmed_str = ", ".join(confirmed_keys) if confirmed_keys else "—"
            ocr_status = (
                " | OCR: loading..." if not ocr.is_ready()
                else (f" | OCR: {ocr_result.medicine_key} ({ocr_result.confidence:.2f})"
                      if ocr_result else "")
            )
            draw_status_bar(
                frame, fps_display,
                f"Detected: {confirmed_str}{ocr_status}   Speech: {'ON' if speech_enabled else 'OFF'}",
                detector.reference_count(),
            )
        else:
            if confirmed_keys:
                logger.info("Detected: %s", ", ".join(confirmed_keys))

        if gui_available:
            cv2.imshow(WINDOW_TITLE, frame)
            key_press = cv2.waitKey(1) & 0xFF
        else:
            time.sleep(0.005)
            key_press = 0

        if key_press in (ord("q"), 27):
            break
        elif key_press == ord("r"):
            medications, med_lookup = fetch_patient_medications()
            detector = MedicineDetector()
            detector.load_from_medications(medications)
            ocr.update_medicines(med_lookup)
            orb_worker = OrbWorker(detector)
            states = {k: MedState() for k in detector.loaded_keys()}
            logger.info("Reloaded from DB: %s", detector.loaded_keys())
        elif key_press == ord("s"):
            speech_enabled = not speech_enabled
            logger.info("Speech %s", "ON" if speech_enabled else "OFF")
        elif key_press == ord("d"):
            debug_mode = not debug_mode

    cam.release()
    if gui_available:
        cv2.destroyAllWindows()
    speech.stop()
    logger.info("Stopped")


if __name__ == "__main__":
    main()
