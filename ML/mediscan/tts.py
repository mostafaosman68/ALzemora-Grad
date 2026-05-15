"""
Text-to-speech via Windows PowerShell SAPI.
Reliable on all Windows versions — no pip package, no COM threading issues.
"""

import logging
import subprocess
import threading

logger = logging.getLogger(__name__)

_CREATION_FLAGS = 0x08000000  # CREATE_NO_WINDOW


class SpeechEngine:
    def __init__(self, rate: int = 1) -> None:
        """rate: -10 (slow) to 10 (fast), 0 = default, 1 = slightly faster"""
        self._rate = rate
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None

    def speak(self, text: str) -> None:
        """Speak text. Interrupts any currently playing speech."""
        safe = text.replace('"', "").replace("'", "").replace(";", "")
        self._kill_current()
        cmd = [
            "powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-Command",
            (
                f"Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Rate = {self._rate}; "
                f'$s.Speak("{safe}");'
            ),
        ]
        try:
            with self._lock:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=_CREATION_FLAGS,
                )
        except Exception as exc:
            logger.error("TTS launch failed: %s", exc)

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
