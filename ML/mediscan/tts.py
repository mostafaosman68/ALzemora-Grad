"""
Text-to-speech.
Priority: Piper (neural, natural) → espeak-ng/espeak (robotic fallback)
"""

import logging
import os
import subprocess
import threading
import shutil

logger = logging.getLogger(__name__)

PIPER_BIN   = os.path.expanduser("~/piper/piper")
PIPER_MODEL = os.path.expanduser("~/piper/voices/en_US-lessac-medium.onnx")


def _make_safe_text(text: str) -> str:
    return text.replace('"', "").replace("'", "").replace(";", "")


class SpeechEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._use_piper = os.path.isfile(PIPER_BIN) and os.path.isfile(PIPER_MODEL)
        if self._use_piper:
            logger.info("TTS: Piper neural voice (%s)", PIPER_MODEL)
        else:
            logger.warning("TTS: Piper not found — using espeak fallback")

    def speak(self, text: str) -> None:
        safe = _make_safe_text(text)
        self._kill_current()

        if self._use_piper:
            self._speak_piper(safe)
        else:
            self._speak_espeak(safe)

    def stop(self) -> None:
        self._kill_current()

    def _speak_piper(self, text: str) -> None:
        try:
            echo = subprocess.Popen(["echo", text], stdout=subprocess.PIPE)
            aplay_cmd = ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-q", "-"]
            piper_cmd = [PIPER_BIN, "--model", PIPER_MODEL, "--output_raw", "--quiet"]
            piper = subprocess.Popen(
                piper_cmd,
                stdin=echo.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            echo.stdout.close()
            with self._lock:
                self._proc = subprocess.Popen(
                    aplay_cmd,
                    stdin=piper.stdout,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            piper.stdout.close()
        except Exception as exc:
            logger.error("Piper TTS failed: %s", exc)

    def _speak_espeak(self, text: str) -> None:
        espeak_bin = shutil.which("espeak-ng") or shutil.which("espeak")
        if espeak_bin is None:
            logger.error("No TTS engine available")
            print(f"[TTS] {text}")
            return
        cmd = [
            espeak_bin,
            "-v", "en-us",
            "-s", "115",
            "-p", "52",
            "-g", "12",
            "-a", "180",
            text,
        ]
        try:
            with self._lock:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception as exc:
            logger.error("espeak launch failed: %s", exc)

    def _kill_current(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.kill()
                except OSError:
                    pass
            self._proc = None
