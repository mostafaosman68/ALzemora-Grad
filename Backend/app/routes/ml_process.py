import os
import sys
import subprocess
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["ml"])

# Track the running recognizer process
_recognizer_process: subprocess.Popen | None = None

ML_SCRIPT_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),   # .../backend/app/routes
    "..", "..", "..",             # up to project root
    "ML", "user_aware_recognizer.py"
))


class StartRecognitionRequest(BaseModel):
    user_id: str


@router.post("/start-recognition")
def start_recognition(body: StartRecognitionRequest):
    """
    Launch user_aware_recognizer.py for a specific user.
    Called by the mobile app with { user_id: "..." } in the request body.
    The user_id is injected into the subprocess via USER_ID_FOR_RECOGNITION env var.
    """
    global _recognizer_process

    user_id = body.user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    if not os.path.exists(ML_SCRIPT_PATH):
        raise HTTPException(
            status_code=500,
            detail=f"ML script not found at: {ML_SCRIPT_PATH}"
        )

    # If a process is already running, stop it first
    if _recognizer_process is not None and _recognizer_process.poll() is None:
        _recognizer_process.terminate()
        _recognizer_process.wait(timeout=5)

    env = os.environ.copy()
    env["USER_ID_FOR_RECOGNITION"] = user_id

    _recognizer_process = subprocess.Popen(
        [sys.executable, ML_SCRIPT_PATH],
        env=env,
    )

    return {
        "status": "started",
        "user_id": user_id,
        "pid": _recognizer_process.pid,
        "message": "Face and voice recognition has been started.",
        "instructions": "Open the camera window on your laptop.",
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
