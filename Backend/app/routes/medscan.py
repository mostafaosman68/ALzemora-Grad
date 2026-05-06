from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
import re

from bson import ObjectId
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.database import get_db
from app.services.medscan_service import MedScanAnalyzer, get_medicine_catalog

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