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
import json
import threading
import traceback
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
RELATION_DB_PATH = PROJECT_ROOT / "ML" / "relation_db.json"

_relation_db_lock = threading.Lock()


def _update_relation_db(name: str, relation: str):
    with _relation_db_lock:
        try:
            db_path = str(RELATION_DB_PATH)
            if os.path.exists(db_path):
                with open(db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {}
            data[name] = relation or ""
            with open(db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[REGISTER] Failed to update relation_db.json: {e}")

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
):
    db = get_db()

    try:
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return {"error": f"Patient with id {user_id} does not exist"}

        print(f"[REGISTER PERSON] Adding friend '{name}' for patient: {user.get('full_name')} (ID: {user_id})")

        friend_folder = sanitize_folder_name(name)
        face_folder = FACES_DIR / friend_folder
        face_folder.mkdir(parents=True, exist_ok=True)

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

        person_doc = {
            "user_id": user_id,
            "name": name,
            "relation": relation,
            "photo_url": str(jpg_face_path),
            "voice": None,
            "voice_files": [],
            "permissions": permissions,
            "face_embedding": face_embedding,
            "voice_embedding": None,
        }

        result = await db.people.insert_one(person_doc)

        _update_relation_db(name, relation or "")

        print(f"[REGISTER PERSON] Successfully registered friend '{name}' for patient {user.get('full_name')}")

        return {
            "message": f"{name} registered successfully as friend for {user.get('full_name')}",
            "person_id": str(result.inserted_id),
            "patient_id": user_id,
            "patient_name": user.get('full_name'),
            "face_path": str(jpg_face_path),
        }

    except Exception as e:
        return {"error": str(e)}


@router.post("/add-voice")
async def add_voice(
    user_id: str = Form(...),
    name: str = Form(...),
    voice_file_1: UploadFile = File(...),
    voice_file_2: UploadFile = File(...),
    voice_file_3: UploadFile = File(...),
    voice_file_4: UploadFile = File(...),
):
    db = get_db()

    try:
        incoming = [voice_file_1, voice_file_2, voice_file_3, voice_file_4]
        for vf in incoming:
            if not (vf.filename or "").lower().endswith(".wav"):
                return {"error": f"Only .wav files are supported (got: {vf.filename})"}

        print(f"[ADD VOICE] Lookup: user_id={user_id!r} name={name!r}")

        person = await db.people.find_one({"user_id": user_id, "name": name})
        if not person:
            person = await db.people.find_one({
                "user_id": user_id,
                "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
            })
        if not person:
            return {"error": f"No registered person named '{name}' found for this patient"}

        folder_name = sanitize_folder_name(person.get("name", name))
        voice_folder = VOICES_DIR / folder_name
        voice_folder.mkdir(parents=True, exist_ok=True)
        print(f"[ADD VOICE] Saving to folder: {voice_folder}")

        voice_paths = []
        for idx, vf in enumerate(incoming, start=1):
            voice_path = voice_folder / f"sample_{idx}.wav"
            content = await vf.read()
            size_kb = len(content) / 1024
            print(f"[ADD VOICE] sample_{idx}.wav — {len(content)} bytes ({size_kb:.1f} KB)")
            if len(content) < 1000:
                return {"error": f"sample_{idx}.wav is too small ({len(content)} bytes). The recording may have failed — please try again."}
            with open(str(voice_path), "wb") as f:
                f.write(content)
            voice_paths.append(str(voice_path))

        # Try to generate voice embedding; if it fails we still save the files and
        # return a partial-success so the user is not left with nothing.
        voice_embedding = None
        embedding_warning = None
        try:
            embeddings = []
            for saved_path in voice_paths:
                wav_size = os.path.getsize(saved_path)
                print(f"[ADD VOICE] Generating embedding for {saved_path} ({wav_size} bytes)")
                emb = compute_voice_embedding_from_wav(saved_path)
                embeddings.append(torch.tensor(emb))
            voice_embedding = torch.stack(embeddings, dim=0).mean(dim=0).tolist()
            print(f"[ADD VOICE] Embedding generated: dim={len(voice_embedding)}")
        except Exception as emb_err:
            tb = traceback.format_exc()
            print(f"[ADD VOICE] Embedding failed:\n{tb}")
            embedding_warning = f"Voice files saved, but embedding failed: {type(emb_err).__name__}: {emb_err}"

        result = await db.people.update_one(
            {"_id": person["_id"]},
            {"$set": {
                "voice": voice_paths[0],
                "voice_files": voice_paths,
                "voice_embedding": voice_embedding,
            }},
        )
        print(f"[ADD VOICE] DB update matched={result.matched_count} modified={result.modified_count} embedding={'yes' if voice_embedding else 'no'}")

        if embedding_warning:
            return {"error": embedding_warning}

        return {
            "message": f"Voice added successfully for {person.get('name')}",
            "person_id": str(person["_id"]),
            "voice_files_count": len(voice_paths),
        }

    except Exception as e:
        print(f"[ADD VOICE] Unexpected error: {e}")
        return {"error": str(e)}


@router.delete("/people/{person_id}")
async def delete_person(person_id: str):
    db = get_db()

    try:
        person_object_id = ObjectId(person_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="person_id is invalid") from exc

    person = await db.people.find_one({"_id": person_object_id})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    name = person.get("name", "")
    folder_name = sanitize_folder_name(name)

    face_folder = FACES_DIR / folder_name
    if face_folder.exists():
        shutil.rmtree(face_folder)

    voice_folder = VOICES_DIR / folder_name
    if voice_folder.exists():
        shutil.rmtree(voice_folder)

    # Remove from relation_db.json
    with _relation_db_lock:
        try:
            if RELATION_DB_PATH.exists():
                with open(str(RELATION_DB_PATH), "r", encoding="utf-8") as f:
                    data = json.load(f)
                data.pop(name, None)
                with open(str(RELATION_DB_PATH), "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[DELETE PERSON] Failed to update relation_db.json: {e}")

    await db.people.delete_one({"_id": person_object_id})

    return {"message": "Person deleted successfully", "person_id": person_id}


@router.get("/all-relations")
async def get_all_relations():
    """Return {name: relation} for every registered person.
    Used by the standalone multimodal_recognizer.py at startup."""
    db = get_db()
    result = {}
    async for person in db.people.find({}, {"name": 1, "relation": 1, "_id": 0}):
        name = person.get("name")
        if name:
            result[name] = person.get("relation") or ""
    return result


@router.get("/people/{user_id}")
async def get_people_for_user(user_id: str, include_embeddings: bool = True):
    db = get_db()

    people = []
    async for person in db.people.find({"user_id": user_id}):
        entry = {
            "_id": str(person["_id"]),
            "name": person.get("name"),
            "relation": person.get("relation"),
            "photo_url": person.get("photo_url"),
            "has_voice": person.get("voice_embedding") is not None,
        }
        if include_embeddings:
            entry["face_embedding"] = person.get("face_embedding")
            entry["voice_embedding"] = person.get("voice_embedding")
        people.append(entry)

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
        project_root = Path(__file__).parent.parent.parent.parent
        ml_dir = project_root / "ML"
        script_path = ml_dir / "multimodal_recognizer.py"

        if not script_path.exists():
            raise HTTPException(status_code=500, detail="Recognition script not found on server")

        print(f"[RECOGNITION] Starting for user: {user.get('full_name', user_id)} (ID: {user_id})")
        print(f"[RECOGNITION] Found {people_count} people to recognize")

        try:
            env = os.environ.copy()
            env.setdefault("DISPLAY", ":0")
            env.setdefault("XAUTHORITY", os.path.expanduser("~/.Xauthority"))
            env.setdefault("WAYLAND_DISPLAY", "wayland-0")
            env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

            process = subprocess.Popen(
                [sys.executable, "-u", str(script_path)],
                cwd=str(ml_dir),
                env=env,
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