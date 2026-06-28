import logging
from datetime import datetime
from typing import Optional

from app.services.firebase_service import send_push_notification

logger = logging.getLogger(__name__)


async def send_alert_notification(
    db,
    patient_id: str,
    alert_type: str,
    heart_rate: int,
    threshold: int,
    message: Optional[str] = None,
) -> bool:
    """
    Send an alert notification to the patient's device via push notification.
    Also records the alert in the database for history.
    
    Args:
        db: Database connection
        patient_id: Patient's MongoDB ID
        alert_type: Type of alert (e.g., 'high_heart_rate')
        heart_rate: Current heart rate reading
        threshold: Threshold that was exceeded
        message: Custom message (optional)
        
    Returns:
        bool: True if notification was sent successfully
    """
    if not patient_id:
        logger.warning("[NOTIFICATION] patient_id not provided")
        return False
    
    try:
        alerts_collection = getattr(db, "alerts", None)
        if alerts_collection is None:
            logger.warning("[NOTIFICATION] alerts collection not available")
            return False
        
        default_message = message or f"Heart rate {heart_rate} BPM exceeded threshold of {threshold} BPM"
        
        alert_doc = {
            "patient_id": str(patient_id),
            "alert_type": alert_type,
            "heart_rate": heart_rate,
            "threshold": threshold,
            "message": default_message,
            "created_at": datetime.utcnow(),
            "read": False,
        }
        
        # Store alert in database
        result = await alerts_collection.insert_one(alert_doc)
        if not result.inserted_id:
            logger.warning("[NOTIFICATION] Failed to store alert in DB")
            return False
        
        # Get patient's FCM token
        users_collection = getattr(db, "users", None)
        if users_collection is None:
            logger.warning("[NOTIFICATION] users collection not available")
            return False
        
        from bson import ObjectId
        patient = await users_collection.find_one({"_id": ObjectId(patient_id)})
        if not patient or not patient.get("fcm_token"):
            logger.warning(f"[NOTIFICATION] No FCM token for patient {patient_id}")
            return False
        
        fcm_token = patient.get("fcm_token")
        
        # Send push notification
        notification_title = "⚠️ Heart Rate Alert"
        notification_body = f"BPM: {heart_rate} (Threshold: {threshold})"
        
        push_sent = await send_push_notification(
            fcm_token=fcm_token,
            title=notification_title,
            body=notification_body,
            data={
                "alert_id": str(result.inserted_id),
                "patient_id": str(patient_id),
                "heart_rate": str(heart_rate),
                "threshold": str(threshold),
                "alert_type": alert_type,
            },
            priority="high",
        )
        
        if push_sent:
            logger.info(f"[NOTIFICATION] Push notification sent to patient {patient_id}: BPM={heart_rate}, threshold={threshold}")
        
        return push_sent
        
    except Exception as exc:
        logger.error(f"[NOTIFICATION] Failed to send alert: {exc}")
        return False


async def get_unread_alerts(db, patient_id: str) -> list:
    """
    Get all unread alerts for a patient.
    """
    try:
        alerts_collection = getattr(db, "alerts", None)
        if alerts_collection is None:
            return []
        
        alerts = []
        cursor = alerts_collection.find(
            {"patient_id": str(patient_id), "read": False}
        ).sort("created_at", -1)
        
        async for doc in cursor:
            doc["_id"] = str(doc.get("_id"))
            alerts.append(doc)
        
        return alerts
        
    except Exception as exc:
        logger.error(f"[NOTIFICATION] Failed to fetch alerts: {exc}")
        return []


async def mark_alert_as_read(db, alert_id: str) -> bool:
    """
    Mark an alert as read.
    """
    try:
        from bson import ObjectId
        
        alerts_collection = getattr(db, "alerts", None)
        if alerts_collection is None:
            return False
        
        result = await alerts_collection.update_one(
            {"_id": ObjectId(alert_id)},
            {"$set": {"read": True, "read_at": datetime.utcnow()}}
        )
        
        return result.modified_count > 0
        
    except Exception as exc:
        logger.error(f"[NOTIFICATION] Failed to mark alert as read: {exc}")
        return False
