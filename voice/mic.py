"""
One shared microphone stream for the whole assistant loop. Opening/closing
the mic between wake-word listening and recording was the cause of the
"wait a bit before talking" lag — keeping it open the whole time removes
that reacquire delay.
"""
import sounddevice as sd
import settings

SAMPLE_RATE = 16000
FRAME = 1280  # 80ms of audio at 16kHz


def open_stream():
    return sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                          blocksize=FRAME, device=settings.MIC_DEVICE)

def flush(stream):
    """Discards whatever built up in the buffer (e.g. while TTS was
    playing), so recording starts from "now" instead of a backlog."""
    try:
        n = stream.read_available
        if n:
            stream.read(n)
    except Exception:
        pass