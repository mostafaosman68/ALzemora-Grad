import cv2
import numpy as np
import json
import torch
import torch.nn.functional as F
import threading
import pyaudio
import subprocess
import os
import sys
import time
import requests
import warnings
from collections import deque
from PIL import Image

# Suppress pyttsx3 warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pyttsx3")

# Initialize TTS engine at startup for faster first use
try:
    import pyttsx3
    tts_engine = pyttsx3.init()
    TTS_ENGINE_AVAILABLE = True
    print("✅ TTS engine initialized")
except Exception as e:
    TTS_ENGINE_AVAILABLE = False
    print(f"⚠️ TTS engine not available: {e}")

# ==========================================
# 🔍 DEPENDENCY CHECK
# ==========================================
def check_dependencies():
    """Check if all required packages are installed"""
    print("🔍 Checking dependencies...")

    required_packages = {
        'torch': 'torch',
        'torchaudio': 'torchaudio', 
        'cv2': 'opencv-python',
        'PIL': 'Pillow',
        'requests': 'requests',
        'pyaudio': 'pyaudio'
    }

    missing_packages = []

    for module_name, package_name in required_packages.items():
        try:
            __import__(module_name)
            print(f"✅ {module_name}")
        except ImportError:
            missing_packages.append(package_name)
            print(f"❌ {module_name} (missing)")

    # Check insightface separately (don't import during check to avoid complex dependencies)
    try:
        import importlib
        if importlib.util.find_spec("insightface") is not None:
            print("✅ insightface")
        else:
            missing_packages.append("insightface")
            print("❌ insightface (missing)")
    except:
        missing_packages.append("insightface")
        print("❌ insightface (missing)")

    # Check speechbrain separately
    try:
        import importlib
        if importlib.util.find_spec("speechbrain") is not None:
            print("✅ speechbrain")
        else:
            missing_packages.append("speechbrain")
            print("❌ speechbrain (missing)")
    except:
        missing_packages.append("speechbrain")
        print("❌ speechbrain (missing)")

    if missing_packages:
        print("\n❌ Missing required packages!")
        print("Please install them with:")
        print(f"   pip install {' '.join(missing_packages)}")
        print("\nFor the complete ML environment, run:")
        print("   pip install torch torchaudio opencv-python Pillow requests pyaudio insightface speechbrain onnxruntime")
        return False

    print("✅ All dependencies found!")
    return True

# Check dependencies before proceeding
if not check_dependencies():
    print("\n💡 Tip: If you're getting import errors, try:")
    print("   1. Use a virtual environment: python -m venv venv && venv\\Scripts\\activate")
    print("   2. Install packages: pip install torch torchaudio insightface speechbrain")
    print("   3. Or use conda: conda install pytorch torchvision torchaudio -c pytorch")
    exit(1)

# Now import the complex ML packages after dependency check
print("📦 Importing ML libraries...")
try:
    from insightface.app import FaceAnalysis
    import speechbrain
    print("✅ ML libraries imported successfully!")
except Exception as e:
    print(f"❌ Error importing ML libraries: {e}")
    print("This might be due to complex dependency conflicts.")
    print("Try installing in a fresh virtual environment:")
    print("   python -m venv ml_env")
    print("   ml_env\\Scripts\\activate")
    print("   pip install torch torchaudio insightface speechbrain onnxruntime")
    exit(1)

# ==========================================
# ⚙️ CONFIGURATION - USER-AWARE
# ==========================================
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

RATE             = 16000
WINDOW_SECONDS   = 2.0
UPDATE_SECONDS   = 0.5
CHUNK            = int(RATE * UPDATE_SECONDS)

FACE_THRESHOLD         = 0.40
VOICE_THRESHOLD        = 0.45
ENERGY_THRESHOLD       = 0.005
SMOOTHING_FRAMES       = 5

W_FACE                 = 0.70
W_VOICE                = 0.30
FUSION_THRESHOLD       = 0.55
CONFLICT_PENALTY       = 0.80
FUSION_MIN_FACE_SCORE  = 0.35
FUSION_MIN_VOICE_SCORE = 0.40

# ==========================================
# 🧠 SHARED STATE
# ==========================================
shared_voice_state = {"person": "Unknown", "score": 0.0, "status": "Silence"}

# ==========================================
# 🔗 DATABASE CONNECTION
# ==========================================
def load_user_people(user_id: str):
    """
    Load face and voice embeddings for people associated with a specific user/patient
    """
    try:
        # Get people data from backend API
        url = f"{API_BASE_URL}/people/{user_id}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"[DB] Error fetching people for user {user_id}: {response.status_code}")
            print(f"[DB] Response: {response.text}")
            return {}, {}, {}

        data = response.json()
        people = data.get("people", [])

        face_db = {}
        voice_db = {}
        relation_db = {}

        for person in people:
            name = person.get("name")
            if not name:
                continue

            relation_db[name] = person.get("relation") or ""

            # Load face embedding
            if person.get("face_embedding"):
                face_db[name] = person["face_embedding"]

            # Load voice embedding
            if person.get("voice_embedding"):
                voice_embedding = torch.tensor(person["voice_embedding"], dtype=torch.float32)
                voice_db[name] = F.normalize(voice_embedding, dim=0)

        print(f"[DB] Loaded {len(face_db)} faces, {len(voice_db)} voices, and {len(relation_db)} relations for user {user_id}")
        return face_db, voice_db, relation_db

    except Exception as e:
        print(f"[DB] Error loading user data from {API_BASE_URL}: {e}")
        return {}, {}, {}

# ==========================================
# 🔀 POST-FUSION ENGINE
# ==========================================
def normalize_score(raw_cosine: float) -> float:
    return (raw_cosine + 1.0) / 2.0


def speak_text(message: str):
    def _speak(msg):
        global tts_engine, TTS_ENGINE_AVAILABLE
        if TTS_ENGINE_AVAILABLE:
            try:
                tts_engine.say(msg)
                tts_engine.runAndWait()
                return
            except Exception:
                TTS_ENGINE_AVAILABLE = False
        
        # Fallback to PowerShell TTS
        if os.name == 'nt':
            try:
                ps_script = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    "$s.Speak([Console]::In.ReadToEnd());"
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    input=msg,
                    text=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                print(f"[TTS] Failed to speak: {msg}")
        else:
            print(f"[TTS] {msg}")

    threading.Thread(target=_speak, args=(message,), daemon=True).start()


def fuse(face_person, face_raw_score, face_active,
         voice_person, voice_raw_score, voice_active):

    f_norm = normalize_score(face_raw_score) if face_active else 0.0
    v_norm = normalize_score(voice_raw_score) if voice_active else 0.0

    face_valid = face_active and face_raw_score >= FUSION_MIN_FACE_SCORE
    voice_valid = voice_active and voice_raw_score >= FUSION_MIN_VOICE_SCORE

    if face_valid and voice_valid:
        conflict = (
            face_person != voice_person
            and face_person != "Unknown"
            and voice_person != "Unknown"
        )

        face_boost = 1.0 - (v_norm * W_VOICE)
        w_f = min(W_FACE + (1.0 - W_FACE - W_VOICE) * face_boost, 1.0)
        fused = w_f * f_norm + (1.0 - w_f) * v_norm

        if conflict:
            fused *= CONFLICT_PENALTY
            identity = face_person
            mode = "speaker_not_visible"
        else:
            identity = face_person if face_person != "Unknown" else voice_person
            mode = "face+voice"

    elif face_valid:
        fused = f_norm
        identity = face_person
        conflict = False
        mode = "face_only"

    elif voice_valid:
        fused = v_norm
        identity = voice_person
        conflict = False
        mode = "voice_only"

    else:
        fused = max(f_norm, v_norm)
        identity = "Unknown"
        conflict = False
        mode = "unknown"

    if fused < FUSION_THRESHOLD and identity != "Unknown":
        identity = "Unknown"

    return {
        "identity": identity,
        "fused_score": round(fused, 4),
        "mode": mode,
        "conflict": conflict,
        "face_norm": round(f_norm, 4),
        "voice_norm": round(v_norm, 4),
    }

# ==========================================
# 🎙️ VOICE RECOGNITION (USER-AWARE)
# ==========================================
def audio_worker(voice_db):
    global shared_voice_state

    if not voice_db:
        shared_voice_state["status"] = "No Voice Data"
        print("[Audio] No voice data available for this user")
        return

    torch.set_num_threads(1)

    # Use the local ECAPA model path
    VOICE_MODEL_PATH = r"C:\Users\ITD\Downloads\MOBILEFaceNet\ML\Voice_Recognition\pretrained_ecapa_local"

    try:
        # Import the ECAPA encoder from the original multimodal_recognizer
        sys.path.append(r"C:\Users\ITD\Downloads\MOBILEFaceNet\ML")
        from multimodal_recognizer import ECAPAEncoder
        encoder = ECAPAEncoder(VOICE_MODEL_PATH)
    except Exception as e:
        print(f"[Audio] ❌ Model load error:\n{e}")
        shared_voice_state["status"] = "Model Error"
        return

    # Audio device setup (same as original)
    p = pyaudio.PyAudio()

    try:
        # Find best input device
        device_index = None
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                device_index = i
                break

        if device_index is None:
            shared_voice_state["status"] = "No Mic"
            return

        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK,
        )
    except Exception as e:
        print(f"[Audio] ❌ Stream error: {e}")
        shared_voice_state["status"] = "Stream Error"
        p.terminate()
        return

    buffer_chunks = []
    max_buf = int(RATE * WINDOW_SECONDS)
    score_history = deque(maxlen=SMOOTHING_FRAMES)
    debug_tick = 0

    print("[Audio] 🎤 Listening...")

    while True:
        try:
            raw = stream.read(CHUNK, exception_on_overflow=False)
            pcm = torch.frombuffer(bytearray(raw), dtype=torch.int16).float() / 32768.0

            buffer_chunks.append(pcm)
            total = sum(c.shape[0] for c in buffer_chunks)

            while total > max_buf and len(buffer_chunks) > 1:
                total -= buffer_chunks.pop(0).shape[0]

            energy = pcm.abs().mean().item()
            debug_tick += 1
            if debug_tick % 20 == 0:
                print(f"[Audio] energy={energy:.5f}  buffer={total}")

            if energy < ENERGY_THRESHOLD:
                shared_voice_state["status"] = "Silence"
                continue

            shared_voice_state["status"] = "Speaking"

            if total < RATE:
                continue

            audio_tensor = torch.cat(buffer_chunks).unsqueeze(0)
            audio_tensor = audio_tensor / (audio_tensor.abs().max() + 1e-9)

            emb = F.normalize(encoder.embed(audio_tensor), dim=0)

            best_person, best_score = "Unknown", -1.0
            for person, db_emb in voice_db.items():
                score = torch.dot(emb, db_emb).item()
                if score > best_score:
                    best_score = score
                    best_person = person

            score_history.append((best_person, best_score))
            persons = [x[0] for x in score_history]
            top_person = max(set(persons), key=persons.count)
            avg_score = float(
                torch.tensor([x[1] for x in score_history if x[0] == top_person]).mean()
            )

            shared_voice_state["person"] = (
                top_person if avg_score >= VOICE_THRESHOLD else "Unknown"
            )
            shared_voice_state["score"] = avg_score

        except OSError as e:
            print(f"[Audio] Stream error: {e}")
            break
        except Exception:
            import traceback
            traceback.print_exc()
            break

    stream.stop_stream()
    stream.close()
    p.terminate()
    print("[Audio] Worker stopped.")

# ==========================================
# 📸 FACE RECOGNITION (USER-AWARE)
# ==========================================
def get_face_results(frame, app, face_db):
    results = []

    for face in app.get(frame):
        emb = face.embedding
        best_person, best_score = "Unknown", 0.0

        for name, db_emb in face_db.items():
            db_emb = np.array(db_emb)
            score = float(
                np.dot(emb, db_emb)
                / (np.linalg.norm(emb) * np.linalg.norm(db_emb) + 1e-9)
            )
            if score > best_score:
                best_score = score
                best_person = name

        results.append(
            {
                "box": face.bbox.astype(int),
                "person": best_person if best_score >= FACE_THRESHOLD else "Unknown",
                "raw_score": best_score,
                "active": True,
            }
        )

    return results

# ==========================================
# 🎬 MAIN USER-AWARE RECOGNIZER
# ==========================================
def main(user_id: str):
    """
    Main function that takes a user_id and only recognizes people associated with that user
    """
    if not user_id:
        print("[ERROR] No user_id provided. Usage: python user_aware_recognizer.py <user_id>")
        return

    print(f"[USER] Starting recognition for user: {user_id}")

    # Load user-specific face and voice databases
    face_db, voice_db, relation_db = load_user_people(user_id)

    if not face_db and not voice_db:
        print(f"[ERROR] No face or voice data found for user {user_id}")
        print(f"[ERROR] Check that the backend is reachable at {API_BASE_URL}")
        print("Please add friends/family members for this user first.")
        return

    # Start voice recognition thread
    if voice_db:
        threading.Thread(target=audio_worker, args=(voice_db,), daemon=True).start()
    else:
        print("[WARNING] No voice data available - voice recognition disabled")

    # Initialize face recognition
    app = FaceAnalysis(name="buffalo_s")
    app.prepare(ctx_id=0, det_size=(640, 640))

    # Open webcam
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[Video] ❌ Cannot open webcam.")
        return

    print("✅ USER-AWARE MULTIMODAL FUSION READY")
    print(f"   User ID: {user_id}")
    print(f"   Face DB: {len(face_db)} people")
    print(f"   Voice DB: {len(voice_db)} people")
    print(f"   Weights → Face={W_FACE}  Voice={W_VOICE}  Threshold={FUSION_THRESHOLD}")
    print("   Press Q to quit\n")

    last_spoken_identity = None
    last_spoken_time = 0.0
    SPEAK_COOLDOWN = 420.0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        face_results = get_face_results(frame, app, face_db)

        v_person = shared_voice_state["person"]
        v_score = shared_voice_state["score"]
        v_status = shared_voice_state["status"]
        v_active = (v_status == "Speaking")

        if face_results:
            for fr in face_results:
                r = fuse(
                    fr["person"], fr["raw_score"], fr["active"],
                    v_person, v_score, v_active
                )

                identity = r["identity"]
                fused_score = r["fused_score"]
                mode = r["mode"]
                conflict = r["conflict"]
                box = fr["box"]

                if mode == "speaker_not_visible":
                    color = (0, 165, 255)
                elif identity != "Unknown":
                    color = (0, 255, 0)
                else:
                    color = (0, 0, 255)

                cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), color, 2)

                if mode == "speaker_not_visible":
                    line1 = f"Face: {identity} [{fused_score:.2f}]"
                    line2 = f"Speaker: {v_person}  NOT VISIBLE"

                    cv2.putText(
                        frame, line2, (box[0], max(25, box[1] - 30)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 2
                    )
                    cv2.putText(
                        frame, line1, (box[0], box[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2
                    )
                else:
                    label = f"{identity} [{fused_score:.2f}] {mode}"
                    cv2.putText(
                        frame, label, (box[0], box[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2
                    )

                relation = relation_db.get(identity, "")
                if identity != "Unknown" and relation:
                    now = time.time()
                    if identity != last_spoken_identity or (now - last_spoken_time) > SPEAK_COOLDOWN:
                        speak_text(f"This is your {relation}.")
                        last_spoken_identity = identity
                        last_spoken_time = now

        # Display voice status
        status_text = f"Voice: {v_person} ({v_status})"
        cv2.putText(
            frame, status_text, (10, frame.shape[0] - 40),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
        )

        # Display user info
        user_text = f"User: {user_id}"
        cv2.putText(
            frame, user_text, (10, frame.shape[0] - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1
        )

        cv2.imshow("User-Aware Multimodal Recognition", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[USER] Recognition stopped.")

if __name__ == "__main__":
    # 1. Try environment variable (set by backend when launching automatically)
    user_id = os.environ.get("USER_ID_FOR_RECOGNITION")

    # 2. Try command-line argument
    if not user_id and len(sys.argv) == 2:
        user_id = sys.argv[1]

    # 3. Ask the user to type it in
    if not user_id:
        user_id = input("Enter User ID: ").strip()

    if not user_id:
        print("[ERROR] No user ID provided.")
        sys.exit(1)

    main(user_id)