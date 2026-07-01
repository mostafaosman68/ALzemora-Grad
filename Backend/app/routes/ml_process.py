import os
import sys
import subprocess
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

router = APIRouter(tags=["ml"])

# Track the running recognizer process
_recognizer_process: subprocess.Popen | None = None

# user_aware_recognizer loads only the people linked to a specific patient
_ML_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__),   # .../backend/app/routes
    "..", "..", "..",             # up to project root
    "ML",
))
_RECOGNIZER_SCRIPT = os.path.join(_ML_DIR, "user_aware_recognizer.py")


class StartRecognitionRequest(BaseModel):
    user_id: str


@router.post("/start-recognition")
def start_recognition(body: StartRecognitionRequest):
    """
    Launch user_aware_recognizer.py for a specific patient.
    Called by the mobile app with { user_id: "..." }.
    Note: on the Pi the primary controller is main_ai.py (GPIO-based).
    This endpoint is used when triggering recognition directly from the app.
    """
    global _recognizer_process

    user_id = body.user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    if not os.path.exists(_RECOGNIZER_SCRIPT):
        raise HTTPException(
            status_code=500,
            detail=f"ML script not found at: {_RECOGNIZER_SCRIPT}",
        )

    # If a process is already running, stop it first
    if _recognizer_process is not None and _recognizer_process.poll() is None:
        _recognizer_process.terminate()
        try:
            _recognizer_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _recognizer_process.kill()

    env = os.environ.copy()
    env["USER_ID_FOR_RECOGNITION"] = user_id
    env["PATIENT_ID"] = user_id   # for mode polling inside user_aware_recognizer

    env.setdefault("DISPLAY", ":0")
    env.setdefault("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

    log_file = open("/tmp/recognition_log.txt", "w")
    _recognizer_process = subprocess.Popen(
        [sys.executable, "-u", _RECOGNIZER_SCRIPT, user_id],
        env=env,
        stdout=log_file,
        stderr=log_file,
    )

    return {
        "status": "started",
        "user_id": user_id,
        "pid": _recognizer_process.pid,
        "message": "Face and voice recognition has been started.",
        "people_count": 0,
    }


@router.post("/stop-recognition")
def stop_recognition():
    """Stop the currently running recognizer process."""
    global _recognizer_process

    if _recognizer_process is None or _recognizer_process.poll() is not None:
        return {"status": "not_running"}

    _recognizer_process.terminate()
    _recognizer_process.wait(timeout=5)
    _recognizer_process = None

    return {"status": "stopped"}


@router.get("/recognition-status")
def recognition_status():
    """Check whether the recognizer process is currently running."""
    global _recognizer_process

    if _recognizer_process is None:
        return {"status": "not_started"}

    poll = _recognizer_process.poll()
    if poll is None:
        return {"status": "running", "pid": _recognizer_process.pid}

    return {"status": "exited", "exit_code": poll}


_FRAME_PATH = "/tmp/recognition_frame.jpg"


@router.get("/latest-frame")
def latest_frame():
    """Return the most recent annotated frame written by the recognizer."""
    if not os.path.exists(_FRAME_PATH):
        raise HTTPException(status_code=404, detail="No frame available yet")
    with open(_FRAME_PATH, "rb") as f:
        data = f.read()
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )
