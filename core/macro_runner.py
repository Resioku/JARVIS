"""
Runs macros (simulated key presses, clicks, and waits) and manages their
global hotkeys. A small built-in delay after every single step
(MIN_STEP_DELAY_MS) stops a zero-wait macro from hammering the target
app or your CPU.

Loop macros keep running until stopped — by pressing the same hotkey
again, saying "stop" to JARVIS, or clicking Run again in the panel.
trigger_macro() is the one function all three of those call, so they
all behave the same way.
"""
import logging
import time
import atexit
import keyboard
import mouse
from PyQt6.QtCore import QThread

from core.macro_store import load_macros
from core.input_hub import get_hub

log = logging.getLogger(__name__)

MIN_STEP_DELAY_MS = 10   # built-in floor after every step, regardless of type
STOP_CHECK_INTERVAL_MS = 50   # how often a loop checks for a stop request, even mid-wait

_running_loops = {}     # macro name -> MacroRunnerThread, only while a loop macro is active
_fire_and_forget = set()  # holds one-shot threads so they aren't garbage-collected mid-run


# ---------- Functions (low-level execution) ----------

def _sleep_interruptible(ms, should_stop):
    """Sleeps in small chunks, checking should_stop() throughout, so a
    long wait step doesn't delay a stop request."""
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        if should_stop():
            return
        time.sleep(min(STOP_CHECK_INTERVAL_MS, max(0, (end - time.monotonic()) * 1000)) / 1000)


_active_held = []   # every running macro's held inputs, so quitting JARVIS can let go too


def _target(step):
    if "key" in step:
        return ("key", step["key"])
    return ("mouse", step.get("button", "left"))


def _down(held, target):
    kind, name = target
    if kind == "key":
        keyboard.press(name)
    else:
        mouse.press(button=name)
    held.add(target)


def _up(held, target):
    kind, name = target
    if kind == "key":
        keyboard.release(name)
    else:
        mouse.release(button=name)
    held.discard(target)


def _release_held(held):
    """Lets go of anything a macro pressed and never released."""
    for kind, name in list(held):
        try:
            if kind == "key":
                keyboard.release(name)
            else:
                mouse.release(button=name)
        except Exception:
            log.exception("Couldn't release %s %s", kind, name)
    held.clear()


atexit.register(lambda: [_release_held(h) for h in list(_active_held)])


def _run_steps_once(macro, should_stop, apply_floor, held):
    for step in macro.get("steps", []):
        if should_stop():
            return

        kind = step.get("type")

        if kind == "key":
            keyboard.press_and_release(step["key"])
        elif kind == "click":
            mouse.click(button=step.get("button", "left"))
        elif kind in ("keydown", "mousedown"):
            _down(held, _target(step))
        elif kind in ("keyup", "mouseup"):
            _up(held, _target(step))
        elif kind == "hold":
            target = _target(step)
            _down(held, target)
            _sleep_interruptible(step.get("ms", 0), should_stop)
            _up(held, target)
        elif kind == "wait":
            _sleep_interruptible(step.get("ms", 0), should_stop)

        if apply_floor:
            _sleep_interruptible(MIN_STEP_DELAY_MS, should_stop)


def run_macro(macro: dict):
    held = set()
    try:
        _run_steps_once(macro, should_stop=lambda: False, apply_floor=False, held=held)
    finally:
        _release_held(held)


# ---------- Threads ----------

class MacroRunnerThread(QThread):
    """Runs a macro off the UI thread. If macro['loop'] is set, repeats
    its steps until request_stop() is called."""

    def __init__(self, macro):
        super().__init__()
        self.macro = macro
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def _should_stop(self):
        return self._stop_requested

    def run(self):
        held = set()
        _active_held.append(held)
        try:
            if self.macro.get("loop"):
                while not self._stop_requested:
                    _run_steps_once(self.macro, self._should_stop, apply_floor=True, held=held)
            else:
                _run_steps_once(self.macro, self._should_stop, apply_floor=False, held=held)
        except Exception:
            log.exception("Macro '%s' failed", self.macro.get("name"))
        finally:
            _release_held(held)
            _active_held.remove(held)
            _running_loops.pop(self.macro.get("name"), None)


# ---------- Functions (what hotkeys/voice/UI actually call) ----------

def is_running(name: str) -> bool:
    return name in _running_loops


def trigger_macro(macro: dict) -> str:
    """The single entry point hotkeys, voice, and the UI Run button all
    use. For a loop macro this TOGGLES it: starts if stopped, stops if
    already running. For a normal macro it just runs once."""
    name = macro.get("name", "")

    if macro.get("loop"):
        if name in _running_loops:
            _running_loops[name].request_stop()
            return f"Stopping {name}, sir."
        thread = MacroRunnerThread(macro)
        _running_loops[name] = thread
        thread.start()
        return f"Running {name} on loop, sir. Say \"stop\" to end it."

    thread = MacroRunnerThread(macro)
    _fire_and_forget.add(thread)
    thread.finished.connect(lambda t=thread: _fire_and_forget.discard(t))
    thread.start()
    return f"Running {name}, sir."


def stop_macro_by_name(name: str) -> bool:
    if name in _running_loops:
        _running_loops[name].request_stop()
        return True
    return False


def stop_all():
    for thread in list(_running_loops.values()):
        thread.request_stop()


# ---------- Hotkeys ----------

def _run_by_name(name):
    for macro in load_macros():
        if macro.get("name") == name:
            trigger_macro(macro)
            return
    log.warning("Trigger fired for unknown macro '%s'", name)


def register_hotkeys():
    """Re-binds every macro's trigger (keyboard keys or controller buttons).
    Call after any macro is added, edited or deleted, and once at startup."""
    hub = get_hub()
    hub.on_macro = _run_by_name
    hub.set_triggers([(m["hotkey"], m["name"]) for m in load_macros() if m.get("hotkey")])
    hub.start()