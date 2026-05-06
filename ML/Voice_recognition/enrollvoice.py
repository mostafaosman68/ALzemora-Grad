import pyaudio
import torch
import json
import numpy as np
import os
import time
from speechbrain.inference import EncoderClassifier

# ---------------- CONFIG ----------------
OUTPUT_FILE = "voice_embeddings.json"
MODEL_PATH = r"C:\Users\ITD\Downloads\MOBILEFaceNet\pretrained_ecapa_local"
RATE = 16000
CLIP_DURATION = 4  # Seconds per clip
NUM_CLIPS = 5      # How many clips to average
CHUNK = 1024

# ---------------- SETUP ----------------
classifier = EncoderClassifier.from_hparams(
    source=MODEL_PATH, savedir=None, run_opts={"device": "cpu"}
)

def record_clip(index):
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)
    print(f"\n🔴 Recording Clip {index}/{NUM_CLIPS} (Speak naturally)...")
    
    frames = []
    for _ in range(0, int(RATE / CHUNK * CLIP_DURATION)):
        data = stream.read(CHUNK)
        frames.append(data)
    
    print("✅ Stop.")
    stream.stop_stream()
    stream.close()
    p.terminate()

    # Convert to waveform
    waveform = np.frombuffer(b''.join(frames), dtype=np.int16).astype(np.float32)
    waveform /= 32768.0  # Normalize to -1..1
    
    # Peak Normalize (Critical for consistency)
    waveform = waveform / (np.max(np.abs(waveform)) + 1e-9)
    return torch.from_numpy(waveform).unsqueeze(0)

# ---------------- MAIN ----------------
print("--- VOICE ENROLLER ---")
name = input("Enter the user's name (e.g., Mostafa): ").strip()

embeddings = []
input(f"Press ENTER to start recording {NUM_CLIPS} samples for '{name}'...")

for i in range(1, NUM_CLIPS + 1):
    wav_tensor = record_clip(i)
    
    # Generate embedding immediately
    with torch.no_grad():
        emb = classifier.encode_batch(wav_tensor).squeeze().cpu().numpy()
        embeddings.append(emb)
    
    time.sleep(0.5)

# Average the embeddings to create a stable reference
final_embedding = np.mean(embeddings, axis=0)

# Load existing DB
if os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, "r") as f:
        db = json.load(f)
else:
    db = {}

# Save new user
db[name] = final_embedding.tolist()

with open(OUTPUT_FILE, "w") as f:
    json.dump(db, f)

print(f"\n🎉 Success! '{name}' has been saved to {OUTPUT_FILE}.")
print("Now run your Multimodal Recognizer again. Your scores should jump to 0.6+.")