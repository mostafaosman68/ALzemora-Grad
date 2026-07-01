"""
Main AI entry point — Raspberry Pi smart glasses.

Reads the GPIO light sensor (PIN 17) to detect when the glasses are worn,
then spawns the face/voice recognition process (multimodal_recognizer.py).

Medication timing is managed by MedTimingController (med_timing.py) running
in a background thread.  When a medication is due it:
  1. Stops the face/voice recognition camera.
  2. Runs mediscan/main.py for up to 5 minutes (or until the medication
     is confirmed by the camera).
  3. Sends a medication_missed alert to the backend if not detected.
  4. Resumes normal face/voice recognition automatically.

Usage:
  python main_ai.py [patient_id]

  patient_id can also be provided via the PATIENT_ID environment variable.
  Without it, medication scheduling is disabled and only GPIO camera
  control runs.
"""
import logging
import os
import subprocess
import sys
import threading
import time

import RPi.GPIO as GPIO

from med_timing import MedTimingController

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main_ai")

# ── GPIO config ───────────────────────────────────────────────────────────────
PIN       = 17
THRESHOLD = 3    # consecutive HIGH reads before starting camera

# ── Patient config ─────────────────────────────────────────────────────────────
PATIENT_ID = os.getenv("PATIENT_ID") or (
    sys.argv[1] if len(sys.argv) > 1 else ""
)

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
_RECOGNIZER_SCRIPT = os.path.join(_BASE_DIR, "multimodal_recognizer.py")

# ── Camera state ──────────────────────────────────────────────────────────────
_camera_running = False
_process: subprocess.Popen | None = None
_medscan_active = threading.Event()   # set while MediScan session is running


def _start_camera() -> None:
    global _camera_running, _process
    if _camera_running or _medscan_active.is_set():
        return
    logger.info("Camera ON — starting face/voice recognition")
    _process = subprocess.Popen(
        [sys.executable, "-u", _RECOGNIZER_SCRIPT],
        env=os.environ.copy(),
    )
    _camera_running = True


def _stop_camera() -> None:
    global _camera_running, _process
    if not _camera_running:
        return
    logger.info("Camera OFF")
    if _process:
        _process.terminate()
        try:
            _process.wait(timeout=5)   # wait for OS to release /dev/video0
        except subprocess.TimeoutExpired:
            _process.kill()
            _process.wait()
        _process = None
    _camera_running = False


# ── MediScan handoff callbacks ────────────────────────────────────────────────

def _on_medscan_start() -> None:
    """Called by MedTimingController just before launching MediScan."""
    logger.info("Medication due — pausing face/voice recognition for MediScan")
    _medscan_active.set()    # block GPIO loop from restarting camera
    _stop_camera()


def _on_medscan_end() -> None:
    """Called by MedTimingController after the MediScan session ends."""
    logger.info("MediScan session complete — resuming face/voice recognition")
    _medscan_active.clear()
    # The GPIO loop restarts the camera on the next tick if glasses are worn


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    GPIO.cleanup()
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIN, GPIO.IN)

    # Pass PATIENT_ID (may be ""); MedTimingController.start() auto-fetches it
    # from /users/active-patient when empty.
    med_controller = MedTimingController(
        patient_id=PATIENT_ID,
        on_medscan_start=_on_medscan_start,
        on_medscan_end=_on_medscan_end,
    )
    med_controller.start()

    bright_counter = 0

    try:
        while True:
            value = GPIO.input(PIN)

            if value == 1:       # light detected → glasses worn
                bright_counter += 1
            else:
                bright_counter = 0

            if _medscan_active.is_set():
                pass             # MediScan owns the camera — do nothing
            elif bright_counter >= THRESHOLD:
                _start_camera()
            else:
                _stop_camera()

            time.sleep(0.3)

    except KeyboardInterrupt:
        logger.info("Exiting...")
        med_controller.stop()
        _stop_camera()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
