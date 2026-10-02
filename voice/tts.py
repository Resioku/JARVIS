"""
Text-to-speech using Microsoft's neural voices (edge-tts, needs internet).
Playback goes through sounddevice (the same audio backend used for the
mic) instead of Windows' legacy MCI/winmm — mixing those two caused the
microphone to go dead for a few seconds after every reply.
Short phrases are cached on disk so repeats play instantly.
"""
import asyncio
import hashlib
import logging
import winsound
from pathlib import Path

import edge_tts
import miniaudio
import numpy as np
import sounddevice as sd

import settings

log = logging.getLogger(__name__)

# ---------- Variables ----------
CACHE_DIR = Path(__file__).resolve().parent / "_cache"
CACHE_DIR.mkdir(exist_ok=True)
MAX_CACHED_CHARS = 80      # longer replies are one-offs, so they aren't kept


# ---------- Functions ----------

def _audio_path(text: str) -> Path:
    key = f"{settings.TTS_VOICE}|{settings.TTS_RATE}|{text}"
    return CACHE_DIR / (hashlib.sha1(key.encode("utf-8")).hexdigest() + ".mp3")


async def _synthesize(text: str, path: Path):
    part = path.with_suffix(".part")   # write to a temp name so a failed download never gets cached
    await edge_tts.Communicate(text, settings.TTS_VOICE, rate=settings.TTS_RATE).save(str(part))
    part.replace(path)


def _play(path: Path):
    decoded = miniaudio.mp3_read_file_f32(str(path))
    samples = np.array(decoded.samples, dtype=np.float32)
    if decoded.nchannels > 1:
        samples = samples.reshape(-1, decoded.nchannels)
    sd.play(samples, decoded.sample_rate)
    sd.wait()   # block until playback finishes, same as the old MCI "wait"


def prepare(text: str) -> bool:
    """Pre-generates the audio without playing it, so the first playback is instant."""
    try:
        path = _audio_path(text)
        if not path.exists():
            asyncio.run(_synthesize(text, path))
        return True
    except Exception:
        log.exception("Couldn't prepare speech: %s", text)
        return False


def _play_async(path: Path):
    """Same as _play(), but doesn't block — used for the 'Yes?' ack so
    recording can start the instant the wake word fires, instead of
    waiting for the ack sound to finish playing first."""
    decoded = miniaudio.mp3_read_file_f32(str(path))
    samples = np.array(decoded.samples, dtype=np.float32)
    if decoded.nchannels > 1:
        samples = samples.reshape(-1, decoded.nchannels)
    sd.play(samples, decoded.sample_rate)   # no sd.wait() — returns immediately, plays in the background


def speak_async(text: str) -> bool:
    """Like speak(), but non-blocking. Used specifically for the ack
    sound, so listening starts immediately rather than after it finishes."""
    if not text:
        return True
    path = _audio_path(text)
    try:
        if not path.exists():
            asyncio.run(_synthesize(text, path))
        _play_async(path)
        return True
    except Exception:
        log.exception("Couldn't speak (async): %s", text)
        return False


def speak(text: str) -> bool:
    """Says the text out loud. Returns False if anything went wrong."""
    if not text:
        return True
    path = _audio_path(text)
    try:
        if not path.exists():
            asyncio.run(_synthesize(text, path))
        _play(path)
        return True
    except Exception:
        log.exception("Couldn't speak: %s", text)
        return False
    finally:
        if len(text) > MAX_CACHED_CHARS:
            path.unlink(missing_ok=True)


def beep():
    """Fallback 'I heard you' sound for when speech isn't available (e.g. offline)."""
    winsound.Beep(880, 110)
    winsound.Beep(1320, 110)