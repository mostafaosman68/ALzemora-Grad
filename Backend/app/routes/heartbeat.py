from fastapi import APIRouter, HTTPException, Request

from app.database import get_db
from app.services.heartbeat_service import (
    evaluate_heartbeat,
    get_latest_heartbeat_state,
    record_heartbeat_sample,
)

router = APIRouter(prefix="/heartbeat", tags=["heartbeat"])


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

        if result["alert_triggered"]:
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
        return {
            "message": "Heartbeat state fetched",
            **result,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load live heartbeat: {str(exc)}") from exc