import os
import sys
import subprocess
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

router = APIRouter(tags=["ml"])

# Track the running coordinator process
_recognizer_process: subprocess.Popen | None = None

# Coordinator manages both face/voice recognition and MediScan mode switching
_COORDINATOR_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),   # .../backend/app/routes
    "..", "..", "..",             # up to project root
    "ML", "coordinator.py"
))


class StartRecognitionRequest(BaseModel):
    user_id: str
    patient_id: str | None = None


@router.post("/start-recognition")
def start_recognition(body: StartRecognitionRequest):
    """
    Launch the ML coordinator for a specific patient.
    The coordinator manages mode switching between face/voice recognition and
    MediScan depending on the system_state stored in MongoDB.
    Called by the mobile app with { user_id: "...", patient_id: "..." }.
    patient_id defaults to user_id when not provided (patient using their own account).
    """
    global _recognizer_process

    user_id = body.user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    # patient_id == user_id for patients; for helpers user_id is the patient ID
    patient_id = (body.patient_id or user_id).strip()

    if not os.path.exists(_COORDINATOR_PATH):
        raise HTTPException(
            status_code=500,
            detail=f"Coordinator script not found at: {_COORDINATOR_PATH}",
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
    env["PATIENT_ID"] = patient_id

    env.setdefault("DISPLAY", ":0")
    env.setdefault("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

    log_file = open("/tmp/recognition_log.txt", "w")
    _recognizer_process = subprocess.Popen(
        [sys.executable, "-u", _COORDINATOR_PATH, user_id, patient_id],
        env=env,
        stdout=log_file,
        stderr=log_file,
    )

    return {
        "status": "started",
        "user_id": user_id,
        "patient_id": patient_id,
        "pid": _recognizer_process.pid,
        "message": "ML coordinator started — face/voice recognition active, MediScan on standby.",
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
