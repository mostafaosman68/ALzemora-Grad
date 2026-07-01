"""
Medication Timing Controller for ML/main_ai.py

Runs as a daemon background thread.  Every POLL_INTERVAL seconds it:
  1. Checks local cached medication schedules for the current minute.
  2. Also polls the backend mode as a secondary trigger.

When a medication is due it:
  - Announces via TTS: "It is time to take [name]. Please show the medication to the camera."
  - Calls on_medscan_start() so main_ai.py stops face/voice and blocks GPIO.
  - Spawns mediscan/main.py with the target medication args.
  - Waits up to MEDSCAN_TIMEOUT seconds (default 300) for detection.
  - If detected → resets backend mode and notifies dashboard.
  - If timed out → posts medication_missed alert.
  - Calls on_medscan_end() so GPIO resumes camera control.

The medication list is refreshed from the backend every REFRESH_INTERVAL seconds
and cached locally, so timing works even if the network drops temporarily.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Callable, Optional

import requests

logger = logging.getLogger("med_timing")

API_BASE_URL     = os.getenv("API_BASE_URL",          "http://127.0.0.1:8000")
POLL_INTERVAL    = int(os.getenv("MED_POLL_INTERVAL",    "20"))   # seconds between checks
MEDSCAN_TIMEOUT  = int(os.getenv("MEDSCAN_TIMEOUT_S",    "300"))  # max seconds for MediScan
REFIRE_COOLDOWN  = int(os.getenv("MED_REFIRE_COOLDOWN",  "300"))  # 5 min between same-med fires
REFRESH_INTERVAL = int(os.getenv("MED_REFRESH_INTERVAL", "120"))  # seconds between med-list refreshes

_BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
_MEDSCAN_MAIN = os.path.join(_BASE_DIR, "mediscan", "main.py")

_WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# ── Piper TTS paths (ML/piper/ directory) ─────────────────────────────────────
_PIPER_DIR   = os.path.join(_BASE_DIR, "piper")
_PIPER_BIN   = os.path.join(_PIPER_DIR, "piper")
_PIPER_MODEL = os.path.join(_PIPER_DIR, "voices", "en_US-lessac-medium.onnx")


def _piper_env() -> dict:
    env = os.environ.copy()
    existing = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = f"{_PIPER_DIR}:{existing}" if existing else _PIPER_DIR
    env["ESPEAK_DATA_PATH"] = os.path.join(_PIPER_DIR, "espeak-ng-data")
    return env


def _piper_sample_rate() -> int:
    try:
        import json
        with open(_PIPER_MODEL + ".json") as f:
            return int(json.load(f).get("audio", {}).get("sample_rate", 22050))
    except Exception:
        return 22050


# ── TTS ───────────────────────────────────────────────────────────────────────

def _speak(text: str) -> None:
    """Speak text via Piper neural TTS → aplay (blocking until audio finishes)."""
    safe = text.replace('"', "").replace("'", "").replace(";", "")
    logger.info("[MedTiming] TTS: %s", safe)

    if not os.path.isfile(_PIPER_BIN) or not os.path.isfile(_PIPER_MODEL):
        logger.warning("[MedTiming] Piper binary or model not found — no audio output")
        return

    try:
        sample_rate = _piper_sample_rate()
        env = _piper_env()

        piper = subprocess.Popen(
            [_PIPER_BIN, "--model", _PIPER_MODEL, "--output_raw", "--quiet"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        aplay = subprocess.Popen(
            ["aplay", "-r", str(sample_rate), "-f", "S16_LE", "-t", "raw", "-q", "-"],
            stdin=piper.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        piper.stdout.close()          # let aplay own the read end
        piper.communicate(input=safe.encode())
        aplay.wait()
    except Exception as exc:
        logger.error("[MedTiming] Piper TTS failed: %s", exc)


# ── Schedule matching ─────────────────────────────────────────────────────────

def _time_matches(schedule: dict, now: datetime) -> bool:
    """Return True when the medication schedule matches the current local minute."""
    if not isinstance(schedule, dict):
        return False

    days: list = schedule.get("days") or []
    if days:
        if _WEEKDAY_SHORT[now.weekday()] not in days:
            return False

    hour:   Optional[int] = None
    minute: int           = 0

    raw_hour   = schedule.get("hour")
    raw_minute = schedule.get("minute")

    if raw_hour is not None:
        try:
            hour   = int(raw_hour)
            minute = int(raw_minute or 0)
        except (TypeError, ValueError):
            hour = None

    if hour is None:
        time_str: str = schedule.get("time") or ""
        if time_str:
            try:
                parts  = time_str.strip().split()
                hm     = parts[0].split(":")
                h      = int(hm[0])
                m      = int(hm[1]) if len(hm) > 1 else 0
                if len(parts) > 1:
                    period = parts[1].upper()
                    if period == "PM" and h != 12:
                        h += 12
                    elif period == "AM" and h == 12:
                        h = 0
                hour, minute = h, m
            except Exception:
                return False

    if hour is None:
        return False

    period: str = str(schedule.get("period") or "").upper()
    if period == "PM" and hour != 12:
        hour += 12
    elif period == "AM" and hour == 12:
        hour = 0

    return now.hour == hour and now.minute == minute


# ── Controller ────────────────────────────────────────────────────────────────

class MedTimingController:
    """
    Background thread that watches medication schedules and triggers MediScan.

    Parameters
    ----------
    patient_id      Patient's MongoDB user ID. Pass "" to auto-fetch from backend.
    on_medscan_start  Callback called before MediScan launches (stop face/voice camera).
    on_medscan_end    Callback called after MediScan finishes (resume GPIO camera loop).
    python_exe        Python interpreter for the MediScan subprocess.
    """

    def __init__(
        self,
        patient_id: str,
        on_medscan_start: Callable[[], None],
        on_medscan_end: Callable[[], None],
        python_exe: str = sys.executable,
    ) -> None:
        self.patient_id       = patient_id
        self.on_medscan_start = on_medscan_start
        self.on_medscan_end   = on_medscan_end
        self.python_exe       = python_exe

        self._stop_event        = threading.Event()
        self._fired_cache:  dict[str, float] = {}
        self._med_cache:    list = []
        self._last_refresh: float = 0.0

        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="med_timing"
        )

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self) -> None:
        # Auto-fetch patient_id if not provided
        if not self.patient_id:
            self.patient_id = self._fetch_active_patient_id()
            if not self.patient_id:
                logger.error("[MedTiming] Could not determine patient_id — scheduling disabled")
                return

        self._thread.start()
        logger.info(
            "[MedTiming] Started — patient=%s  poll=%ds  timeout=%ds",
            self.patient_id, POLL_INTERVAL, MEDSCAN_TIMEOUT,
        )

    def stop(self) -> None:
        self._stop_event.set()

    # ── Background loop ───────────────────────────────────────────────────────

    def _loop(self) -> None:
        # Refresh medications immediately on first run
        self._refresh_medications()

        while not self._stop_event.is_set():
            try:
                self._check_and_trigger()
            except Exception as exc:
                logger.error("[MedTiming] Unexpected error: %s", exc)
            self._stop_event.wait(POLL_INTERVAL)

    def _refresh_medications(self) -> None:
        meds = self._fetch_medications()
        if meds:
            self._med_cache    = meds
            self._last_refresh = time.time()
            logger.info("[MedTiming] Cached %d medication(s)", len(meds))
        elif not self._med_cache:
            logger.warning("[MedTiming] No medications available — backend reachable?")

    def _check_and_trigger(self) -> None:
        # Refresh cached medication list periodically
        if time.time() - self._last_refresh >= REFRESH_INTERVAL:
            self._refresh_medications()

        now = datetime.now()
        logger.debug(
            "[MedTiming] Check at %s | %d meds cached",
            now.strftime("%H:%M:%S"), len(self._med_cache),
        )

        # ── Primary path: backend already signalled "medscan" ─────────────────
        mode_data = self._fetch_backend_mode()
        if mode_data and mode_data.get("mode") == "medscan":
            med_id    = mode_data.get("pending_medication_id")
            med_name  = mode_data.get("pending_medication_name") or "medication"
            cache_key = med_id or med_name   # shared key — prevents local path re-firing
            if time.time() - self._fired_cache.get(cache_key, 0.0) >= REFIRE_COOLDOWN:
                self._fired_cache[cache_key] = time.time()
                logger.info("[MedTiming] Backend triggered medscan for '%s'", med_name)
                self._run_full_session(med_id, med_name)
            return

        # ── Local path: match cached schedule against current time ─────────────
        for med in self._med_cache:
            if med.get("is_active") is False:
                continue

            schedule = med.get("schedule") or {}
            if not _time_matches(schedule, now):
                continue

            med_id    = str(med.get("_id") or med.get("id") or "")
            med_name  = med.get("name") or "medication"
            cache_key = med_id or med_name   # same key format as backend path

            if now.timestamp() - self._fired_cache.get(cache_key, 0.0) < REFIRE_COOLDOWN:
                logger.debug("[MedTiming] '%s' already fired recently — skipping", med_name)
                continue

            logger.info(
                "[MedTiming] Schedule match: '%s' at %s — triggering MediScan",
                med_name, now.strftime("%H:%M"),
            )
            self._fired_cache[cache_key] = now.timestamp()
            # Tell backend to create the alert + send FCM to helpers
            self._set_backend_mode_medscan(med_id, med_name)
            self._run_full_session(med_id, med_name)
            return   # one medication at a time

    # ── MediScan session ──────────────────────────────────────────────────────

    def _run_full_session(self, medication_id: Optional[str], medication_name: str) -> None:
        """Announce, suspend face/voice, run MediScan, then resume."""
        # 1. Announce via speaker FIRST (before stopping the camera)
        _speak(f"This is {medication_name}. You have to take it now.")

        # 2. Stop face/voice recognition and block GPIO from restarting it
        self.on_medscan_start()

        detected = False
        try:
            detected = self._run_medscan_subprocess(medication_id, medication_name)
        finally:
            self._post_reset_mode()
            if detected:
                _speak("Well done.")
            else:
                self._send_missed_alert(medication_id, medication_name)
            self.on_medscan_end()
            logger.info(
                "[MedTiming] Session done (detected=%s) — resuming face/voice", detected
            )

    def _run_medscan_subprocess(
        self, medication_id: Optional[str], medication_name: str
    ) -> bool:
        """
        Launch mediscan/main.py and block until it exits or times out.
        Returns True when the process exits by itself (medication detected).
        Returns False on timeout.
        """
        env = os.environ.copy()
        env.setdefault("DISPLAY",         ":0")
        env.setdefault("XAUTHORITY",      os.path.expanduser("~/.Xauthority"))
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        env.setdefault("API_BASE_URL",    API_BASE_URL)

        cmd = [self.python_exe, "-u", _MEDSCAN_MAIN]
        if medication_id:
            cmd += ["--medication-id",   medication_id]
        if medication_name:
            cmd += ["--medication-name", medication_name]
        cmd += ["--patient-id", self.patient_id]

        logger.info("[MedTiming] Launching MediScan: %s", " ".join(cmd))

        try:
            proc = subprocess.Popen(
                cmd,
                env=env,
                cwd=os.path.join(_BASE_DIR, "mediscan"),
                stdout=open("/tmp/medscan_log.txt", "w"),
                stderr=subprocess.STDOUT,
            )
        except Exception as exc:
            logger.error("[MedTiming] Failed to launch MediScan: %s", exc)
            return False

        deadline = time.time() + MEDSCAN_TIMEOUT
        while True:
            ret = proc.poll()
            if ret is not None:
                elapsed = MEDSCAN_TIMEOUT - (deadline - time.time())
                logger.info(
                    "[MedTiming] MediScan exited (code=%d) after %.0fs — medication detected",
                    ret, elapsed,
                )
                return True

            if time.time() >= deadline:
                logger.warning(
                    "[MedTiming] MediScan timed out after %ds", MEDSCAN_TIMEOUT
                )
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
                return False

            time.sleep(2)

    # ── Backend helpers ───────────────────────────────────────────────────────

    def _fetch_active_patient_id(self) -> str:
        """Try to get the logged-in patient's ID from the backend."""
        try:
            resp = requests.get(f"{API_BASE_URL}/users/active-patient", timeout=5)
            resp.raise_for_status()
            pid = resp.json().get("user_id", "")
            if pid:
                logger.info("[MedTiming] Auto-fetched patient_id: %s", pid)
            return pid
        except Exception as exc:
            logger.warning("[MedTiming] Could not fetch active patient: %s", exc)
            return ""

    def _fetch_medications(self) -> list:
        try:
            resp = requests.get(
                f"{API_BASE_URL}/medications/{self.patient_id}", timeout=8
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            logger.info("[MedTiming] Fetched %d medications from backend", len(items))
            return items
        except Exception as exc:
            logger.warning("[MedTiming] Could not fetch medications: %s", exc)
            return []

    def _fetch_backend_mode(self) -> Optional[dict]:
        try:
            resp = requests.get(
                f"{API_BASE_URL}/ml-mode/{self.patient_id}", timeout=4
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def _set_backend_mode_medscan(
        self, medication_id: Optional[str], medication_name: str
    ) -> None:
        try:
            requests.post(
                f"{API_BASE_URL}/ml-mode/{self.patient_id}",
                json={
                    "mode":            "medscan",
                    "medication_id":   medication_id,
                    "medication_name": medication_name,
                },
                timeout=5,
            )
        except Exception as exc:
            logger.debug("[MedTiming] Could not set backend mode: %s", exc)

    def _post_reset_mode(self) -> None:
        try:
            requests.post(
                f"{API_BASE_URL}/ml-mode/{self.patient_id}",
                json={"mode": "face_recognition"},
                timeout=5,
            )
            logger.info("[MedTiming] Backend mode reset → face_recognition")
        except Exception as exc:
            logger.warning("[MedTiming] Could not reset mode: %s", exc)

    def _send_missed_alert(
        self, medication_id: Optional[str], medication_name: str
    ) -> None:
        try:
            requests.post(
                f"{API_BASE_URL}/alerts/medication-missed",
                json={
                    "patient_id":      self.patient_id,
                    "medication_id":   medication_id,
                    "medication_name": medication_name,
                },
                timeout=5,
            )
            logger.info("[MedTiming] Sent medication_missed alert for '%s'", medication_name)
        except Exception as exc:
            logger.warning("[MedTiming] Could not send missed alert: %s", exc)
