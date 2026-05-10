from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId

from app.database import get_db
from app.services.notification_service import get_unread_alerts, mark_alert_as_read

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
