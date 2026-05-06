from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from pathlib import Path
import shutil
import cv2
import torch
import torchaudio
import subprocess
import sys
import os
import re
from typing import List, Optional

from bson import ObjectId
from insightface.app import FaceAnalysis

from app.database import get_db
from app.services.voice_service import compute_voice_embedding_from_wav

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BASE_DIR.parent
FACES_DIR = PROJECT_ROOT / "data" / "NewPersonImages"
VOICES_DIR = PROJECT_ROOT / "data" / "voices"

face_app = FaceAnalysis(name="buffalo_s")
face_app.prepare(ctx_id=0, det_size=(640, 640))


def sanitize_folder_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", (name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "unknown"


@router.post("/register-person")
async def register_person(
    user_id: str = Form(...),
    name: str = Form(...),
    relation: str = Form(None),
    permissions: str = Form(None),
    face_file: UploadFile = File(...),
    voice_files: Optional[List[UploadFile]] = File(None),
):
    db = get_db()

    try:
        # Verify the user_id belongs to a patient (not a guardian/caregiver)
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return {"error": f"Patient with id {user_id} does not exist"}

        print(f"[REGISTER PERSON] Adding friend '{name}' for patient: {user.get('full_name')} (ID: {user_id})")

        friend_folder = sanitize_folder_name(name)
        face_folder = FACES_DIR / friend_folder
        voice_folder = VOICES_DIR / friend_folder
        face_folder.mkdir(parents=True, exist_ok=True)
        voice_folder.mkdir(parents=True, exist_ok=True)

        temp_face_path = face_folder / face_file.filename
        with open(str(temp_face_path), "wb") as buffer:
            shutil.copyfileobj(face_file.file, buffer)

        img = cv2.imread(str(temp_face_path))
        if img is None:
            temp_face_path.unlink(missing_ok=True)
            return {"error": "Uploaded face file is not a valid image"}

        jpg_face_path = face_folder / f"{name}.jpg"
        cv2.imwrite(str(jpg_face_path), img)
        temp_face_path.unlink(missing_ok=True)

        faces = face_app.get(img)
        if len(faces) == 0:
            return {"error": "No face detected in uploaded image"}

        face_embedding = faces[0].embedding.tolist()

        voice_path_str = None
        voice_paths = []
        voice_embedding = None

        valid_voice_files = [vf for vf in (voice_files or []) if vf and vf.filename]
        if len(valid_voice_files) not in (0, 3):
            return {"error": "Voice must include exactly 3 .wav files when provided"}

        if len(valid_voice_files) == 3:
            for idx, voice_file in enumerate(valid_voice_files, start=1):
                incoming_name = (voice_file.filename or "").lower()
                if not incoming_name.endswith(".wav"):
                    return {"error": "Only .wav voice files are supported"}

                voice_path = voice_folder / f"sample_{idx}.wav"
                with open(str(voice_path), "wb") as buffer:
                    shutil.copyfileobj(voice_file.file, buffer)

                voice_paths.append(str(voice_path))

            voice_path_str = voice_paths[0] if voice_paths else None

            # Generate embedding using the same local ECAPA loader style used by multimodal flow.
            try:
                embeddings = []
                for saved_voice_path in voice_paths:
                    embeddings.append(torch.tensor(compute_voice_embedding_from_wav(saved_voice_path)))
                voice_embedding = torch.stack(embeddings, dim=0).mean(dim=0).tolist()
            except Exception as emb_err:
                return {"error": f"Failed to generate voice embedding: {emb_err}"}

        person_doc = {
            "user_id": user_id,
            "name": name,
            "relation": relation,
            "photo_url": str(jpg_face_path),
            "voice": voice_path_str,
            "voice_files": voice_paths,
            "permissions": permissions,
            "face_embedding": face_embedding,
            "voice_embedding": voice_embedding,
        }

        result = await db.people.insert_one(person_doc)

        print(f"[REGISTER PERSON] Successfully registered friend '{name}' for patient {user.get('full_name')}")

        return {
            "message": f"{name} registered successfully as friend for {user.get('full_name')}",
            "person_id": str(result.inserted_id),
            "patient_id": user_id,
            "patient_name": user.get('full_name'),
            "face_path": str(jpg_face_path),
            "voice_added": len(voice_paths) == 3,
            "voice_files_count": len(voice_paths),
            "voice_embedding_added": voice_embedding is not None,
        }

    except Exception as e:
        return {"error": str(e)}


@router.get("/people/{user_id}")
async def get_people_for_user(user_id: str):
    db = get_db()
    
    people = []
    async for person in db.people.find({"user_id": user_id}):
        # Only return essential data for recognition, not full embeddings for security
        people.append({
            "name": person.get("name"),
            "relation": person.get("relation"),
            "face_embedding": person.get("face_embedding"),
            "voice_embedding": person.get("voice_embedding"),
        })
    
    return {"count": len(people), "people": people}


@router.post("/start-recognition")
async def start_recognition_for_user(request: Request):
    """
    Start multimodal recognition for the logged-in user.
    This will only recognize people associated with that user's patient.
    """
    try:
        # Get user_id from request body
        body = await request.json()
        user_id = body.get("user_id")

        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required in request body")

        db = get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="Database connection failed")

        # Verify user exists
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

        # Check if user has any associated people
        people_count = await db.people.count_documents({"user_id": user_id})
        if people_count == 0:
            return {
                "message": f"No people registered for {user.get('full_name', 'this user')}. Please add friends/family members first.",
                "status": "no_people",
                "user_id": user_id
            }

        # Path to the recognition script
        # From Backend/app/routes/people.py, go up 4 levels to project root, then to ML
        project_root = Path(__file__).parent.parent.parent.parent  # Go up to project root
        ml_dir = project_root / "ML"
        script_path = ml_dir / "start_recognition.py"

        if not script_path.exists():
            raise HTTPException(status_code=500, detail="Recognition script not found on server")

        print(f"[RECOGNITION] Starting for user: {user.get('full_name', user_id)} (ID: {user_id})")
        print(f"[RECOGNITION] Found {people_count} people to recognize")

        # Start the recognition process (this will run in background)
        # Note: In production, you'd want to manage processes better
        try:
            process = subprocess.Popen(
                [sys.executable, str(script_path), user_id],
                cwd=str(ml_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            return {
                "message": f"Recognition started for {user.get('full_name', 'user')}",
                "status": "started",
                "user_id": user_id,
                "people_count": people_count,
                "instructions": "Open camera on your laptop to see recognition"
            }
        except Exception as proc_error:
            print(f"[RECOGNITION] Failed to start process: {proc_error}")
            raise HTTPException(status_code=500, detail=f"Failed to start recognition process: {str(proc_error)}")

    except HTTPException:
        raise
    except Exception as e:
        print(f"[RECOGNITION ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start recognition: {str(e)}")