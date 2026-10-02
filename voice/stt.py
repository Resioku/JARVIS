"""
Speech-to-text using faster-whisper, running locally on your CPU.
The first run downloads the model (~150 MB for base.en), then it's offline.
"""
from faster_whisper import WhisperModel

import settings


# ---------- Functions ----------

def load_model():
    return WhisperModel(settings.WHISPER_MODEL, device="cpu", compute_type="int8")


def transcribe(model, audio) -> str:
    segments, _ = model.transcribe(audio, language="en", beam_size=1, vad_filter=False)
    return " ".join(seg.text.strip() for seg in segments).strip()