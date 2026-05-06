import pyaudio
import numpy as np
import torch
import json
from speechbrain.inference import EncoderClassifier
from collections import deque

# ---------------- SETTINGS ----------------
RATE = 16000
WINDOW_SECONDS = 2.0     # Shorter window for faster reaction
UPDATE_SECONDS = 0.5     # Update every 0.5s
CHUNK = int(RATE * UPDATE_SECONDS)
ENERGY_THRESHOLD = 0.005 

# --- SENSITIVITY SETTINGS ---
SIMILARITY_THRESHOLD = 0.45  # Lowered this (0.35 is usually good for mic)
SMOOTHING_FRAMES = 5         # Average the last 5 results to stop flickering

# Paths
DB_FILE = "voice_embeddings.json"
MODEL_PATH = r"C:\Users\ITD\Downloads\MOBILEFaceNet\Voice_recognition\pretrained_ecapa_local"

# ---------------- LOAD RESOURCES ----------------
print("Loading Voice Database...")
try:
    with open(DB_FILE, "r") as f:
        voice_db = json.load(f)
    print(f"Loaded {len(voice_db)} unique voices.")
except FileNotFoundError:
    print("Error: JSON file not found.")
    exit()

print("Loading AI Model...")
classifier = EncoderClassifier.from_hparams(
    source=MODEL_PATH,
    savedir=None,
    run_opts={"device": "cpu"}
)

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# ---------------- SETUP AUDIO & BUFFERS ----------------
p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16,
                channels=1,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK)

# Audio Buffer (Rolling window)
audio_buffer = np.zeros(0, dtype=np.float32)
max_buffer_size = int(RATE * WINDOW_SECONDS)

# Score Buffer (For smoothing results)
# Stores tuples: (best_person_name, score)
score_history = deque(maxlen=SMOOTHING_FRAMES)

print("\n" + "="*50)
print(f"🎤 STABILIZED RECOGNITION STARTED")
print(f"   Threshold: {SIMILARITY_THRESHOLD}")
print("   Speak now...")
print("="*50 + "\n")

try:
    while True:
        # 1. Read & Process Audio
        audio_data = stream.read(CHUNK, exception_on_overflow=False)
        new_waveform = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        new_waveform /= 32768.0

        # Update Audio Buffer
        audio_buffer = np.concatenate((audio_buffer, new_waveform))
        if len(audio_buffer) > max_buffer_size:
            audio_buffer = audio_buffer[-max_buffer_size:]

        # 2. Skip if silence (keeps last known state or waits)
        if np.mean(np.abs(new_waveform)) < ENERGY_THRESHOLD:
            continue

        # Wait until buffer is full enough
        if len(audio_buffer) < RATE * 1.0:
            continue

        # 3. AI Inference
        process_waveform = audio_buffer / (np.max(np.abs(audio_buffer)) + 1e-9)
        waveform_tensor = torch.from_numpy(process_waveform).unsqueeze(0)

        with torch.no_grad():
            emb = classifier.encode_batch(waveform_tensor)
            emb = emb.squeeze().cpu().numpy()

        # 4. Find Best Match for THIS frame
        frame_best_person = "Unknown"
        frame_best_score = -1.0

        for person, db_emb in voice_db.items():
            score = cosine_similarity(emb, np.array(db_emb))
            if score > frame_best_score:
                frame_best_score = score
                frame_best_person = person

        # 5. Add to History (Smoothing)
        score_history.append((frame_best_person, frame_best_score))

        # 6. Calculate Average Score & Most Frequent Person
        # Get the person who appeared most in the last 5 frames
        persons = [x[0] for x in score_history]
        most_common_person = max(set(persons), key=persons.count)
        
        # Average the scores for that person only
        avg_score = np.mean([x[1] for x in score_history if x[0] == most_common_person])

        # 7. Final Decision
        if avg_score >= SIMILARITY_THRESHOLD:
            final_name = most_common_person.upper()
            symbol = "✅"
        else:
            final_name = "UNKNOWN"
            symbol = "❌"
            # Show who it *thinks* it is, even if score is low
            if most_common_person != "Unknown":
                final_name += f" (Maybe {most_common_person}?)"

        # Print cleanly
        print(f"\r{symbol} Identity: {final_name:<25} | Avg Score: {avg_score:.3f} | Instant: {frame_best_score:.3f}", end="")

except KeyboardInterrupt:
    print("\nStopping...")
    stream.stop_stream()
    stream.close()
    p.terminate()