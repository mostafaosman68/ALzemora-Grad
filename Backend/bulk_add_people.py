#!/usr/bin/env python3
"""
Script to add people (friends) from data folder to database under patient Moustafa Osman
"""

import asyncio
import cv2
import torch
import torchaudio
import numpy as np
from pathlib import Path
from bson import ObjectId
from insightface.app import FaceAnalysis
from speechbrain.inference import EncoderClassifier

from app.database import connect_to_mongo, get_db

# Configuration
PATIENT_NAME = "Moustafa Osman"
PATIENT_ID = "69c5cfd79a8741407bef64fa"  # From test_system.py output

BASE_DIR = Path(__file__).resolve().parents[1]
FACES_DIR = BASE_DIR / "data" / "NewPersonImages"
VOICES_DIR = BASE_DIR / "data" / "voices"

# Initialize face recognition
face_app = FaceAnalysis(name="buffalo_s")
face_app.prepare(ctx_id=0, det_size=(640, 640))

# Initialize voice recognition
VOICE_MODEL_PATH = BASE_DIR / "ML" / "Voice_recognition" / "pretrained_ecapa_local"
classifier = EncoderClassifier.from_hparams(
    source=str(VOICE_MODEL_PATH).replace("\\", "/"),
    savedir=str(VOICE_MODEL_PATH).replace("\\", "/"),
    run_opts={"device": "cpu"},
)

def extract_face_embedding(image_path):
    """Extract face embedding from image"""
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"❌ Could not read image: {image_path}")
        return None

    faces = face_app.get(img)
    if len(faces) == 0:
        print(f"❌ No face detected in: {image_path}")
        return None

    if len(faces) > 1:
        print(f"⚠️  Multiple faces detected in {image_path}, using first one")

    return faces[0].embedding.tolist()

def extract_voice_embedding(voice_files):
    """Extract voice embedding from audio files"""
    if not voice_files:
        return None

    embeddings = []
    for voice_file in voice_files:
        try:
            waveform, sample_rate = torchaudio.load(str(voice_file))
            if waveform.shape[0] > 1:
                waveform = torch.mean(waveform, dim=0, keepdim=True)

            with torch.no_grad():
                embedding = (
                    classifier.encode_batch(waveform)
                    .squeeze()
                    .cpu()
                    .numpy()
                    .tolist()
                )
            embeddings.append(embedding)
        except Exception as e:
            print(f"❌ Error processing voice file {voice_file}: {e}")
            continue

    if not embeddings:
        return None

    # Average all voice embeddings
    return np.mean(embeddings, axis=0).tolist()

async def add_person_to_database(name, face_embedding, voice_embedding, face_image_path, voice_files):
    """Add person to database"""
    db = get_db()

    # Check if person already exists
    existing = await db.people.find_one({"user_id": PATIENT_ID, "name": name})
    if existing:
        print(f"⚠️  {name} already exists in database, skipping")
        return False

    person_doc = {
        "user_id": PATIENT_ID,
        "name": name,
        "relation": "friend",  # Default relation
        "photo_url": str(face_image_path),
        "voice": str(voice_files[0]) if voice_files else None,
        "permissions": "full",  # Default permissions
        "face_embedding": face_embedding,
        "voice_embedding": voice_embedding,
    }

    result = await db.people.insert_one(person_doc)
    print(f"✅ Added {name} to database (ID: {result.inserted_id})")
    return True

async def process_person_folder(person_name):
    """Process a single person's folder"""
    print(f"\n🔍 Processing {person_name}...")

    # Get face images
    face_folder = FACES_DIR / person_name
    if not face_folder.exists():
        print(f"❌ Face folder not found: {face_folder}")
        return False

    face_images = list(face_folder.glob("*"))
    face_images = [f for f in face_images if f.suffix.lower() in ['.jpg', '.jpeg', '.png']]

    if not face_images:
        print(f"❌ No face images found in {face_folder}")
        return False

    # Use first image for face embedding
    face_image_path = face_images[0]
    face_embedding = extract_face_embedding(face_image_path)
    if not face_embedding:
        return False

    # Get voice files
    voice_folder = VOICES_DIR / person_name
    voice_files = []
    if voice_folder.exists():
        voice_files = list(voice_folder.glob("*.wav"))
        voice_files.extend(voice_folder.glob("*.mp3"))
        voice_files.extend(voice_folder.glob("*.flac"))

    voice_embedding = None
    if voice_files:
        voice_embedding = extract_voice_embedding(voice_files)
        print(f"🎤 Found {len(voice_files)} voice files")
    else:
        print(f"🎤 No voice files found")

    # Add to database
    success = await add_person_to_database(
        person_name, face_embedding, voice_embedding, face_image_path, voice_files
    )

    return success

async def main():
    """Main function"""
    print("🚀 Starting bulk person registration for Moustafa Osman")
    print(f"📁 Faces directory: {FACES_DIR}")
    print(f"🎤 Voices directory: {VOICES_DIR}")
    print(f"👤 Patient ID: {PATIENT_ID}")

    # Connect to database
    await connect_to_mongo()
    db = get_db()

    # Verify patient exists
    patient = await db.users.find_one({"_id": ObjectId(PATIENT_ID)})
    if not patient:
        print(f"❌ Patient {PATIENT_NAME} not found in database")
        return

    print(f"✅ Found patient: {patient.get('full_name')}")

    # Get all person folders
    person_folders = [f for f in FACES_DIR.iterdir() if f.is_dir()]
    print(f"📂 Found {len(person_folders)} person folders: {[f.name for f in person_folders]}")

    # Process each person
    success_count = 0
    for person_folder in person_folders:
        try:
            if await process_person_folder(person_folder.name):
                success_count += 1
        except Exception as e:
            print(f"❌ Error processing {person_folder.name}: {e}")
            continue

    print(f"\n🎉 Registration complete! Successfully added {success_count}/{len(person_folders)} people")

    # Final verification
    people_count = await db.people.count_documents({"user_id": PATIENT_ID})
    print(f"📊 Total people in database for {PATIENT_NAME}: {people_count}")

if __name__ == "__main__":
    asyncio.run(main())