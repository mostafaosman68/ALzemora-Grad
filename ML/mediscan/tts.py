"""
Text-to-speech.
Priority: Piper (neural, natural) → espeak-ng/espeak (robotic fallback)
"""

import json
import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Piper binary + voice model live in ML/piper/
_MEDISCAN_DIR = Path(__file__).resolve().parent          # ML/mediscan/
_ML_DIR       = _MEDISCAN_DIR.parent                     # ML/
PIPER_DIR     = _ML_DIR / "piper"
PIPER_BIN     = str(PIPER_DIR / "piper")
PIPER_MODEL   = str(PIPER_DIR / "voices" / "en_US-lessac-medium.onnx")


def _make_safe_text(text: str) -> str:
    return text.replace('"', "").replace("'", "").replace(";", "")


def _read_sample_rate(model_path: str) -> int:
    try:
        with open(model_path + ".json") as f:
            return int(json.load(f).get("audio", {}).get("sample_rate", 22050))
    except Exception:
        return 22050


def _piper_env() -> dict:
    """Build env with LD_LIBRARY_PATH and ESPEAK_DATA_PATH so piper finds its bundled libs."""
    env = os.environ.copy()
    lib_path = str(PIPER_DIR)
    existing = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = f"{lib_path}:{existing}" if existing else lib_path
    env["ESPEAK_DATA_PATH"] = str(PIPER_DIR / "espeak-ng-data")
    return env


class SpeechEngine:
    def __init__(self) -> None:
        self._lock  = threading.Lock()
        self._procs: list[subprocess.Popen] = []
        self._use_piper = os.path.isfile(PIPER_BIN) and os.path.isfile(PIPER_MODEL)
        self._sample_rate = _read_sample_rate(PIPER_MODEL) if self._use_piper else 22050

        if self._use_piper:
            logger.info("TTS: Piper neural voice (%s, %d Hz)", PIPER_MODEL, self._sample_rate)
        else:
            logger.warning(
                "TTS: Piper not found at %s or model missing at %s — using espeak fallback",
                PIPER_BIN, PIPER_MODEL,
            )

    def speak(self, text: str) -> None:
        """Non-blocking: kills any current speech then starts new synthesis in background."""
        safe = _make_safe_text(text)
        threading.Thread(target=self._do_speak, args=(safe,), daemon=True).start()

    def stop(self) -> None:
        self._kill_current()

    # ── internals ────────────────────────────────────────────────────────────

    def _do_speak(self, text: str) -> None:
        self._kill_current()
        if self._use_piper:
            self._speak_piper(text)
        else:
            self._speak_espeak(text)

    def _speak_piper(self, text: str) -> None:
        try:
            env = _piper_env()
            piper_cmd = [PIPER_BIN, "--model", PIPER_MODEL, "--output_raw", "--quiet"]
            aplay_cmd = ["aplay", "-D", "pulse", "-r", str(self._sample_rate), "-f", "S16_LE", "-t", "raw", "-q", "-"]

            piper = subprocess.Popen(
                piper_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            aplay = subprocess.Popen(
                aplay_cmd,
                stdin=piper.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            piper.stdout.close()  # hand ownership of the read-end to aplay

            with self._lock:
                self._procs = [piper, aplay]

            try:
                piper.stdin.write(text.encode())
                piper.stdin.close()
            except BrokenPipeError:
                pass

        except Exception as exc:
            logger.error("Piper TTS failed: %s", exc)

    def _speak_espeak(self, text: str) -> None:
        espeak_bin = shutil.which("espeak-ng") or shutil.which("espeak")
        if espeak_bin is None:
            logger.error("No TTS engine available")
            print(f"[TTS] {text}")
            return
        cmd = [espeak_bin, "-v", "en-us", "-s", "115", "-p", "52", "-g", "12", "-a", "180", text]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with self._lock:
                self._procs = [proc]
        except Exception as exc:
            logger.error("espeak launch failed: %s", exc)

    def _kill_current(self) -> None:
        with self._lock:
            procs, self._procs = self._procs, []
        for proc in procs:
            if proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    pass
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass
