from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
import re
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.database import get_db
from app.services.medscan_service import MedScanAnalyzer, get_medicine_catalog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/medscan", tags=["medscan"])

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BASE_DIR.parent
TEMP_DIR = PROJECT_ROOT / "data" / "temp_medscan"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def _serialize_detection_event(document: dict) -> dict:
    payload = {**document}
    payload["_id"] = str(payload.get("_id")) if payload.get("_id") is not None else None
    created_at = payload.get("created_at")
    if isinstance(created_at, datetime):
        payload["created_at"] = created_at.isoformat()
    detections = []
    for detection in payload.get("detections", []) or []:
        det = dict(detection)
        if isinstance(det.get("bbox"), tuple):
            det["bbox"] = list(det["bbox"])
        detections.append(det)
    payload["detections"] = detections
    return payload


def _normalize_medicine_key(value: str | None) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip())
    cleaned = cleaned.strip("_")
    return cleaned.lower() or "unknown"


async def _get_patient_reference_images(db, patient_id: str) -> list[tuple[str, str]]:
    reference_images: list[tuple[str, str]] = []
    cursor = db.medications.find({"patient_id": str(patient_id)}).sort("created_at", -1)

    async for medication in cursor:
        key = _normalize_medicine_key(medication.get("name") or medication.get("medication_name"))
        paths = []
        photo_urls = medication.get("photo_urls") or []
        if isinstance(photo_urls, list):
            paths.extend(photo_urls)
        photo_url = medication.get("photo_url")
        if photo_url:
            paths.append(photo_url)

        for raw_path in paths:
            path = Path(raw_path)
            if path.exists():
                reference_images.append((key, str(path)))

    return reference_images


@router.get("/catalog")
async def medicine_catalog():
    medicines = get_medicine_catalog()
    return {"count": len(medicines), "medicines": medicines}


@router.post("/scan")
async def scan_medicine(
    patient_id: str = Form(...),
    actor_user_id: str = Form(None),
    actor_role: str = Form(None),
    image_file: UploadFile = File(...),
):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        patient_object_id = ObjectId(patient_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="patient_id is invalid") from exc

    patient = await db.users.find_one({"_id": patient_object_id})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient account not found")

    reference_images = await _get_patient_reference_images(db, str(patient_id))
    if not reference_images:
        raise HTTPException(
            status_code=404,
            detail="No stored medication photos found for this patient",
        )

    analyzer = MedScanAnalyzer(reference_images=reference_images)

    safe_name = Path(image_file.filename or "scan.jpg").name
    temp_path = TEMP_DIR / f"{patient_id}_{safe_name}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(image_file.file, buffer)

    try:
        analysis = analyzer.analyze(str(temp_path))
        if analysis.get("status") == "error":
            raise HTTPException(status_code=400, detail=analysis.get("error") or "Unable to analyze image")

        detections = analysis.get("detections") or []
        primary = analysis.get("primary_detection") or {}

        event = {
            "patient_id": str(patient_id),
            "actor_user_id": actor_user_id,
            "actor_role": actor_role,
            "image_name": safe_name,
            "image_path": str(temp_path),
            "status": analysis.get("status", "no_match"),
            "ocr_text": analysis.get("ocr_text"),
            "primary_medicine_key": primary.get("medicine_key"),
            "primary_medicine_name": primary.get("name"),
            "primary_confidence": primary.get("confidence", 0.0),
            "detections": detections,
            "summary_text": analysis.get("summary_text"),
            "created_at": datetime.utcnow(),
        }

        result = await db.medscan_events.insert_one(event)
        event["_id"] = result.inserted_id

        return {
            "message": "Medicine scan completed",
            "event": _serialize_detection_event(event),
        }
    finally:
        temp_path.unlink(missing_ok=True)


class MedDetectedRequest(BaseModel):
    patient_id: str
    medication_id: Optional[str] = None
    medication_name: Optional[str] = None
    confidence: float = 0.0


@router.post("/detected")
async def medication_detected(body: MedDetectedRequest):
    """
    Called by the Pi MediScan process when a target medication is confirmed.
    Resets system mode back to face_recognition, marks the pending alert as
    read, logs the medication event, and notifies helpers that the med was taken.
    """
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        ObjectId(body.patient_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="patient_id is invalid") from exc

    now = datetime.utcnow()

    # 1. Reset system mode → face_recognition
    await db.system_state.update_one(
        {"patient_id": body.patient_id},
        {
            "$set": {
                "mode": "face_recognition",
                "pending_medication_id": None,
                "pending_medication_name": None,
                "mode_changed_at": now,
            }
        },
        upsert=True,
    )

    # 2. Mark the pending medication_due alert as read
    alert_filter: dict = {"patient_id": body.patient_id, "alert_type": "medication_due", "read": False}
    if body.medication_id:
        alert_filter["medication_id"] = body.medication_id
    await db.alerts.update_many(
        alert_filter,
        {"$set": {"read": True, "read_at": now}},
    )

    # 3. Log medication taken event
    event = {
        "patient_id": body.patient_id,
        "medication_id": body.medication_id,
        "medication_name": body.medication_name,
        "detection_method": "medscan",
        "confidence": body.confidence,
        "created_at": now,
    }
    await db.medication_events.insert_one(event)

    # 4. Notify helpers that the medication was taken
    try:
        from app.services.heartbeat_service import find_notifiable_helpers
        from app.services.firebase_service import send_push_notification

        med_name = body.medication_name or "medication"
        title = "Medication Confirmed"
        notif_body = f"Patient took {med_name} — detected by camera"
        data = {
            "alert_type": "medication_taken",
            "patient_id": body.patient_id,
            "medication_name": med_name,
        }

        helpers = await find_notifiable_helpers(db, body.patient_id)
        for helper in helpers:
            helper_id = helper.get("helper_id")
            if not helper_id:
                continue
            helper_doc = await db.users.find_one({"_id": ObjectId(helper_id)})
            if helper_doc and helper_doc.get("fcm_token"):
                await send_push_notification(helper_doc["fcm_token"], title, notif_body, data)
    except Exception as exc:
        logger.warning("[MEDSCAN] Failed to send helper notification: %s", exc)

    return {
        "message": "Medication detected — mode reset to face_recognition",
        "patient_id": body.patient_id,
        "medication_name": body.medication_name,
    }


@router.get("/history/{patient_id}")
async def scan_history(patient_id: str, limit: int = 20):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        ObjectId(patient_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="patient_id is invalid") from exc

    cursor = (
        db.medscan_events
        .find({"patient_id": str(patient_id)})
        .sort("created_at", -1)
        .limit(max(1, min(int(limit), 50)))
    )

    items = []
    async for document in cursor:
        items.append(_serialize_detection_event(document))

    return {
        "patient_id": str(patient_id),
        "count": len(items),
        "items": items,
    }