"""
ML Coordinator — owns the camera lifecycle on the Raspberry Pi.

Runs as the single long-lived process launched by the backend's
/start-recognition endpoint.  It polls the backend every POLL_INTERVAL
seconds for the current system mode and spawns the right child process:

  face_recognition  → user_aware_recognizer.py  (default)
  medscan           → mediscan/main.py           (when a medication is due)

When MediScan detects the medication it posts to /medscan/detected,
which flips the mode back to face_recognition.  The coordinator then
kills MediScan and restarts face/voice recognition automatically.

Safety guards:
  - Dead process auto-restart (both modes)
  - MEDSCAN_TIMEOUT_S: if MediScan runs longer than this without
    confirming, the coordinator resets the mode and switches back.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from typing import Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("coordinator")

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_RECOGNITION_SCRIPT = os.path.join(_BASE_DIR, "user_aware_recognizer.py")
_MEDSCAN_SCRIPT = os.path.join(_BASE_DIR, "mediscan", "main.py")

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
POLL_INTERVAL = 5            # seconds between mode polls
MEDSCAN_TIMEOUT_S = 300      # 5 min — revert to face/voice if no detection


# ── Helpers ───────────────────────────────────────────────────────────────────

def _kill(proc: Optional[subprocess.Popen]) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.warning("Process did not terminate — killing")
        proc.kill()
    except Exception as exc:
        logger.error("Error killing process: %s", exc)


def _common_env() -> dict:
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    env.setdefault("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env.setdefault("API_BASE_URL", API_BASE_URL)
    return env


def _start_recognition(user_id: str) -> subprocess.Popen:
    env = _common_env()
    env["USER_ID_FOR_RECOGNITION"] = user_id
    logger.info("Starting face/voice recognition — user_id=%s", user_id)
    return subprocess.Popen(
        [sys.executable, "-u", _RECOGNITION_SCRIPT, user_id],
        env=env,
        stdout=open("/tmp/recognition_log.txt", "w"),
        stderr=subprocess.STDOUT,
    )


def _start_medscan(
    patient_id: str,
    medication_id: Optional[str],
    medication_name: Optional[str],
) -> subprocess.Popen:
    env = _common_env()
    args = [sys.executable, "-u", _MEDSCAN_SCRIPT]
    if medication_id:
        args += ["--medication-id", medication_id]
    if medication_name:
        args += ["--medication-name", medication_name]
    if patient_id:
        args += ["--patient-id", patient_id]

    logger.info(
        "Starting MediScan — target: %s (%s)", medication_name, medication_id
    )
    return subprocess.Popen(
        args,
        env=env,
        cwd=os.path.join(_BASE_DIR, "mediscan"),
        stdout=open("/tmp/medscan_log.txt", "w"),
        stderr=subprocess.STDOUT,
    )


def _fetch_mode(patient_id: str) -> dict:
    try:
        resp = requests.get(
            f"{API_BASE_URL}/ml-mode/{patient_id}", timeout=5
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("Could not fetch mode: %s", exc)
        return {"mode": "face_recognition"}


def _reset_mode(patient_id: str) -> None:
    try:
        requests.post(
            f"{API_BASE_URL}/ml-mode/{patient_id}",
            json={"mode": "face_recognition"},
            timeout=5,
        )
        logger.info("Reset mode → face_recognition")
    except Exception as exc:
        logger.warning("Could not reset mode: %s", exc)


# ── Main loop ─────────────────────────────────────────────────────────────────

def main(user_id: str, patient_id: str) -> None:
    logger.info(
        "Coordinator started — user_id=%s  patient_id=%s", user_id, patient_id
    )

    current_proc: Optional[subprocess.Popen] = None
    current_mode = "face_recognition"
    medscan_started_at = 0.0

    # Launch face/voice recognition immediately
    current_proc = _start_recognition(user_id)

    def _shutdown(signum, frame):
        logger.info("Coordinator received signal %s — shutting down", signum)
        _kill(current_proc)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    while True:
        time.sleep(POLL_INTERVAL)

        # ── Handle dead child process ──────────────────────────────────────
        if current_proc is not None and current_proc.poll() is not None:
            exit_code = current_proc.poll()
            if current_mode == "face_recognition":
                logger.warning(
                    "Recognition process exited (code %s) — restarting", exit_code
                )
                current_proc = _start_recognition(user_id)
            else:
                # MediScan exited — either detected successfully or crashed.
                # In both cases reset the mode and go back to face recognition.
                logger.info("MediScan exited (code %s)", exit_code)
                _reset_mode(patient_id)
                current_mode = "face_recognition"
                current_proc = _start_recognition(user_id)
                medscan_started_at = 0.0
            continue

        # ── MediScan timeout guard ─────────────────────────────────────────
        if current_mode == "medscan":
            elapsed = time.time() - medscan_started_at
            if elapsed > MEDSCAN_TIMEOUT_S:
                logger.warning(
                    "MediScan timed out after %.0fs — reverting to face/voice", elapsed
                )
                _kill(current_proc)
                _reset_mode(patient_id)
                current_mode = "face_recognition"
                current_proc = _start_recognition(user_id)
                medscan_started_at = 0.0
                continue

        # ── Poll backend for desired mode ──────────────────────────────────
        mode_data = _fetch_mode(patient_id)
        desired_mode = mode_data.get("mode", "face_recognition")

        if desired_mode == current_mode:
            continue

        # ── Mode switch ────────────────────────────────────────────────────
        logger.info("Mode change: %s → %s", current_mode, desired_mode)
        _kill(current_proc)

        if desired_mode == "medscan":
            current_proc = _start_medscan(
                patient_id,
                mode_data.get("pending_medication_id"),
                mode_data.get("pending_medication_name"),
            )
            current_mode = "medscan"
            medscan_started_at = time.time()
        else:
            current_proc = _start_recognition(user_id)
            current_mode = "face_recognition"
            medscan_started_at = 0.0


if __name__ == "__main__":
    # Priority: env vars > CLI args
    _user_id = os.environ.get("USER_ID_FOR_RECOGNITION") or (
        sys.argv[1] if len(sys.argv) > 1 else ""
    )
    _patient_id = os.environ.get("PATIENT_ID") or (
        sys.argv[2] if len(sys.argv) > 2 else _user_id
    )

    if not _user_id:
        logger.error("Usage: python coordinator.py <user_id> [patient_id]")
        sys.exit(1)

    main(_user_id, _patient_id)
