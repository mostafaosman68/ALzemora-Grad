import logging
from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.database import get_db
from app.services.notification_service import get_unread_alerts, mark_alert_as_read

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/{patient_id}")
async def get_patient_alerts(patient_id: str):
    """Get all unread alerts for a patient."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        ObjectId(patient_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="patient_id is invalid") from exc
    
    alerts = await get_unread_alerts(db, patient_id)
    return {
        "patient_id": str(patient_id),
        "count": len(alerts),
        "alerts": alerts,
    }


@router.post("/{alert_id}/read")
async def mark_read(alert_id: str):
    """Mark an alert as read."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    success = await mark_alert_as_read(db, alert_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to mark alert as read")
    
    return {"message": "Alert marked as read"}


class MedicationMissedRequest(BaseModel):
    patient_id: str
    medication_id: Optional[str] = None
    medication_name: Optional[str] = None


@router.post("/medication-missed")
async def medication_missed(body: MedicationMissedRequest):
    """
    Called by the Pi med_timing controller when the MediScan session times out
    without detecting the target medication.  Creates a medication_missed alert
    in the database and pushes an FCM notification to the patient's helpers.
    """
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        ObjectId(body.patient_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="patient_id is invalid") from exc

    now = datetime.utcnow()
    med_name = body.medication_name or "medication"

    # 1. Create medication_missed alert
    alert_doc = {
        "patient_id":      body.patient_id,
        "alert_type":      "medication_missed",
        "medication_id":   body.medication_id,
        "medication_name": med_name,
        "message":         f"Medication not detected: {med_name}",
        "created_at":      now,
        "read":            False,
    }
    result = await db.alerts.insert_one(alert_doc)
    alert_id = str(result.inserted_id)

    # 2. Push FCM notification to patient + helpers
    try:
        from app.services.heartbeat_service import find_notifiable_helpers
        from app.services.firebase_service import send_push_notification

        title      = "Medication Not Taken"
        notif_body = f"Camera did not detect {med_name} — please check on the patient"
        data       = {
            "alert_type":      "medication_missed",
            "alert_id":        alert_id,
            "patient_id":      body.patient_id,
            "medication_name": med_name,
        }

        # Patient token
        try:
            patient = await db.users.find_one({"_id": ObjectId(body.patient_id)})
            if patient and patient.get("fcm_token"):
                await send_push_notification(patient["fcm_token"], title, notif_body, data, priority="high")
        except Exception as exc:
            logger.warning("[MISSED] Patient FCM failed: %s", exc)

        # Helper tokens
        helpers = await find_notifiable_helpers(db, body.patient_id)
        for helper in helpers:
            helper_id = helper.get("helper_id")
            if not helper_id:
                continue
            helper_doc = await db.users.find_one({"_id": ObjectId(helper_id)})
            if helper_doc and helper_doc.get("fcm_token"):
                try:
                    await send_push_notification(
                        helper_doc["fcm_token"], title, notif_body, data, priority="high"
                    )
                except Exception as exc:
                    logger.warning("[MISSED] Helper FCM failed: %s", exc)

    except Exception as exc:
        logger.error("[MISSED] Notification error: %s", exc)

    return {
        "message":         "medication_missed alert created",
        "alert_id":        alert_id,
        "medication_name": med_name,
    }


@router.post("/{patient_id}/clear-all")
async def clear_all_alerts(patient_id: str):
    """Clear all unread alerts for a patient."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        ObjectId(patient_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="patient_id is invalid") from exc
    
    alerts_collection = getattr(db, "alerts", None)
    if alerts_collection is None:
        raise HTTPException(status_code=500, detail="Alerts collection not available")
    
    result = await alerts_collection.update_many(
        {"patient_id": str(patient_id), "read": False},
        {"$set": {"read": True, "read_at": __import__("datetime").datetime.utcnow()}},
    )
    
    return {
        "message": f"Cleared {result.modified_count} alerts",
        "cleared_count": result.modified_count,
    }
