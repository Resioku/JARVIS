"""
Every tweakable knob in one place. Edit a value, restart JARVIS.
"""

# ---------- Wake word ----------
WAKE_WORD_MODEL = "hey_jarvis"
WAKE_THRESHOLD = 0.5          # 0 to 1. Raise if it triggers by accident, lower if it ignores you

# ---------- Microphone ----------
MIC_DEVICE = None             # None = Windows default mic. To pick another, run: python -m sounddevice
                              # then put the device number (or its name) here

# ---------- Listening (after the wake word) ----------
SPEECH_RMS_THRESHOLD = 500    # loudness that counts as "talking". Raise it if recording never stops,
                              # lower it if you get cut off mid-sentence (jarvis.log shows your peak level)
SILENCE_SECONDS = 1.0         # this much quiet ends your sentence
NO_SPEECH_TIMEOUT = 5.0       # give up if you say nothing for this long
MAX_RECORD_SECONDS = 12.0     # hard cap on one command

# ---------- Speech-to-text ----------
WHISPER_MODEL = "base.en"     # "tiny.en" = fastest, "small.en" = more accurate (bigger first download)

# ---------- Voice ----------
TTS_VOICE = "en-GB-RyanNeural"   # British male. More to try: en-GB-ThomasNeural, en-US-GuyNeural
TTS_RATE = "+0%"                 # "+10%" = faster, "-10%" = slower
ACK_PHRASE = "Yes?"               # only spoken as a nudge if you stay silent — see below
SLOW_START_PROMPT_SECONDS = 1.0   # how long to wait quietly before nudging with the ack
STARTUP_PHRASE = "Online and ready, sir."   # spoken when JARVIS starts. "" = stay quiet
CANCEL_PHRASES = ["nevermind", "never mind", "cancel", "forget it"]   # only checked at the START of what you say