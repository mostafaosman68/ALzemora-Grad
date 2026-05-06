from pathlib import Path
from typing import List
import json
import os
import subprocess
import sys
import yaml
import torch
import torch.nn.functional as F
import torchaudio


BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BASE_DIR.parent

VOICE_MODEL_CANDIDATES = [
	PROJECT_ROOT / "ML" / "Voice_recognition" / "pretrained_ecapa_local",
	PROJECT_ROOT / "ML" / "Voice_Recognition" / "pretrained_ecapa_local",
	PROJECT_ROOT / "pretrained_ecapa_local",
]

_encoder = None


def resolve_voice_model_path() -> Path:
	for candidate in VOICE_MODEL_CANDIDATES:
		if (candidate / "hyperparams.yaml").exists() and (candidate / "embedding_model.ckpt").exists():
			return candidate.resolve()

	searched = ", ".join(str(path) for path in VOICE_MODEL_CANDIDATES)
	raise FileNotFoundError(
		f"Voice model not found. Expected hyperparams.yaml and embedding_model.ckpt in one of: {searched}"
	)


def _load_ecapa_from_ckpt(model_path: Path):
	from speechbrain.lobes.models.ECAPA_TDNN import ECAPA_TDNN

	hp_file = model_path / "hyperparams.yaml"
	if not hp_file.exists():
		raise FileNotFoundError(f"hyperparams.yaml not found in {model_path}")

	class IgnoreUnknownLoader(yaml.SafeLoader):
		pass

	def ignore_unknown(loader, tag_suffix, node):
		if isinstance(node, yaml.ScalarNode):
			return loader.construct_scalar(node)
		if isinstance(node, yaml.SequenceNode):
			return loader.construct_sequence(node)
		if isinstance(node, yaml.MappingNode):
			return loader.construct_mapping(node)
		return None

	IgnoreUnknownLoader.add_multi_constructor("", ignore_unknown)
	hp = yaml.load(hp_file.read_text(encoding="utf-8"), Loader=IgnoreUnknownLoader)

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

	ckpt_path = model_path / "embedding_model.ckpt"
	state = torch.load(str(ckpt_path), map_location="cpu")
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
	except Exception:
		cleaned = {}
		for key, value in candidate_state.items():
			new_key = key
			if new_key.startswith("embedding_model."):
				new_key = new_key[len("embedding_model."):]
			if new_key.startswith("module."):
				new_key = new_key[len("module."):]
			cleaned[new_key] = value
		model.load_state_dict(cleaned, strict=True)

	model.eval()
	return model, n_mels


class LocalECAPAEncoder:
	def __init__(self, model_path: Path):
		self.model, n_mels = _load_ecapa_from_ckpt(model_path)
		try:
			from speechbrain.lobes.features import Fbank

			self.fbank = Fbank(n_mels=n_mels)
			self.fbank_mode = "speechbrain"
		except Exception:
			self.fbank = torchaudio.transforms.MelSpectrogram(
				sample_rate=16000,
				n_fft=400,
				hop_length=160,
				n_mels=n_mels,
			)
			self.fbank_mode = "torchaudio"

	def embed_waveform(self, waveform: torch.Tensor) -> torch.Tensor:
		with torch.no_grad():
			feats = self.fbank(waveform)
			if self.fbank_mode == "torchaudio":
				feats = feats.transpose(1, 2)
			emb = self.model(feats).squeeze()
			return F.normalize(emb, dim=0)


def get_voice_encoder() -> LocalECAPAEncoder:
	global _encoder
	if _encoder is None:
		_encoder = LocalECAPAEncoder(resolve_voice_model_path())
	return _encoder


def _compute_voice_embedding_local(wav_path: str) -> List[float]:
	waveform, sample_rate = torchaudio.load(wav_path)
	if sample_rate != 16000:
		waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
	if waveform.shape[0] > 1:
		waveform = torch.mean(waveform, dim=0, keepdim=True)

	encoder = get_voice_encoder()
	embedding = encoder.embed_waveform(waveform).cpu().tolist()
	return embedding


def _compute_voice_embedding_with_python(wav_path: str, python_executable: str) -> List[float]:
	code = (
		"import json;"
		"from app.services.voice_service import _compute_voice_embedding_local;"
		f"print(json.dumps(_compute_voice_embedding_local(r'{wav_path}')))"
	)

	result = subprocess.run(
		[python_executable, "-c", code],
		capture_output=True,
		text=True,
		cwd=str(PROJECT_ROOT / "Backend"),
	)
	if result.returncode != 0:
		stderr_text = (result.stderr or "").strip()
		raise RuntimeError(stderr_text or f"Subprocess embedding failed with code {result.returncode}")

	output_lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
	if not output_lines:
		raise RuntimeError("Subprocess embedding returned empty output")

	return json.loads(output_lines[-1])


def compute_voice_embedding_from_wav(wav_path: str) -> List[float]:
	try:
		return _compute_voice_embedding_local(wav_path)
	except Exception as exc:
		if "Numpy is not available" not in str(exc):
			raise

		preferred_pythons = [
			r"C:\Program Files\Python310\python.exe",
			sys.executable,
		]

		last_error = exc
		for python_exec in preferred_pythons:
			if not python_exec or not os.path.exists(python_exec):
				continue
			try:
				return _compute_voice_embedding_with_python(wav_path, python_exec)
			except Exception as sub_exc:
				last_error = sub_exc

		raise RuntimeError(f"Voice embedding failed after fallback attempts: {last_error}")
