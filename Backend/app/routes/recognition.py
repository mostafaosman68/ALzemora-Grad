from fastapi import APIRouter, UploadFile, File
from pathlib import Path
import shutil
import cv2
import torch

from insightface.app import FaceAnalysis

from app.database import get_db
from app.services.voice_service import compute_voice_embedding_from_wav

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BASE_DIR.parent
TEMP_DIR = PROJECT_ROOT / "data" / "temp_recognition"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

FACE_THRESHOLD = 0.40
VOICE_THRESHOLD = 0.45

face_app = FaceAnalysis(name="buffalo_s")
face_app.prepare(ctx_id=0, det_size=(640, 640))


def cosine_similarity(a, b):
    a_tensor = torch.tensor(a, dtype=torch.float32)
    b_tensor = torch.tensor(b, dtype=torch.float32)
    denom = torch.norm(a_tensor) * torch.norm(b_tensor)
    if denom.item() == 0:
        return 0.0
    return float(torch.dot(a_tensor, b_tensor) / denom)


@router.post("/recognize-person")
async def recognize_person(
    face_file: UploadFile = File(...),
    voice_file: UploadFile = File(None),
):
    db = get_db()

    temp_face_path = TEMP_DIR / face_file.filename
    with open(str(temp_face_path), "wb") as buffer:
        shutil.copyfileobj(face_file.file, buffer)

    img = cv2.imread(str(temp_face_path))
    if img is None:
        temp_face_path.unlink(missing_ok=True)
        return {"error": "Uploaded face file is not a valid image"}

    faces = face_app.get(img)
    if len(faces) == 0:
        temp_face_path.unlink(missing_ok=True)
        return {"error": "No face detected in uploaded image"}

    query_face_embedding = faces[0].embedding.tolist()

    people = []
    async for person in db.people.find():
        people.append(person)

    best_face_person = "Unknown"
    best_face_score = 0.0
    best_face_person_id = None

    for person in people:
        db_face_embedding = person.get("face_embedding")
        if not db_face_embedding:
            continue

        score = cosine_similarity(query_face_embedding, db_face_embedding)
        if score > best_face_score:
            best_face_score = score
            best_face_person = person["name"]
            best_face_person_id = str(person["_id"])

    if best_face_score < FACE_THRESHOLD:
        best_face_person = "Unknown"
        best_face_person_id = None

    best_voice_person = "Not provided"
    best_voice_score = 0.0
    best_voice_person_id = None

    if voice_file is not None:
        temp_voice_path = TEMP_DIR / voice_file.filename
        with open(str(temp_voice_path), "wb") as buffer:
            shutil.copyfileobj(voice_file.file, buffer)

        query_voice_embedding = compute_voice_embedding_from_wav(str(temp_voice_path))

        best_voice_person = "Unknown"

        for person in people:
            db_voice_embedding = person.get("voice_embedding")
            if not db_voice_embedding:
                continue

            score = cosine_similarity(query_voice_embedding, db_voice_embedding)
            if score > best_voice_score:
                best_voice_score = score
                best_voice_person = person["name"]
                best_voice_person_id = str(person["_id"])

        if best_voice_score < VOICE_THRESHOLD:
            best_voice_person = "Unknown"
            best_voice_person_id = None

        temp_voice_path.unlink(missing_ok=True)

    final_person = best_face_person
    final_person_id = best_face_person_id
    decision_source = "face"

    if voice_file is not None:
        if best_face_person != "Unknown" and best_voice_person != "Unknown":
            if best_face_person == best_voice_person:
                decision_source = "face+voice"
            else:
                decision_source = "conflict_prefer_face"
        elif best_face_person == "Unknown" and best_voice_person != "Unknown":
            final_person = best_voice_person
            final_person_id = best_voice_person_id
            decision_source = "voice"
        elif best_face_person == "Unknown" and best_voice_person == "Unknown":
            final_person = "Unknown"
            final_person_id = None
            decision_source = "none"

    temp_face_path.unlink(missing_ok=True)

    return {
        "final_result": {
            "person_id": final_person_id,
            "name": final_person,
            "decision_source": decision_source,
        },
        "face_result": {
            "person_id": best_face_person_id,
            "name": best_face_person,
            "score": round(best_face_score, 4),
            "threshold": FACE_THRESHOLD,
        },
        "voice_result": {
            "person_id": best_voice_person_id,
            "name": best_voice_person,
            "score": round(best_voice_score, 4),
            "threshold": VOICE_THRESHOLD if voice_file is not None else None,
        },
    }