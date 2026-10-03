"""
Records what you do (keys, mouse buttons + scroll wheel, controller buttons)
into macro steps, with the pauses between them. Stop with F8.

Rules, to keep recordings tidy instead of a wall of tiny steps:
  - a press and release right next to each other becomes ONE step: a tap if it
    was quick, or a timed hold if it lasted longer
  - pauses shorter than WAIT_FLOOR_MS are dropped
  - each mouse click is preceded by a "move mouse to" step for where you clicked
    (the path the mouse took in between is not recorded)
"""
import logging
import time

from PyQt6.QtCore import QObject, pyqtSignal

from core.macro_steps import step_for_input

log = logging.getLogger(__name__)

STOP_TOKEN = "f8"
MAX_SECONDS = 600
WAIT_FLOOR_MS = 25         # shorter gaps than this aren't worth a Wait step
TAP_MAX_MS = 120           # a press shorter than this is a tap, longer is a timed hold


class MacroRecorder(QObject):
    finished = pyqtSignal(list)       # emitted with the recorded steps (from a worker thread; Qt queues it)

    def __init__(self, hub):
        super().__init__()
        self._hub = hub
        self.active = False
        self._events = []             # (time, kind, payload)
        self._t0 = 0.0
        self._mouse_hook = None

    # ---------- control ----------

    def start(self):
        self._events = []
        self._t0 = time.monotonic()
        self.active = True
        self._hub.set_muted(True)     # your recorded keys must not fire your other macros
        self._hub.add_raw_listener(self._raw)
        try:
            import mouse
            self._mouse_hook = mouse.hook(self._on_mouse)
        except Exception:
            log.exception("Couldn't hook the mouse wheel for recording")

    def stop(self):
        """Ends the recording and emits the steps."""
        if not self.active:
            return
        self._teardown()
        self.finished.emit(self._build())

    def cancel(self):
        """Ends the recording and throws it away."""
        if self.active:
            self._teardown()

    def _teardown(self):
        self.active = False
        self._hub.remove_raw_listener(self._raw)
        self._hub.set_muted(False)
        if self._mouse_hook is not None:
            try:
                import mouse
                mouse.unhook(self._mouse_hook)
            except Exception:
                pass
            self._mouse_hook = None

    # ---------- capture ----------

    def _raw(self, token, down, t):
        if not self.active:
            return
        if token == STOP_TOKEN:
            if down:
                self.stop()
            return
        if t - self._t0 > MAX_SECONDS:
            self.stop()
            return
        if token.startswith("mouse:") and down:
            try:
                import mouse
                self._events.append((t, "move", mouse.get_position()))
            except Exception:
                pass
        self._events.append((t, "down" if down else "up", token))

    def _on_mouse(self, event):
        if type(event).__name__ == "WheelEvent" and self.active:
            self._events.append((time.monotonic(), "scroll", event.delta))

    # ---------- turning events into steps ----------

    def _build(self):
        # drop orphan releases (e.g. the click that pressed the Record button) and key repeats
        pressed, seq, last_pos = set(), [], None
        for t, kind, payload in sorted(self._events, key=lambda e: e[0]):
            if kind == "down":
                if payload in pressed:
                    continue
                pressed.add(payload)
            elif kind == "up":
                if payload not in pressed:
                    continue
                pressed.discard(payload)
            elif kind == "move":
                if payload == last_pos:
                    continue
                last_pos = payload
            seq.append((t, kind, payload))

        # pair adjacent press+release into one item
        items, i = [], 0
        while i < len(seq):
            t, kind, payload = seq[i]
            nxt = seq[i + 1] if i + 1 < len(seq) else None
            if kind == "down" and nxt and nxt[1] == "up" and nxt[2] == payload:
                ms = int((nxt[0] - t) * 1000)
                if ms <= TAP_MAX_MS:
                    step = step_for_input(payload, "tap")
                else:
                    step = step_for_input(payload, "hold", ms=ms)
                items.append((t, nxt[0], step))
                i += 2
                continue
            if kind in ("down", "up"):
                step = step_for_input(payload, kind)
            elif kind == "move":
                step = {"type": "move", "x": payload[0], "y": payload[1], "ms": 0}
            else:
                step = {"type": "scroll", "amount": int(payload)}
            items.append((t, t, step))
            i += 1

        steps, prev_end = [], None
        for start, end, step in items:
            if step is None:
                continue
            if prev_end is not None:
                gap = int((start - prev_end) * 1000)
                if gap >= WAIT_FLOOR_MS:
                    steps.append({"type": "wait", "ms": gap, "rand": 0})
            steps.append(step)
            prev_end = end
        return steps