"""
Wake word detection ("Hey Jarvis") using openWakeWord.
Runs fully offline — no audio leaves your PC until the phrase is heard.
"""
import logging

from openwakeword.model import Model
from openwakeword.utils import download_models

import settings

log = logging.getLogger(__name__)


# ---------- Functions ----------

def load_model():
    try:
        return Model(wakeword_models=[settings.WAKE_WORD_MODEL], inference_framework="onnx")
    except Exception:
        # first run: the pretrained models aren't downloaded yet
        log.info("Downloading wake word models (one-time)...")
        download_models()
        return Model(wakeword_models=[settings.WAKE_WORD_MODEL], inference_framework="onnx")


def wait_for_wake(model, stream, should_stop) -> bool:
    """Blocks until 'hey jarvis' is heard, reading from the shared mic
    stream. Returns False if should_stop() became true first."""
    if hasattr(model, "reset"):
        model.reset()  # clear leftover audio so we don't instantly re-trigger

    from voice.mic import FRAME
    while not should_stop():
        frame, _ = stream.read(FRAME)
        scores = model.predict(frame.flatten())
        if scores and max(scores.values()) >= settings.WAKE_THRESHOLD:
            return True
    return False