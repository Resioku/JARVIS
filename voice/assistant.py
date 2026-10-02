"""
The voice assistant loop. Runs on its own thread so the UI never freezes.

wake word -> "Yes?" -> record -> transcribe -> route (commands / brain) -> speak
"""
import logging

from PyQt6.QtCore import QThread, pyqtSignal

import settings
from voice import mic, recorder, tts   # lightweight — fine to import on the main thread
from voice.router import route
from voice.textutil import normalize

# NOTE: `stt` and `wakeword` are deliberately NOT imported up here. They pull in
# onnxruntime/ctranslate2 and similar heavy libraries; importing them at module
# load time meant they loaded synchronously on the MAIN thread the moment this
# file was first imported (from main.py), freezing the whole app — including
# the already-drawn orb — until the import finished. They're imported instead
# at the top of run(), which actually executes on this background thread.

log = logging.getLogger(__name__)

# ---------- Variables ----------
_instance = None


# ---------- Functions ----------

def get_assistant():
    """One shared assistant for the whole app (main.py and the Assistant section both use it)."""
    global _instance

    if _instance is None:
        _instance = VoiceAssistant()

    return _instance


class VoiceAssistant(QThread):
    # states: loading / idle / listening / thinking / speaking / muted / error
    state_changed = pyqtSignal(str)
    log_line = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._muted = False
        self.state = "loading"
        self.history = []   # last few log lines, so the Assistant section can show them when opened

    # ---------- Called from the UI thread ----------

    def set_muted(self, muted: bool):
        self._muted = muted

    def is_muted(self) -> bool:
        return self._muted

    def stop(self):
        self.requestInterruption()

        if not self.wait(3000):
            self.terminate()

    # ---------- Runs on the worker thread ----------

    def run(self):
        self._set_state("loading")

        from voice import stt, wakeword
        # See NOTE above — deferred to this thread on purpose.

        try:
            wake_model = wakeword.load_model()
            stt_model = stt.load_model()

        except Exception:
            log.exception("Couldn't load voice models")
            self._set_state("error")
            self._add_line("Couldn't load voice models. See jarvis.log")
            return

        # Pre-generate the acknowledgement so there is no synthesis delay
        # when the wake word is detected.
        tts.prepare(settings.ACK_PHRASE)

        if settings.STARTUP_PHRASE:
            self._say(settings.STARTUP_PHRASE)

        # One mic stream for the whole session — reopening it between wake
        # word and recording was the source of the "wait before talking" lag.
        with mic.open_stream() as stream:

            while not self.isInterruptionRequested():

                if self._muted:
                    self._set_state("muted")
                    self.msleep(300)
                    continue

                self._set_state("idle")

                try:
                    if not wakeword.wait_for_wake(
                        wake_model,
                        stream,
                        self._should_stop
                    ):
                        continue

                    self._add_line("- wake word heard -")
                    self._handle_interaction(stt, stt_model, stream)

                except Exception:
                    log.exception("Voice loop error")
                    self._set_state("error")
                    self.msleep(3000)

    def _handle_interaction(self, stt, stt_model, stream):
        self._set_state("listening")

        # Silent by default — recording starts the instant the wake word
        # fires, no sound at all. "Yes?" only plays as a nudge if you
        # haven't started talking within SLOW_START_PROMPT_SECONDS, and
        # it's non-blocking, so recording never pauses for it either way.
        audio = recorder.record_utterance(
            stream,
            self._should_stop,
            on_slow_start=lambda: tts.speak_async(settings.ACK_PHRASE)
        )

        if audio is None:
            self._add_line("(heard nothing)")
            return

        self._set_state("thinking")

        text = stt.transcribe(stt_model, audio)

        if not text:
            self._add_line("(couldn't make that out)")
            return

        self._add_line(f"You: {text}")

        # only cancels if said at the very START of your sentence, so it
        # doesn't trip on "nevermind" showing up mid-thought for other reasons
        said = normalize(text)
        if any(said.startswith(normalize(phrase)) for phrase in settings.CANCEL_PHRASES):
            self._add_line("(cancelled)")
            return

        reply = route(text)

        if reply:
            self._say(reply)

    def _should_stop(self) -> bool:
        return self.isInterruptionRequested() or self._muted

    def _say(self, text: str):
        self._add_line(f"Jarvis: {text}")
        self._set_state("speaking")
        tts.speak(text)

    def _set_state(self, state: str):
        self.state = state
        self.state_changed.emit(state)

    def _add_line(self, line: str):
        self.history.append(line)
        del self.history[:-50]
        self.log_line.emit(line)