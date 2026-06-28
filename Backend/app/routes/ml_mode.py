"""
ML mode control — single source of truth for which ML process the Pi should run.
The Pi coordinator polls GET /ml-mode/{patient_id} every 10 seconds.
The medication scheduler (and the /medscan/detected endpoint) POST here to flip the mode.
"""
from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_db

router = APIRouter(prefix="/ml-mode", tags=["ml"])

_DEFAULT_MODE = "face_recognition"


def _serialize_state(doc: dict) -> dict:
    changed_at = doc.get("mode_changed_at")
    return {
        "patient_id": doc.get("patient_id"),
        "mode": doc.get("mode", _DEFAULT_MODE),
        "pending_medication_id": doc.get("pending_medication_id"),
        "pending_medication_name": doc.get("pending_medication_name"),
        "mode_changed_at": changed_at.isoformat() if isinstance(changed_at, datetime) else None,
    }


@router.get("/{patient_id}")
async def get_ml_mode(patient_id: str):
    """Pi coordinator polls this to know which process to run."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        ObjectId(patient_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="patient_id is invalid") from exc

    doc = await db.system_state.find_one({"patient_id": str(patient_id)})
    if not doc:
        return {
            "patient_id": patient_id,
            "mode": _DEFAULT_MODE,
            "pending_medication_id": None,
            "pending_medication_name": None,
            "mode_changed_at": None,
        }

    return _serialize_state(doc)


class SetModeRequest(BaseModel):
    mode: str
    medication_id: str | None = None
    medication_name: str | None = None


@router.post("/{patient_id}")
async def set_ml_mode(patient_id: str, body: SetModeRequest):
    """Set the active ML mode for a patient (used internally by scheduler/detected endpoint)."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    if body.mode not in ("face_recognition", "medscan"):
        raise HTTPException(
            status_code=400,
            detail="mode must be 'face_recognition' or 'medscan'",
        )

    try:
        ObjectId(patient_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="patient_id is invalid") from exc

    doc = {
        "patient_id": str(patient_id),
        "mode": body.mode,
        "pending_medication_id": body.medication_id,
        "pending_medication_name": body.medication_name,
        "mode_changed_at": datetime.utcnow(),
    }
    await db.system_state.update_one(
        {"patient_id": str(patient_id)},
        {"$set": doc},
        upsert=True,
    )

    return {"message": "Mode updated", "mode": body.mode}
