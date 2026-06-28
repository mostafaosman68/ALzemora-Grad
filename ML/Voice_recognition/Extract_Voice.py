import torchaudio
import torch
from speechbrain.inference import EncoderClassifier
import json
import numpy as np
import os
torchaudio.set_audio_backend("sox_io")


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
input_voice_folder = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "data", "voices"))
output_file = os.path.join(BASE_DIR, "voice_embeddings.json")

all_embeddings = {}

# Use the local model folder inside this repository
local_model_path = os.path.join(BASE_DIR, "pretrained_ecapa_local")
classifier = EncoderClassifier.from_hparams(
    source=local_model_path,
    savedir=None
)

def get_voice_embedding(path):
    signal, fs = torchaudio.load(path)
    emb = classifier.encode_batch(signal)
    return emb.squeeze().detach().numpy()

# Loop over your dataset
for person in os.listdir(input_voice_folder):
    person_folder = os.path.join(input_voice_folder, person)
    if not os.path.isdir(person_folder):
        continue

    person_embs = []

    for file in os.listdir(person_folder):
        if file.lower().endswith(".wav"):
            path = os.path.join(person_folder, file)
            emb = get_voice_embedding(path)
            person_embs.append(emb)

    if person_embs:
        all_embeddings[person] = np.mean(person_embs, axis=0).tolist()
        print("Voice processed:", person)

# Save embeddings to JSON
with open(output_file, "w") as f:
    json.dump(all_embeddings, f)

print("All voices processed successfully.")
