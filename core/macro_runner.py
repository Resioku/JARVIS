"""
Runs macros and wires their triggers up. What each step does lives in
core/macro_steps.py; this file is only about WHEN and HOW a macro runs.

Run modes (macro["mode"]):
    once    - run the steps one time
    repeat  - run them macro["repeat"] times
    toggle  - loop until stopped: trigger again, say "stop", or click Stop
    hold    - loop only while the trigger is held down (stops when you let go)
Older macros with just "loop": true are treated as "toggle".

trigger_macro() is what the Run button and voice use. Hotkey/controller
triggers go through _on_trigger / _on_release below.
"""
import atexit
import ctypes
import logging

from PyQt6.QtCore import QThread

from core.input_hub import get_hub
from core.macro_steps import STEPS, RunContext, normalize, release_held
from core.macro_store import load_macros
from core.virtual_pad import PadUnavailable

log = logging.getLogger(__name__)

MIN_STEP_DELAY_MS = 10   # built-in floor after every step of a looping/repeating macro

_running = {}            # macro name -> MacroRunnerThread, while it is running (any mode)
_threads = set()         # keeps threads alive until they have fully finished
_active_ctx = []         # contexts of running macros, so quitting JARVIS can release held inputs
atexit.register(lambda: [release_held(c.held) for c in list(_active_ctx)])


# ---------- Functions (helpers) ----------

def macro_mode(macro: dict) -> str:
    mode = macro.get("mode")
    if mode in ("once", "repeat", "toggle", "hold"):
        return mode
    return "toggle" if macro.get("loop") else "once"


def _foreground_title() -> str:
    try:
        user32 = ctypes.windll.user32
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(user32.GetForegroundWindow(), buf, 256)
        return buf.value
    except Exception:
        return ""


def _find(name):
    return next((m for m in load_macros() if m.get("name") == name), None)


# ---------- Threads ----------

class MacroRunnerThread(QThread):
    """Runs a macro off the UI thread, following its run mode."""

    def __init__(self, macro):
        super().__init__()
        self.macro = macro
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def _should_stop(self):
        return self._stop_requested

    def _run_once(self, ctx, floor):
        for step in self.macro.get("steps", []):
            if self._stop_requested:
                return
            step = normalize(step)
            spec = STEPS.get(step.get("type"))
            if spec is None:
                log.warning("Macro '%s': unknown step type %r, skipped", self.macro.get("name"), step.get("type"))
                continue
            spec["run"](step, ctx)
            if floor:
                ctx.sleep(MIN_STEP_DELAY_MS)

    def run(self):
        ctx = RunContext(self._should_stop)
        _active_ctx.append(ctx)
        mode = macro_mode(self.macro)
        try:
            if not self.macro.get("steps"):
                return
            if mode in ("toggle", "hold"):
                while not self._stop_requested:
                    self._run_once(ctx, floor=True)
            else:
                rounds = max(1, int(self.macro.get("repeat", 1))) if mode == "repeat" else 1
                for _ in range(rounds):
                    if self._stop_requested:
                        break
                    self._run_once(ctx, floor=rounds > 1)
        except PadUnavailable as e:
            log.error("Macro '%s' stopped: %s", self.macro.get("name"), e)
        except Exception:
            log.exception("Macro '%s' failed", self.macro.get("name"))
        finally:
            release_held(ctx.held)
            _active_ctx.remove(ctx)
            if _running.get(self.macro.get("name")) is self:
                _running.pop(self.macro.get("name"), None)


def _start(macro):
    thread = MacroRunnerThread(macro)
    _running[macro.get("name", "")] = thread
    _threads.add(thread)
    thread.finished.connect(lambda t=thread: _threads.discard(t))
    thread.start()


def run_macro(macro: dict):
    """Runs a macro's steps once, blocking, in the calling thread."""
    ctx = RunContext(lambda: False)
    try:
        for step in macro.get("steps", []):
            step = normalize(step)
            spec = STEPS.get(step.get("type"))
            if spec:
                spec["run"](step, ctx)
    finally:
        release_held(ctx.held)


# ---------- Functions (what voice, the UI and triggers call) ----------

def is_running(name: str) -> bool:
    return name in _running


def trigger_macro(macro: dict) -> str:
    """Used by the Run button and voice: starts the macro, or stops it if it's already running."""
    name = macro.get("name", "")
    if name in _running:
        _running[name].request_stop()
        return f"Stopping {name}, sir."
    _start(macro)
    if macro_mode(macro) in ("toggle", "hold"):
        return f"Running {name} on loop, sir. Say \"stop\" to end it."
    return f"Running {name}, sir."


def stop_macro_by_name(name: str) -> bool:
    if name in _running:
        _running[name].request_stop()
        return True
    return False


def stop_all():
    for thread in list(_running.values()):
        thread.request_stop()


# ---------- Triggers (hotkeys, mouse buttons, controller buttons) ----------

def _on_trigger(name):
    macro = _find(name)
    if macro is None or not macro.get("enabled", True):
        return
    only = (macro.get("only_in") or "").strip().lower()
    if only and only not in _foreground_title().lower():
        log.info("Trigger for '%s' ignored: active window doesn't contain %r", name, only)
        return
    if macro_mode(macro) == "toggle":
        trigger_macro(macro)           # pressing again stops it
    elif name not in _running:
        _start(macro)                  # once / repeat / hold: ignore presses while it's already running


def _on_release(name):
    macro = _find(name)
    if macro is not None and macro_mode(macro) == "hold":
        stop_macro_by_name(name)


def register_hotkeys():
    """Re-binds every enabled macro's trigger. Call after any macro is added,
    edited, deleted or enabled/disabled, and once at startup."""
    hub = get_hub()
    hub.on_macro = _on_trigger
    hub.on_macro_release = _on_release
    hub.set_triggers([(m["hotkey"], m["name"]) for m in load_macros() if m.get("hotkey") and m.get("enabled", True)])
    hub.start()