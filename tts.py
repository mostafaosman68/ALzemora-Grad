"""
Text-to-speech with Linux/macOS support.
Uses espeak-ng/espeak when available, or falls back to pyttsx3.
"""

import logging
import subprocess
import threading
import shutil

logger = logging.getLogger(__name__)


def _make_safe_text(text: str) -> str:
    return text.replace('"', "").replace("'", "").replace(";", "")


class SpeechEngine:
    def __init__(self, rate: int = 1) -> None:
        """rate: -10 (slow) to 10 (fast), 0 = default, 1 = slightly faster"""
        self._rate = rate
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None

    def speak(self, text: str) -> None:
        """Speak text. Interrupts any currently playing speech."""
        safe = _make_safe_text(text)
        self._kill_current()

        # Try espeak-ng first, then espeak as fallback
        espeak_bin = shutil.which("espeak-ng") or shutil.which("espeak")

        if espeak_bin is not None:
            cmd = [
                espeak_bin,
                "-v", "en-gb",   # clearest available English voice
                "-s", "130",     # slower pace (default 175 is too fast/robotic)
                "-p", "40",      # slightly lower pitch
                "-g", "6",       # gap between words (ms) for natural rhythm
                "-a", "100",     # amplitude
                safe,
            ]
            try:
                with self._lock:
                    self._proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                return
            except Exception as exc:
                logger.error("espeak launch failed: %s", exc)

        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 150 + self._rate * 10)
            engine.say(safe)
            engine.runAndWait()
        except Exception as exc:
            logger.error("TTS fallback failed: %s", exc)
            print(f"[TTS] {safe}")

    def stop(self) -> None:
        self._kill_current()

    def _kill_current(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.kill()
                except OSError:
                    pass
            self._proc = None