import cv2
import numpy as np
import json
from PIL import Image
import os
from insightface.app import FaceAnalysis

# ------------------------------
# Step 1: Load existing embeddings
# ------------------------------
face_db_path = "face_embeddings.json"
if os.path.exists(face_db_path):
    with open(face_db_path, "r") as f:
        face_db = json.load(f)
else:
    face_db = {}

# ------------------------------
# Step 2: Initialize InsightFace
# ------------------------------
app = FaceAnalysis(name='buffalo_s')
app.prepare(ctx_id=0, det_size=(640, 640))

# ------------------------------
# Step 3: Add new people automatically
# ------------------------------
def add_new_people(new_people_folder):
    for person_name in os.listdir(new_people_folder):
        person_folder = os.path.join(new_people_folder, person_name)
        if not os.path.isdir(person_folder):
            continue

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
                embedding = face.embedding
                person_embs.append(embedding)

        if person_embs:
            face_db[person_name] = np.mean(person_embs, axis=0).tolist()
            print(f"Added {person_name} with {len(person_embs)} images.")
        else:
            print("No faces detected for", person_name)

# Folder containing new people
add_new_people(r"C:\Users\ITD\Downloads\MOBILEFaceNet\ML_Models\Face_Recognition\NewPersonImages")

# Save updated embeddings
with open(face_db_path, "w") as f:
    json.dump(face_db, f)

# ------------------------------
# Step 4: Cosine similarity
# ------------------------------
def cosine(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


# ======================================================
# 🔥 NEW PART STARTS HERE – EVALUATION METRICS
# ======================================================

def evaluate(test_folder, threshold=0.4):
    total_known = 0
    correct_id = 0

    total_verifications = 0
    correct_verifications = 0

    false_accept = 0
    false_reject = 0

    for true_person in os.listdir(test_folder):
        person_folder = os.path.join(test_folder, true_person)
        if not os.path.isdir(person_folder):
            continue

        for img_name in os.listdir(person_folder):
            if not img_name.lower().endswith(('.jpg', '.png')):
                continue

            img = Image.open(os.path.join(person_folder, img_name)).convert("RGB")
            img_np = np.array(img)

            faces = app.get(img_np)
            if not faces:
                continue

            emb = faces[0].embedding

            best_person = "Unknown"
            best_score = 0

            for person, db_emb in face_db.items():
                score = cosine(emb, np.array(db_emb))
                if score > best_score:
                    best_score = score
                    best_person = person

            predicted = best_person if best_score >= threshold else "Unknown"

            # ---- Identification ----
            if true_person != "Unknown":
                total_known += 1
                if predicted == true_person:
                    correct_id += 1

            # ---- Verification ----
            total_verifications += 1
            is_known = true_person in face_db
            is_accepted = predicted != "Unknown"

            if (is_known and predicted == true_person) or (not is_known and not is_accepted):
                correct_verifications += 1

            # ---- FAR / FRR ----
            if not is_known and is_accepted:
                false_accept += 1
            if is_known and not is_accepted:
                false_reject += 1

    return {
        "Identification Accuracy": correct_id / total_known if total_known else 0,
        "Verification Accuracy": correct_verifications / total_verifications if total_verifications else 0,
        "False Accept Rate (FAR)": false_accept / total_verifications if total_verifications else 0,
        "False Reject Rate (FRR)": false_reject / total_known if total_known else 0
    }


# ------------------------------
# 🔥 RUN EVALUATION (BEFORE WEBCAM)
# ------------------------------
THRESHOLD = 0.4

# metrics = evaluate(
#     r"C:\Users\ITD\Downloads\MOBILEFaceNet\TestImages",
#     threshold=THRESHOLD
# )

# print("\n--- Evaluation Results ---")
# for k, v in metrics.items():
#     print(f"{k}: {v:.4f}")


# ======================================================
# Step 5: Live webcam recognition (UNCHANGED)
# ======================================================

cap = cv2.VideoCapture(0)
print("Press Q to quit")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    faces = app.get(frame)

    for face in faces:
        emb = face.embedding
        best_person = "Unknown"
        best_score = 0

        for person, db_emb in face_db.items():
            score = cosine(emb, np.array(db_emb))
            if score > best_score:
                best_score = score
                best_person = person

        if best_score < THRESHOLD:
            best_person = "Unknown"

        box = face.bbox.astype(int)
        cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
        cv2.putText(
            frame,
            f"{best_person} ({best_score:.2f})",
            (box[0], box[1] - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

    cv2.imshow("Webcam Face Recognition", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
