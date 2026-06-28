import os
import sys
import cv2
import numpy as np
import json
import torch
import torch.nn.functional as F
import threading
import pyaudio
import re
import time
import shutil
import queue as _queue_module
import requests
from collections import Counter, deque
from insightface.app import FaceAnalysis
from picamera2 import Picamera2
import torchaudio
import subprocess
# Compatibility shim for torchaudio >= 2.1 (removed list_audio_backends)
if not hasattr(torchaudio, 'list_audio_backends'):
    torchaudio.list_audio_backends = lambda: []

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

VOICE_MODEL_PATH  = os.path.join(BASE_DIR, "Voice_recognition", "pretrained_ecapa_local")
API_BASE_URL      = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

SPEAK_COOLDOWN = 120.0  # seconds before the same person is announced again
TTS_RATE       = 120    # words per minute — lower = slower / clearer

RATE             = 16000
WINDOW_SECONDS   = 2.0
UPDATE_SECONDS   = 0.5
CHUNK            = int(RATE * UPDATE_SECONDS)

FACE_THRESHOLD         = 0.40
VOICE_THRESHOLD        = 0.35
VOICE_HOLD_THRESHOLD   = 0.28
VOICE_CONFIRM_THRESHOLD = 0.50
VOICE_CONFIRM_MARGIN   = 0.06
VOICE_MIN_SCORE        = 0.24
VOICE_CONFIRM_FRAMES   = 2
VOICE_STABLE_FRAMES    = 4
VOICE_MAX_MISSES       = 6
SILENCE_RESET_FRAMES   = 2
ENERGY_THRESHOLD       = 0.005
SMOOTHING_FRAMES       = 5

PREFERRED_CAMERA       = '/dev/video8'  # set to None to auto-detect

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

# Shared relation lookup and per-person announcement cooldown (both threads read these)
relation_db: dict = {}
last_spoken_times: dict = {}  # {name: float timestamp}

try:
    import pyttsx3

    tts_engine = pyttsx3.init()
    tts_engine.setProperty("rate", TTS_RATE)
    TTS_AVAILABLE = True
except Exception:
    tts_engine = None
    TTS_AVAILABLE = False


# Serialized TTS queue — drains one message at a time so multiple simultaneous
# detections are announced one after the other on the speaker.
_tts_queue = _queue_module.Queue()


def _speak_blocking(text: str):
    global tts_engine, TTS_AVAILABLE
    if TTS_AVAILABLE and tts_engine is not None:
        try:
            tts_engine.say(text)
            tts_engine.runAndWait()
            return
        except Exception:
            TTS_AVAILABLE = False

    espeak_bin = shutil.which("espeak-ng") or shutil.which("espeak")
    if espeak_bin is not None:
        try:
            wav_file = "/tmp/tts_output.wav"
            subprocess.run(
                [espeak_bin, "-s", str(TTS_RATE), "-w", wav_file, text],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["paplay", "--server=/run/user/1000/pulse/native", wav_file],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass

    print(f"[TTS] {text}")


def _tts_worker():
    while True:
        msg = _tts_queue.get()
        if msg is None:
            break
        _speak_blocking(msg)
        _tts_queue.task_done()


threading.Thread(target=_tts_worker, daemon=True).start()


def speak_text(message: str):
    text = str(message).strip()
    if text:
        _tts_queue.put(text)


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

    # Prefer PulseAudio — avoids ALSA dmix path that segfaults on some Pi configs
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxInputChannels"] < 1:
            continue
        if "pulse" in info["name"].lower():
            for rate in [RATE, int(info["defaultSampleRate"])]:
                if _test_device(p, i, rate):
                    p.terminate()
                    print(f"[Audio] ✅ PulseAudio [{i}]: {info['name']} @ {rate} Hz")
                    return i, rate

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
def audio_worker(voice_db: dict):
    global shared_voice_state

    if not voice_db:
        print("[Audio] No voice data for this patient — voice recognition disabled.")
        shared_voice_state["status"] = "No Voice Data"
        return

    print(f"[Audio] Voice DB: {list(voice_db.keys())}")

    torch.set_num_threads(1)

    try:
        encoder = ECAPAEncoder(VOICE_MODEL_PATH)
    except Exception as e:
        print(f"[Audio] ❌ Model load error:\n{e}")
        shared_voice_state["status"] = "Model Error"
        return

    # Use arecord instead of PyAudio to bypass PortAudio's ALSA dmix segfault
    arecord_bin = shutil.which("arecord")
    if not arecord_bin:
        print("[Audio] ❌ arecord not found — install alsa-utils")
        shared_voice_state["status"] = "No Mic"
        return

    try:
        proc = subprocess.Popen(
            [arecord_bin, "-D", "pulse", "-r", str(RATE), "-f", "S16_LE", "-c", "1", "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"[Audio] ❌ arecord error: {e}")
        shared_voice_state["status"] = "No Mic"
        return

    print(f"[Audio] ✅ Recording via arecord/PulseAudio @ {RATE} Hz")

    chunk_bytes = CHUNK * 2  # S16_LE = 2 bytes per sample
    buffer_chunks = []
    max_buf = int(RATE * WINDOW_SECONDS)
    score_history = deque(maxlen=SMOOTHING_FRAMES)
    noise_floor = ENERGY_THRESHOLD
    locked_person = "Unknown"
    locked_score = 0.0
    miss_count = 0
    silence_count = 0
    debug_tick = 0

    print("[Audio] 🎤 Listening...")

    try:
        while True:
            raw = proc.stdout.read(chunk_bytes)
            if not raw or len(raw) < chunk_bytes:
                print("[Audio] arecord stream ended.")
                break

            pcm = torch.frombuffer(bytearray(raw), dtype=torch.int16).float() / 32768.0

            buffer_chunks.append(pcm)
            total = sum(c.shape[0] for c in buffer_chunks)

            while total > max_buf and len(buffer_chunks) > 1:
                total -= buffer_chunks.pop(0).shape[0]

            energy = pcm.abs().mean().item()
            debug_tick += 1
            if debug_tick % 20 == 0:
                print(f"[Audio] energy={energy:.5f}  buffer={total}")

            adaptive_threshold = max(ENERGY_THRESHOLD, noise_floor * 2.5)
            if energy < adaptive_threshold:
                silence_count += 1
                if silence_count < SILENCE_RESET_FRAMES and locked_person != "Unknown":
                    shared_voice_state["status"] = "Speaking"
                    noise_floor = noise_floor * 0.95 + energy * 0.05
                    continue

                shared_voice_state["status"] = "Silence"
                score_history.clear()
                locked_person = "Unknown"
                locked_score = 0.0
                miss_count = 0
                silence_count = 0
                noise_floor = noise_floor * 0.95 + energy * 0.05
                continue

            shared_voice_state["status"] = "Speaking"
            silence_count = 0
            noise_floor = noise_floor * 0.98 + energy * 0.02

            if total < RATE:
                continue

            audio_tensor = torch.cat(buffer_chunks).unsqueeze(0)
            audio_tensor = audio_tensor / (audio_tensor.abs().max() + 1e-9)

            emb = F.normalize(encoder.embed(audio_tensor), dim=0)

            best_person, best_score = "Unknown", -1.0
            second_score = -1.0
            for person, db_emb in voice_db.items():
                score = torch.dot(emb, db_emb).item()
                if score > best_score:
                    second_score = best_score
                    best_score = score
                    best_person = person
                elif score > second_score:
                    second_score = score

            score_gap = best_score - second_score if second_score > -1.0 else best_score

            candidate_person = best_person if best_score >= VOICE_MIN_SCORE else "Unknown"
            score_history.append((candidate_person, best_score))

            recent_people = [person for person, _ in score_history if person != "Unknown"]

            stable_person = "Unknown"
            stable_score = 0.0
            stable_count = 0
            if recent_people:
                counts = Counter(recent_people)
                stable_person = max(
                    counts,
                    key=lambda person: (
                        counts[person],
                        sum(score for person_name, score in score_history if person_name == person),
                    ),
                )
                stable_scores = [
                    score for person_name, score in score_history if person_name == stable_person
                ]
                stable_score = sum(stable_scores) / len(stable_scores)
                stable_count = counts[stable_person]

            voice_confident = (
                stable_person != "Unknown"
                and stable_count >= VOICE_CONFIRM_FRAMES
                and stable_score >= VOICE_CONFIRM_THRESHOLD
                and score_gap >= VOICE_CONFIRM_MARGIN
            )

            if voice_confident:
                if (
                    locked_person in ("Unknown", stable_person)
                    or stable_score >= locked_score + 0.05
                    or stable_count >= VOICE_STABLE_FRAMES
                ):
                    locked_person = stable_person
                    locked_score = max(stable_score, best_score)
                miss_count = 0
            elif locked_person != "Unknown":
                if best_person == locked_person and best_score >= VOICE_MIN_SCORE:
                    miss_count = 0
                    locked_score = 0.85 * locked_score + 0.15 * best_score
                elif best_score >= VOICE_HOLD_THRESHOLD and best_person != "Unknown":
                    miss_count = 0
                    locked_score = 0.9 * locked_score + 0.1 * best_score
                else:
                    miss_count += 1
                    locked_score *= 0.92
                    if miss_count >= VOICE_MAX_MISSES:
                        locked_person = "Unknown"
                        locked_score = 0.0

            if locked_person != "Unknown":
                shared_voice_state["person"] = locked_person
                shared_voice_state["score"] = round(max(locked_score, best_score), 4)
                if shared_voice_state["score"] >= VOICE_CONFIRM_THRESHOLD:
                    print(
                        f"[Audio] Confirmed speaker: {locked_person} "
                        f"(score={shared_voice_state['score']:.2f})"
                    )
            elif stable_person != "Unknown":
                shared_voice_state["person"] = stable_person
                shared_voice_state["score"] = round(stable_score, 4)
            else:
                shared_voice_state["person"] = "Unknown"
                shared_voice_state["score"] = round(max(best_score, 0.0), 4)

    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        proc.terminate()
        proc.wait()
        print("[Audio] Worker stopped.")


# ==========================================
# 📸 FACE HELPERS
# ==========================================
def fetch_active_patient() -> dict:
    """Query the backend for the most recently logged-in patient. Returns {} on failure."""
    try:
        resp = requests.get(f"{API_BASE_URL}/users/active-patient", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if "user_id" in data:
                print(f"[Patient] Active patient: {data.get('full_name')} (ID: {data['user_id']})")
                return data
        print(f"[Patient] Backend returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[Patient] Backend unreachable ({e})")
    return {}


def load_patient_people(user_id: str) -> tuple:
    """Fetch face_db, voice_db, and relation_db for the given patient from the backend.
    Embeddings are stored in MongoDB by the registration flow — no local files needed."""
    try:
        resp = requests.get(f"{API_BASE_URL}/people/{user_id}", timeout=10)
        if resp.status_code != 200:
            print(f"[People] Backend returned {resp.status_code}")
            return {}, {}, {}

        people = resp.json().get("people", [])
        face_db, voice_db, relation_db = {}, {}, {}

        for person in people:
            name = person.get("name")
            if not name:
                continue
            relation_db[name] = person.get("relation") or ""
            if person.get("face_embedding"):
                face_db[name] = person["face_embedding"]
            if person.get("voice_embedding"):
                emb = torch.tensor(person["voice_embedding"], dtype=torch.float32)
                voice_db[name] = F.normalize(emb, dim=0)

        print(
            f"[People] Loaded {len(face_db)} faces, {len(voice_db)} voices, "
            f"{len(relation_db)} relations for patient {user_id}"
        )
        return face_db, voice_db, relation_db

    except Exception as e:
        print(f"[People] Error loading patient data: {e}")
        return {}, {}, {}


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
    if not os.environ.get("DISPLAY"):
        return False
    try:
        info = cv2.getBuildInformation()
        return not re.search(r'GUI\s*:\s*(NONE|none)', info)
    except Exception:
        return False


def open_camera_source():
    if PREFERRED_CAMERA and os.path.exists(PREFERRED_CAMERA):
        camera = cv2.VideoCapture(PREFERRED_CAMERA)
        if camera.isOpened():
            print(f"[Video] Using preferred camera: {PREFERRED_CAMERA}")
            return "opencv", camera
        camera.release()
        print(f"[Video] Could not open {PREFERRED_CAMERA}, falling back.")

    for camera_index in range(10):
        video_node = f"/dev/video{camera_index}"
        if not os.path.exists(video_node):
            continue

        camera = cv2.VideoCapture(camera_index)
        if camera.isOpened():
            print(f"[Video] Using OpenCV webcam fallback ({video_node}).")
            return "opencv", camera

    print("[Video] No camera source available.")
    return "audio_only", None


def main():
    global relation_db

    # ── Identify active patient from the backend ─────────────────────────────
    patient = fetch_active_patient()
    if not patient:
        print("[ERROR] Could not determine the active patient from the backend.")
        print(f"[ERROR] Make sure a user is logged in and the backend is running at {API_BASE_URL}")
        return

    patient_id   = patient["user_id"]
    patient_name = patient.get("full_name", patient_id)

    # ── Load only this patient's registered people ───────────────────────────
    face_db, voice_db, relation_db = load_patient_people(patient_id)
    if not face_db and not voice_db:
        print(f"[ERROR] No registered people found for patient '{patient_name}'.")
        print("[ERROR] Ask a guardian/caregiver to register family members first.")
        return

    print(f"[Main] Patient: {patient_name} | Faces: {len(face_db)} | Voices: {len(voice_db)}")

    threading.Thread(target=audio_worker, args=(voice_db,), daemon=True).start()

    app = FaceAnalysis(name="buffalo_s")
    app.prepare(ctx_id=0, det_size=(320, 320))

    camera_mode, camera = open_camera_source()

    gui_available = has_cv2_gui_support()
    if not gui_available:
        print("[Video] No GUI display — streaming frames to /tmp/recognition_frame.jpg only.")

    print("\n MULTIMODAL FUSION READY  press Q to quit")
    print(f"   Weights  Face={W_FACE}  Voice={W_VOICE}  Threshold={FUSION_THRESHOLD}\n")

    window_title = f"Multimodal Fusion — {patient_name}"
    if gui_available:
        cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)

    frame_counter = 0
    face_results = []

    while True:

        # ============================
        # REPLACED FRAME CAPTURE
        # ============================
        if camera_mode == "opencv":
            ok, frame = camera.read()
            if not ok:
                continue
        else:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(
                frame,
                "No camera available - audio only mode",
                (30, 240),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
            )

        if frame is None:
            continue

        if frame_counter % 5 == 0:
            face_results = get_face_results(frame, app, face_db)
        frame_counter += 1

        v_person = shared_voice_state["person"]
        v_score = shared_voice_state["score"]
        v_status = shared_voice_state["status"]
        v_active = (v_status == "Speaking")

        now = time.time()
        # Tracks which people get TTS this frame to avoid double-announcement
        # when face and voice agree on the same identity.
        announced_this_frame = set()

        if face_results:
            for fr in face_results:
                r = fuse(
                    fr["person"], fr["raw_score"], fr["active"],
                    v_person, v_score, v_active
                )

                identity = r["identity"]
                fused_score = r["fused_score"]
                mode = r["mode"]
                box = fr["box"]

                rel = relation_db.get(identity, "")

                if mode == "speaker_not_visible":
                    color = (0, 165, 255)
                elif identity != "Unknown":
                    color = (0, 255, 0)
                else:
                    color = (0, 0, 255)

                cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), color, 2)

                if identity != "Unknown" and rel:
                    label = f"{identity} - {rel} [{fused_score:.2f}]"
                else:
                    label = f"{identity} [{fused_score:.2f}] {mode}"
                cv2.putText(
                    frame, label, (box[0], box[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2
                )

                # Queue TTS with relation, per-person 2-minute cooldown
                if identity != "Unknown":
                    if now - last_spoken_times.get(identity, 0) > SPEAK_COOLDOWN:
                        if rel:
                            speak_text(f"{identity}, your {rel}.")
                        else:
                            speak_text(identity)
                        last_spoken_times[identity] = now
                        announced_this_frame.add(identity)

        # Voice-only TTS: announce when voice identifies someone not already
        # announced via face this frame (e.g. person is speaking off-camera).
        if (v_person != "Unknown"
                and v_score >= FUSION_MIN_VOICE_SCORE
                and v_active
                and v_person not in announced_this_frame):
            if now - last_spoken_times.get(v_person, 0) > SPEAK_COOLDOWN:
                v_rel = relation_db.get(v_person, "")
                if v_rel:
                    speak_text(f"{v_person}, your {v_rel}.")
                else:
                    speak_text(v_person)
                last_spoken_times[v_person] = now

        # ── Status panel ──────────────────────────────────────────────────
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
            v_rel_label = relation_db.get(v_person, "") if v_person != "Unknown" else ""
            if v_person != "Unknown" and v_score >= VOICE_CONFIRM_THRESHOLD:
                panel_color = (0, 180, 0)
                main_text = "Speaker Confirmed"
                sub_text = (
                    f"{v_person} ({v_rel_label}) [{v_score:.2f}]"
                    if v_rel_label else f"{v_person} [{v_score:.2f}]"
                )
            else:
                panel_color = (0, 160, 0)
                main_text = "Speaking"
                sub_text = (
                    f"{v_person} ({v_rel_label}) [{v_score:.2f}]"
                    if v_rel_label else f"Voice: {v_person} [{v_score:.2f}]"
                )
        else:
            panel_color = (80, 80, 80)
            main_text = "Listening..."
            sub_text = ""

        cv2.rectangle(frame, (10, 10), (400, 95), panel_color, -1)
        cv2.putText(frame, "FUSION STATUS:", (20, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        cv2.putText(frame, main_text, (20, 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)

        cv2.putText(frame, sub_text, (20, 85),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)

        # Write frame to temp file so the backend can stream it to the phone
        try:
            _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            with open("/tmp/recognition_frame.jpg", "wb") as _f:
                _f.write(jpeg.tobytes())
        except Exception:
            pass

        if gui_available:
            cv2.imshow(window_title, frame)

        time.sleep(0.03)

        if gui_available and cv2.waitKey(1) & 0xFF == ord("q"):
            break

    if camera_mode == "opencv":
        camera.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()