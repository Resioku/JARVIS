"""
Records what you say after the wake word, and stops when you go quiet.
Simple loudness-based detection — tune it in settings.py.
"""
import logging
import time

import numpy as np

import settings
from voice.mic import FRAME as BLOCK, SAMPLE_RATE

log = logging.getLogger(__name__)


# ---------- Functions ----------

def record_utterance(stream, should_stop, on_slow_start=None):
    """Returns your speech as float32 audio, or None if you said nothing.
    Reads from the shared mic stream (already open).

    on_slow_start, if given, is called ONCE — only if you haven't said
    anything by settings.SLOW_START_PROMPT_SECONDS in. That's the "Yes?"
    nudge: silent by default, only speaks up if you seem to need it.
    Recording keeps going uninterrupted either way."""
    chunks = []
    heard_speech = False
    silent_blocks = 0
    peak = 0.0
    prompted = False
    silence_limit = int(settings.SILENCE_SECONDS * SAMPLE_RATE / BLOCK)
    started = time.time()

    while not should_stop():
        frame, _ = stream.read(BLOCK)
        frame = frame.flatten()
        chunks.append(frame)

        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
        peak = max(peak, rms)
        elapsed = time.time() - started

        if rms >= settings.SPEECH_RMS_THRESHOLD:
            heard_speech = True
            silent_blocks = 0
        elif heard_speech:
            silent_blocks += 1
            if silent_blocks >= silence_limit:
                break                      # you finished your sentence
        else:
            if not prompted and on_slow_start and elapsed >= settings.SLOW_START_PROMPT_SECONDS:
                on_slow_start()
                prompted = True
            if elapsed >= settings.NO_SPEECH_TIMEOUT:
                break                      # you never said anything

        if elapsed >= settings.MAX_RECORD_SECONDS:
            break

    log.info("Recording done. Peak loudness %d (threshold %d)", peak, settings.SPEECH_RMS_THRESHOLD)
    if not heard_speech:
        return None
    return np.concatenate(chunks).astype(np.float32) / 32768.0