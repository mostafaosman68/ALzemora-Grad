from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import logging

logger = logging.getLogger(__name__)

from bson import ObjectId
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.database import get_db

router = APIRouter(prefix="/medications", tags=["medications"])

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BASE_DIR.parent
MEDICATIONS_DIR = PROJECT_ROOT / "data" / "medications"
MEDICATIONS_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "unknown"


def _serialize_medication(document: dict) -> dict:
    payload = {**document}
    payload["_id"] = str(payload.get("_id")) if payload.get("_id") is not None else None

    for key in ("created_at", "updated_at"):
        value = payload.get(key)
        if isinstance(value, datetime):
            payload[key] = value.isoformat()

    return payload


def _extract_ocr_text(image_path: str) -> Optional[str]:
    try:
        import easyocr  # type: ignore

        reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        # readtext returns list of (bbox, text, confidence)
        results = reader.readtext(image_path, detail=1, paragraph=False, rotation_info=[90, 180, 270])
        words = [t.lower() for (_, t, conf) in results if conf >= 0.4 and t and len(t.strip()) >= 2]
        if not words:
            return None
        return " ".join(words)
    except Exception as exc:
        logger.info("OCR disabled or failed for %s: %s", image_path, exc)
        return None


@router.post("/add")
async def add_medication(
    patient_id: str = Form(...),
    name: str = Form(...),
    description: str = Form(None),
    schedule: str = Form(None),
    actor_user_id: str = Form(None),
    actor_role: str = Form(None),
    image_files: List[UploadFile] = File(...),
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

    cleaned_name = _sanitize_name(name)
    medication_folder = MEDICATIONS_DIR / str(patient_id) / cleaned_name
    medication_folder.mkdir(parents=True, exist_ok=True)

    saved_files: list[str] = []
    try:
        for index, upload in enumerate(image_files, start=1):
            if not upload or not upload.filename:
                continue

            safe_filename = Path(upload.filename).name
            suffix = Path(safe_filename).suffix or ".jpg"
            target_path = medication_folder / f"{index}_{cleaned_name}{suffix}"
            with open(target_path, "wb") as buffer:
                shutil.copyfileobj(upload.file, buffer)
            saved_files.append(str(target_path))
    finally:
        for upload in image_files:
            try:
                await upload.close()
            except Exception:
                pass

    if not saved_files:
        raise HTTPException(status_code=400, detail="At least one medication image is required")

    parsed_schedule: Optional[dict | str]
    if schedule:
        try:
            parsed_schedule = json.loads(schedule)
        except Exception:
            parsed_schedule = schedule
    else:
        parsed_schedule = None

    medication_doc = {
        "patient_id": str(patient_id),
        "name": name.strip(),
        "description": description.strip() if isinstance(description, str) and description.strip() else None,
        "schedule": parsed_schedule,
        "photo_url": saved_files[0],
        "photo_urls": saved_files,
        "created_by_user_id": actor_user_id,
        "created_by_role": actor_role,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    # Attempt OCR on the primary image (if EasyOCR is available)
    try:
        ocr_text = _extract_ocr_text(saved_files[0])
        if ocr_text:
            medication_doc["ocr_text"] = ocr_text
    except Exception as exc:
        logger.info("Failed OCR for medication image %s: %s", saved_files[0], exc)

    result = await db.medications.insert_one(medication_doc)
    medication_doc["_id"] = result.inserted_id

    return {
        "message": "Medication saved successfully",
        "medication": _serialize_medication(medication_doc),
    }


@router.get("/{patient_id}")
async def list_medications(patient_id: str):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        ObjectId(patient_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="patient_id is invalid") from exc

    items = []
    cursor = db.medications.find({"patient_id": str(patient_id)}).sort("created_at", -1)
    async for document in cursor:
        items.append(_serialize_medication(document))

    return {
        "patient_id": str(patient_id),
        "count": len(items),
        "items": items,
    }


@router.post("/give")
async def record_medication_given(
    patient_id: str = Form(...),
    medication_id: str = Form(None),
    medication_name: str = Form(None),
    actor_user_id: str = Form(None),
    actor_role: str = Form(None),
    image_file: UploadFile = File(...),
):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        ObjectId(patient_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="patient_id is invalid") from exc

    # ensure patient exists
    patient = await db.users.find_one({"_id": ObjectId(patient_id)})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient account not found")

    # store image under given/ folder with timestamp
    cleaned_med = _sanitize_name(medication_name or (medication_id or "medication"))
    given_folder = MEDICATIONS_DIR / str(patient_id) / cleaned_med / "given"
    given_folder.mkdir(parents=True, exist_ok=True)

    safe_filename = Path(image_file.filename or "given.jpg").name
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    target_path = given_folder / f"{timestamp}_{safe_filename}"

    try:
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(image_file.file, buffer)
    finally:
        try:
            await image_file.close()
        except Exception:
            pass

    event = {
        "patient_id": str(patient_id),
        "medication_id": medication_id,
        "medication_name": medication_name,
        "image_path": str(target_path),
        "actor_user_id": actor_user_id,
        "actor_role": actor_role,
        "created_at": datetime.utcnow(),
    }
    # Run OCR on the given image if available
    try:
        ocr_text = _extract_ocr_text(str(target_path))
        if ocr_text:
            event["ocr_text"] = ocr_text
    except Exception as exc:
        logger.info("Failed OCR for given image %s: %s", target_path, exc)

    result = await db.medication_events.insert_one(event)
    event["_id"] = result.inserted_id

    return {"message": "Recorded medication given", "event": _serialize_medication(event)}


@router.post("/detect")
async def detect_medication(image_file: UploadFile = File(...)):
    """
    Detect medication from uploaded image using OCR and/or ORB-based matching.
    Returns the detected medication name and confidence score.
    """
    import tempfile
    import uuid

    if not image_file or not image_file.filename:
        raise HTTPException(status_code=400, detail="No image file provided")

    detected_name = None
    confidence = 0.0

    try:
        # Save uploaded image to temp file
        temp_id = str(uuid.uuid4())
        temp_dir = Path(tempfile.gettempdir()) / "medscan_detect"
        temp_dir.mkdir(exist_ok=True)
        temp_path = temp_dir / f"{temp_id}.jpg"

        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(image_file.file, buffer)

        # Try OCR first to extract text
        try:
            ocr_text = _extract_ocr_text(str(temp_path))
            if ocr_text:
                # Simple text matching: find medicine names in OCR text
                ocr_lower = ocr_text.lower()
                from app.services.medscan_service import MEDICINES

                for med_key, med_info in MEDICINES.items():
                    if med_key in ocr_lower:
                        detected_name = med_info["name"]
                        confidence = 0.85
                        break

                    # Also check generic name
                    generic_lower = med_info.get("generic_name", "").lower()
                    if generic_lower and generic_lower in ocr_lower:
                        detected_name = med_info["name"]
                        confidence = 0.80
                        break
        except Exception as exc:
            logger.debug("OCR detection failed: %s", exc)

        # Try ORB-based matching if OCR didn't find anything
        if not detected_name:
            try:
                from app.services.medscan_service import MedScanAnalyzer

                analyzer = MedScanAnalyzer()
                result = analyzer.analyze(str(temp_path))
                if result and result.get("detected_medicine"):
                    detected_name = result["detected_medicine"].get("name")
                    confidence = result.get("confidence", 0.5)
            except Exception as exc:
                logger.debug("ORB detection failed: %s", exc)

        # Clean up temp file
        try:
            temp_path.unlink()
        except Exception:
            pass

        return {
            "detected_name": detected_name,
            "confidence": confidence,
            "message": (
                f"Detected: {detected_name}" if detected_name else "No medication detected. Please enter manually."
            ),
        }

    except Exception as exc:
        logger.error("Detection endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(exc)}") from exc
    finally:
        try:
            await image_file.close()
        except Exception:
            pass