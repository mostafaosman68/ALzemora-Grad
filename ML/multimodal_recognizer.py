import cv2
import numpy as np
import json
import torch
import torch.nn.functional as F
import threading
import pyaudio
import os
import re
from collections import deque
from PIL import Image
from insightface.app import FaceAnalysis

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FACE_DB_PATH      = os.path.join(BASE_DIR, "face_embeddings.json")
VOICE_DB_PATH     = os.path.join(BASE_DIR, "voice_embeddings.json")
VOICE_MODEL_PATH  = os.path.join(BASE_DIR, "Voice_Recognition", "pretrained_ecapa_local")
NEW_PEOPLE_FOLDER = os.path.join(BASE_DIR, "..", "data", "NewPersonImages")

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
# 🔀 POST-FUSION ENGINE
# ==========================================
def normalize_score(raw_cosine: float) -> float:
    return (raw_cosine + 1.0) / 2.0


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
# 🎙️ PURE LOCAL ECAPA LOADER
# No from_hparams(), no hub fetch, no symlinks
# ==========================================
def _load_ecapa_from_ckpt(model_path: str):
    """
    Load a local SpeechBrain ECAPA model without from_hparams(), hub fetch,
    or symlinks.
    """
    import yaml
    from speechbrain.lobes.models.ECAPA_TDNN import ECAPA_TDNN

    hp_file = os.path.join(model_path, "hyperparams.yaml")
    if not os.path.exists(hp_file):
        raise FileNotFoundError(f"hyperparams.yaml not found in {model_path}")

    with open(hp_file, "r", encoding="utf-8") as f:
        raw = f.read()

    class IgnoreUnknownLoader(yaml.SafeLoader):
        pass

    def ignore_unknown(loader, tag_suffix, node):
        if isinstance(node, yaml.ScalarNode):
            return loader.construct_scalar(node)
        elif isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node)
        elif isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node)
        return None

    IgnoreUnknownLoader.add_multi_constructor("", ignore_unknown)
    hp = yaml.load(raw, Loader=IgnoreUnknownLoader)

    emb_dim = int(hp.get("emb_dim", 192))
    n_mels = int(hp.get("n_mels", 80))
    channels = hp.get("channels", [1024, 1024, 1024, 1024, 3072])
    kernel_sizes = hp.get("kernel_sizes", [5, 3, 3, 3, 1])
    dilations = hp.get("dilations", [1, 2, 3, 4, 1])

    model = ECAPA_TDNN(
        input_size=n_mels,
        channels=channels,
        kernel_sizes=kernel_sizes,
        dilations=dilations,
        lin_neurons=emb_dim,
    )

    ckpt = os.path.join(model_path, "embedding_model.ckpt")
    if not os.path.exists(ckpt):
        raise FileNotFoundError(
            f"embedding_model.ckpt not found in {model_path}. "
            f"Found: {os.listdir(model_path)}"
        )

    print(f"[Audio] Loading weights from: {os.path.basename(ckpt)}")
    state = torch.load(ckpt, map_location="cpu")

    if isinstance(state, dict):
        if "state_dict" in state:
            candidate_state = state["state_dict"]
        elif "model" in state:
            candidate_state = state["model"]
        elif "embedding_model" in state:
            candidate_state = state["embedding_model"]
        else:
            candidate_state = state
    else:
        candidate_state = state

    try:
        model.load_state_dict(candidate_state, strict=True)
        print("[Audio] ✅ Weights loaded with strict=True")
    except Exception as e1:
        cleaned = {}
        for k, v in candidate_state.items():
            nk = k
            if nk.startswith("embedding_model."):
                nk = nk[len("embedding_model."):]
            if nk.startswith("module."):
                nk = nk[len("module."):]
            cleaned[nk] = v

        try:
            model.load_state_dict(cleaned, strict=True)
            print("[Audio] ✅ Weights loaded after key cleanup")
        except Exception as e2:
            raise RuntimeError(
                "Could not load embedding_model.ckpt into ECAPA_TDNN.\n"
                f"Original error: {e1}\n"
                f"After cleanup: {e2}"
            )

    model.eval()
    return model, n_mels


class ECAPAEncoder:
    """
    Wraps ECAPA-TDNN for inference.
    Loaded entirely from local files.
    """

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._model = None
        self._fbank = None
        self._fbank_mode = None
        self._load()

    def _load(self):
        self._model, n_mels = _load_ecapa_from_ckpt(self.model_path)
        self._build_fbank(n_mels)
        print("[Audio] ✅ Model loaded via pure local ECAPA loader")

    def _build_fbank(self, n_mels):
        try:
            from speechbrain.lobes.features import Fbank
            self._fbank = Fbank(n_mels=n_mels)
            self._fbank_mode = "speechbrain"
            print("[Audio] ✅ Using SpeechBrain Fbank")
        except Exception:
            import torchaudio
            self._fbank = torchaudio.transforms.MelSpectrogram(
                sample_rate=16000,
                n_fft=400,
                hop_length=160,
                n_mels=n_mels,
            )
            self._fbank_mode = "torchaudio"
            print("[Audio] ✅ Using torchaudio MelSpectrogram fallback")

    def embed(self, waveform: torch.Tensor) -> torch.Tensor:
        """
        waveform: (1, T) float32 -> embedding (D,)
        """
        with torch.no_grad():
            feats = self._fbank(waveform)

            # torchaudio returns (B, F, T), ECAPA expects (B, T, F)
            if self._fbank_mode == "torchaudio":
                feats = feats.transpose(1, 2)

            emb = self._model(feats)
            return emb.squeeze()


# ==========================================
# 🔍 AUDIO DEVICE UTILITIES
# ==========================================
def list_audio_devices():
    p = pyaudio.PyAudio()
    print("\n[Audio] Available Input Devices:")
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            print(
                f"  [{i}] {info['name']}  ch={info['maxInputChannels']}  "
                f"rate={int(info['defaultSampleRate'])}"
            )
    p.terminate()


def _test_device(p, idx, rate):
    try:
        s = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=rate,
            input=True,
            input_device_index=idx,
            frames_per_buffer=CHUNK,
        )
        s.stop_stream()
        s.close()
        return True
    except Exception:
        return False


def find_best_input_device():
    p = pyaudio.PyAudio()

    try:
        d = p.get_default_input_device_info()
        idx = d["index"]
        rate = RATE if _test_device(p, idx, RATE) else int(d["defaultSampleRate"])
        p.terminate()
        print(f"[Audio] ✅ Default [{idx}]: {d['name']} @ {rate} Hz")
        return idx, rate
    except Exception as e:
        print(f"[Audio] Default device error: {e}")

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxInputChannels"] < 1:
            continue

        for rate in [RATE, int(info["defaultSampleRate"]), 44100, 48000]:
            if _test_device(p, i, rate):
                p.terminate()
                print(f"[Audio] ✅ Fallback [{i}]: {info['name']} @ {rate} Hz")
                return i, rate

    p.terminate()
    return None, RATE


# ==========================================
# 🔊 AUDIO WORKER
# ==========================================
def audio_worker():
    global shared_voice_state

    try:
        with open(VOICE_DB_PATH, "r", encoding="utf-8") as f:
            raw_db = json.load(f)

        voice_db = {
            name: F.normalize(torch.tensor(emb, dtype=torch.float32), dim=0)
            for name, emb in raw_db.items()
        }
        print(f"[Audio] Voice DB: {list(voice_db.keys())}")

    except Exception as e:
        print(f"[Audio] ❌ Voice DB error: {e}")
        shared_voice_state["status"] = "DB Error"
        return

    if not voice_db:
        shared_voice_state["status"] = "Empty DB"
        return

    torch.set_num_threads(1)

    try:
        encoder = ECAPAEncoder(VOICE_MODEL_PATH)
    except Exception as e:
        print(f"[Audio] ❌ Model load error:\n{e}")
        shared_voice_state["status"] = "Model Error"
        return

    list_audio_devices()
    device_index, actual_rate = find_best_input_device()
    if device_index is None:
        shared_voice_state["status"] = "No Mic"
        return

    p = pyaudio.PyAudio()
    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=actual_rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK,
        )
    except Exception as e:
        print(f"[Audio] ❌ Stream error: {e}")
        shared_voice_state["status"] = "Stream Error"
        p.terminate()
        return

    resample_ratio = RATE / actual_rate
    buffer_chunks = []
    max_buf = int(RATE * WINDOW_SECONDS)
    score_history = deque(maxlen=SMOOTHING_FRAMES)
    debug_tick = 0

    print("[Audio] 🎤 Listening...")

    while True:
        try:
            raw = stream.read(CHUNK, exception_on_overflow=False)
            pcm = torch.frombuffer(bytearray(raw), dtype=torch.int16).float() / 32768.0

            if actual_rate != RATE:
                tlen = int(pcm.shape[0] * resample_ratio)
                if tlen > 0:
                    pcm = F.interpolate(
                        pcm.view(1, 1, -1),
                        size=tlen,
                        mode="linear",
                        align_corners=False,
                    ).squeeze()

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
# 📸 FACE HELPERS
# ==========================================
def load_face_db(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Face] Load error: {e}")
    return {}


def save_face_db(db, path):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(db, f)
        print(f"[Face] Saved → {path}")
    except Exception as e:
        print(f"[Face] Save error: {e}")


def add_new_people(folder, app, face_db):
    if not os.path.exists(folder):
        return face_db

    for person_name in os.listdir(folder):
        pf = os.path.join(folder, person_name)
        if not os.path.isdir(pf):
            continue

        embs = []
        for img_name in os.listdir(pf):
            if not img_name.lower().endswith((".jpg", ".jpeg", ".png")):
                continue

            try:
                img = Image.open(os.path.join(pf, img_name)).convert("RGB")
                faces = app.get(np.array(img))
                if faces:
                    embs.append(faces[0].embedding)
            except Exception as e:
                print(f"[Face] {img_name}: {e}")

        if embs:
            face_db[person_name] = np.mean(embs, axis=0).tolist()
            print(f"[Face] {person_name}: {len(embs)} images registered.")

    return face_db


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
# 🎬 MAIN
# ==========================================
def has_cv2_gui_support() -> bool:
    info = cv2.getBuildInformation()
    return not re.search(r'GUI\s*:\s*(NONE|none)', info)


def main():
    threading.Thread(target=audio_worker, daemon=True).start()

    app = FaceAnalysis(name="buffalo_s")
    app.prepare(ctx_id=0, det_size=(640, 640))

    face_db = load_face_db(FACE_DB_PATH)
    face_db = add_new_people(NEW_PEOPLE_FOLDER, app, face_db)
    save_face_db(face_db, FACE_DB_PATH)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[Video] ❌ Cannot open webcam.")
        return

    if not has_cv2_gui_support():
        print("[Video] ❌ OpenCV has no GUI support in this install.")
        print("Install the regular Windows OpenCV package: pip install opencv-python")
        print("Do not use opencv-python-headless if you want cv2.imshow() windows.")
        cap.release()
        return

    print("\n✅ MULTIMODAL FUSION READY — press Q to quit")
    print(f"   Weights → Face={W_FACE}  Voice={W_VOICE}  Threshold={FUSION_THRESHOLD}\n")

    cv2.namedWindow("Multimodal Fusion", cv2.WINDOW_NORMAL)

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
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2
                    )

                cv2.putText(
                    frame, f"F:{fr['raw_score']:.2f}  V:{v_score:.2f}",
                    (box[0], box[3] + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1
                )

                if conflict and mode != "speaker_not_visible":
                    cv2.putText(
                        frame, "CONFLICT",
                        (box[0], box[3] + 38),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 165, 255), 1
                    )

        else:
            r = fuse("Unknown", 0.0, False, v_person, v_score, v_active)
            cv2.putText(
                frame,
                f"No face | Voice: {r['identity']} [{r['fused_score']:.2f}]",
                (10, frame.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 0), 2
            )

        errors = {"No Mic", "DB Error", "Model Error", "Stream Error", "Empty DB"}

        if v_status in errors:
            panel_color = (0, 80, 180)
            main_text = v_status
            sub_text = "Check console"
        elif v_status == "Silence":
            panel_color = (50, 50, 50)
            main_text = "Silence"
            sub_text = "Face-only mode"
        elif v_active:
            panel_color = (0, 160, 0)
            main_text = "Speaking"
            sub_text = f"Voice: {v_person} [{v_score:.2f}]"
        else:
            panel_color = (80, 80, 80)
            main_text = "Listening..."
            sub_text = ""

        cv2.rectangle(frame, (10, 10), (380, 95), panel_color, -1)
        cv2.putText(
            frame, "FUSION STATUS:", (20, 32),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1
        )
        cv2.putText(
            frame, main_text, (20, 62),
            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2
        )
        cv2.putText(
            frame, sub_text, (20, 85),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1
        )
        cv2.putText(
            frame,
            f"Weights: Face={W_FACE}  Voice={W_VOICE}  Threshold={FUSION_THRESHOLD}",
            (10, frame.shape[0] - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1
        )

        cv2.imshow("Multimodal Fusion", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()