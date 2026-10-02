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

import keyboard
import mouse
from PyQt6.QtCore import QThread

from core.macro_store import load_macros

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


def _run_steps_once(macro, should_stop, apply_floor):
    """apply_floor adds the small built-in delay after every step — only
    needed for loop macros, where a zero-wait loop could otherwise hammer
    the target app. A normal macro runs at exactly the timing you set."""
    for step in macro.get("steps", []):
        if should_stop():
            return

        kind = step.get("type")

        if kind == "key":
            keyboard.press_and_release(step["key"])

        elif kind == "click":
            mouse.click(button=step.get("button", "left"))

        elif kind == "wait":
            _sleep_interruptible(step.get("ms", 0), should_stop)

        if apply_floor:
            _sleep_interruptible(MIN_STEP_DELAY_MS, should_stop)


def run_macro(macro: dict):
    """Runs a macro's steps exactly once, blocking until done, with no
    extra delay added — used for non-loop macros."""
    _run_steps_once(
        macro,
        should_stop=lambda: False,
        apply_floor=False
    )


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
        try:
            if self.macro.get("loop"):
                while not self._stop_requested:
                    _run_steps_once(
                        self.macro,
                        self._should_stop,
                        apply_floor=True
                    )
            else:
                _run_steps_once(
                    self.macro,
                    self._should_stop,
                    apply_floor=False
                )
        except Exception:
            log.exception("Macro '%s' failed", self.macro.get("name"))
        finally:
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

_registered_handlers = []   # tracked ourselves — unhook_all_hotkeys() is broken in some `keyboard` versions


def register_hotkeys():
    """Re-binds every macro's global hotkey. Call this after any macro is
    added, edited, or deleted, and once at startup. Pressing a loop
    macro's hotkey again stops it, same as the voice/UI toggle."""
    global _registered_handlers
    for handler in _registered_handlers:
        try:
            keyboard.remove_hotkey(handler)
        except (KeyError, ValueError):
            pass
    _registered_handlers = []

    for macro in load_macros():
        hotkey = macro.get("hotkey")
        if hotkey:
            try:
                handler = keyboard.add_hotkey(hotkey, lambda m=macro: trigger_macro(m))
                _registered_handlers.append(handler)
            except Exception:
                log.exception("Couldn't bind hotkey '%s' for macro '%s'", hotkey, macro.get("name"))