import json
import numpy as np
from PIL import Image
import os
from insightface.app import FaceAnalysis

# Load existing embeddings
face_db_path = "face_embeddings.json"
if os.path.exists(face_db_path):
    with open(face_db_path, "r") as f:
        face_db = json.load(f)
else:
    face_db = {}

# Initialize InsightFace model
app = FaceAnalysis(name='buffalo_s')
app.prepare(ctx_id=0, det_size=(640, 640))

def add_new_person(person_name, person_folder):
    """
    person_name: str, e.g., 'Mostafa'
    person_folder: folder containing images of the person
    """
    person_embs = []

    for img_name in os.listdir(person_folder):
        if not img_name.lower().endswith(('.jpg', '.png')):
            continue
        img_path = os.path.join(person_folder, img_name)
        img = Image.open(img_path).convert('RGB')
        img_np = np.array(img)

        faces = app.get(img_np)
        if len(faces) > 0:
            face = faces[0]
            if hasattr(face, 'normed_face'):
                aligned = face.normed_face
            else:
                aligned = face.kps  # fallback
            embedding = face.embedding if hasattr(face, 'embedding') else face.normed_face.flatten()
            person_embs.append(embedding)

    if person_embs:
        face_db[person_name] = np.mean(person_embs, axis=0).tolist()
        print(f"Added {person_name} to database with {len(person_embs)} images.")
    else:
        print("No faces detected for", person_name)

# Example: add new person
add_new_person("NewPerson", r"C:\Users\PC\Desktop\MOBILEFaceNet\NewPersonImages")

# Save updated database
with open(face_db_path, "w") as f:
    json.dump(face_db, f)


def cosine(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def recognize_face(face_emb):
    best_person = None
    best_score = -1
    for person, emb in face_db.items():
        score = cosine(face_emb, np.array(emb))
        if score > best_score:
            best_score = score
            best_person = person
    return best_person, best_score
