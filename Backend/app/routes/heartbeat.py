from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId

from app.database import get_db
from app.services.heartbeat_bridge_service import set_active_heartbeat_patient
from app.services.heartbeat_service import (
    evaluate_heartbeat,
    get_latest_heartbeat_state,
    record_heartbeat_sample,
)

from app.services.notification_service import send_alert_notification

router = APIRouter(prefix="/heartbeat", tags=["heartbeat"])


def _serialize_for_json(obj):
    """Convert ObjectIds and datetime objects to JSON-serializable types."""
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    elif hasattr(obj, 'isoformat'):
        return obj.isoformat()
    return obj

@router.post("/check")
async def check_heartbeat(request: Request):
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection failed")

        body = await request.json()
        patient_id = body.get("patient_id")
        heart_rate = body.get("heart_rate")
        threshold = body.get("threshold")

        if not patient_id:
            raise HTTPException(status_code=400, detail="patient_id is required")

        if heart_rate is None:
            raise HTTPException(status_code=400, detail="heart_rate is required")

        try:
            heart_rate = int(heart_rate)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="heart_rate must be a number") from exc

        if threshold is not None:
            try:
                threshold = int(threshold)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="threshold must be a number") from exc

        result = await record_heartbeat_sample(
            db,
            patient_id=str(patient_id),
            heart_rate=heart_rate,
            threshold=threshold,
            source="manual_check",
        )

        result = _serialize_for_json(result)

        if result["alert_triggered"]:
            return {
                "status": "alert_triggered",
                "message": "Heart rate exceeded the configured threshold",
                **result,
            }

        return {
            "status": "normal",
            "message": "Heart rate is within the safe range",
            **result,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Heartbeat check failed: {str(exc)}") from exc


@router.post("/report")
async def report_heartbeat(request: Request):
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection failed")

        body = await request.json()
        patient_id = body.get("patient_id")
        heart_rate = body.get("heart_rate")
        threshold = body.get("threshold")

        if not patient_id:
            raise HTTPException(status_code=400, detail="patient_id is required")

        if heart_rate is None:
            raise HTTPException(status_code=400, detail="heart_rate is required")

        try:
            heart_rate = int(heart_rate)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="heart_rate must be a number") from exc

        if threshold is not None:
            try:
                threshold = int(threshold)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="threshold must be a number") from exc

        result = await record_heartbeat_sample(
            db,
            patient_id=str(patient_id),
            heart_rate=heart_rate,
            threshold=threshold,
            source=body.get("source") or "sensor",
        )

        result = _serialize_for_json(result)

        if result["alert_triggered"]:
            # Send alert notification
            await send_alert_notification(
                db,
                patient_id=str(patient_id),
                alert_type="high_heart_rate",
                heart_rate=heart_rate,
                threshold=result["threshold"],
                message=f"High heart rate alert: {heart_rate} BPM (threshold: {result['threshold']} BPM)"
            )
            
            return {
                "status": "alert_triggered",
                "message": "Heart rate exceeded the configured threshold",
                **result,
            }

        return {
            "status": "live",
            "message": "Heartbeat reading recorded",
            **result,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Heartbeat report failed: {str(exc)}") from exc


@router.get("/live/{patient_id}")
async def live_heartbeat(patient_id: str):
    try:
        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection failed")

        result = await get_latest_heartbeat_state(db, patient_id)
        # Convert ObjectIds to strings for JSON serialization
        result = _serialize_for_json(result)
        return {
            "message": "Heartbeat state fetched",
            **result,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load live heartbeat: {str(exc)}") from exc


@router.post("/bridge/active-patient")
async def set_active_bridge_patient(request: Request):
    try:
        body = await request.json()
        patient_id = body.get("patient_id")

        result = await set_active_heartbeat_patient(
            patient_id=patient_id,
            backend_url=body.get("backend_url") or "http://127.0.0.1:8000",
            device_name=body.get("device_name") or "Polar H10",
            device_address=body.get("device_address") or "",
            threshold=int(body.get("threshold") or 90),
            source=body.get("source") or "polar_h10",
            scan_timeout=float(body.get("scan_timeout") or 10.0),
        )

        return result

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to set active bridge patient: {str(exc)}") from exc