"""
Every macro step type lives in the STEPS table at the bottom of this file.
The runner (what it does), the editor's Add/Edit dialogs (which fields to
show) and the step list (how to describe it) all read this one table, so
adding a new kind of step means adding ONE entry here and nothing else.

An entry:
    menu      label in the "+ Add step" menu (None = not listed there)
    fields    [(key, label, kind, default, extra)]  kind: key, pad, text, int, float, choice
    describe  step -> text shown in the list
    run       (step, ctx) -> does it. ctx.sleep(ms) waits but wakes early on stop,
              ctx.held tracks anything pressed so it gets released if the macro stops.
"""
import ctypes
import logging
import random
import sys
import time

import keyboard
import mouse

log = logging.getLogger(__name__)

# ---------- Variables ----------
TAP_HOLD_MS = 15          # how long a "tap" keeps the key/button down, so games actually register it
MOUSE_BUTTONS = ["left", "right", "middle", "x", "x2"]
PAD_BUTTONS = ["a", "b", "x", "y", "lb", "rb", "lt", "rt", "back", "start", "ls", "rs", "up", "down", "left", "right", "guide"]
STICKS = ["left", "right"]

# `keyboard` can only say "1" for numpad 1, so numpad keys are sent by scan code instead
NUMPAD_SCANCODES = {
    "num 0": 82, "num 1": 79, "num 2": 80, "num 3": 81, "num 4": 75, "num 5": 76,
    "num 6": 77, "num 7": 71, "num 8": 72, "num 9": 73,
    "num multiply": 55, "num add": 78, "num sub": 74, "num decimal": 83,
}


# ---------- Run context ----------

def sleep_interruptible(ms, should_stop, chunk_ms=50):
    """Sleeps in small chunks, checking should_stop() throughout."""
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        if should_stop():
            return
        time.sleep(min(chunk_ms, max(0, (end - time.monotonic()) * 1000)) / 1000)


class RunContext:
    def __init__(self, should_stop):
        self.should_stop = should_stop
        self.held = set()      # {("key", "w"), ("mouse", "left"), ("pad", "a"), ("stick", "left")}

    def sleep(self, ms):
        sleep_interruptible(ms, self.should_stop)


# ---------- Low-level helpers ----------

def _parts(name):
    text = str(name).strip()
    if text == "+":
        return ["plus"]
    return [NUMPAD_SCANCODES.get(p.strip().lower(), p.strip()) for p in text.split("+") if p.strip()]


def _keys_down(name):
    for part in _parts(name):
        keyboard.press(part)


def _keys_up(name):
    for part in reversed(_parts(name)):
        keyboard.release(part)


def _pad_names(button):
    return [p.strip().lower() for p in str(button).split("+") if p.strip()]


def _pad():
    from core import virtual_pad
    return virtual_pad


def release_held(held):
    """Lets go of everything a macro pressed and never released, so a stopped
    or crashed macro can't leave a key, button or stick stuck."""
    for kind, name in list(held):
        try:
            if kind == "key":
                _keys_up(name)
            elif kind == "mouse":
                mouse.release(button=name)
            elif kind == "pad":
                for n in reversed(_pad_names(name)):
                    _pad().release(n)
            elif kind == "stick":
                _pad().stick(name, 0.0, 0.0)
        except Exception:
            log.exception("Couldn't release %s %s", kind, name)
    held.clear()


def _repeat(step, ctx, action):
    count = max(1, int(step.get("count", 1)))
    for i in range(count):
        if ctx.should_stop():
            return
        action()
        if i < count - 1:
            ctx.sleep(step.get("gap", 30))


def _mouse_rel(dx, dy, ms, ctx):
    """Relative mouse movement. Uses mouse_event on Windows, which games that read
    raw mouse input (shooters, camera look) respond to; SetCursorPos-style moves don't."""
    if sys.platform != "win32":
        mouse.move(dx, dy, absolute=False, duration=ms / 1000)
        return
    user32 = ctypes.windll.user32
    steps = max(1, int(ms) // 10)
    done_x = done_y = 0
    for i in range(1, steps + 1):
        tx, ty = round(dx * i / steps), round(dy * i / steps)
        user32.mouse_event(0x0001, tx - done_x, ty - done_y, 0, 0)
        done_x, done_y = tx, ty
        if i < steps:
            ctx.sleep(10)


# ---------- Step runners ----------

def _run_key(step, ctx):
    def tap():
        _keys_down(step["key"])
        ctx.sleep(TAP_HOLD_MS)
        _keys_up(step["key"])
    _repeat(step, ctx, tap)


def _run_keydown(step, ctx):
    _keys_down(step["key"])
    ctx.held.add(("key", step["key"]))


def _run_keyup(step, ctx):
    _keys_up(step["key"])
    ctx.held.discard(("key", step["key"]))


def _run_keyhold(step, ctx):
    _run_keydown(step, ctx)
    ctx.sleep(step.get("ms", 0))
    _run_keyup(step, ctx)


def _run_click(step, ctx):
    button = step.get("button", "left")

    def click():
        mouse.press(button=button)
        ctx.sleep(TAP_HOLD_MS)
        mouse.release(button=button)
    _repeat(step, ctx, click)


def _run_mousedown(step, ctx):
    button = step.get("button", "left")
    mouse.press(button=button)
    ctx.held.add(("mouse", button))


def _run_mouseup(step, ctx):
    button = step.get("button", "left")
    mouse.release(button=button)
    ctx.held.discard(("mouse", button))


def _run_mousehold(step, ctx):
    _run_mousedown(step, ctx)
    ctx.sleep(step.get("ms", 0))
    _run_mouseup(step, ctx)


def _run_pad(step, ctx):
    names = _pad_names(step.get("button", "a"))

    def tap():
        for n in names:
            _pad().press(n)
        ctx.sleep(TAP_HOLD_MS * 3)          # pads are polled per game frame, give it a little longer
        for n in reversed(names):
            _pad().release(n)
    _repeat(step, ctx, tap)


def _run_paddown(step, ctx):
    for n in _pad_names(step.get("button", "a")):
        _pad().press(n)
    ctx.held.add(("pad", step.get("button", "a")))


def _run_padup(step, ctx):
    for n in reversed(_pad_names(step.get("button", "a"))):
        _pad().release(n)
    ctx.held.discard(("pad", step.get("button", "a")))


def _run_padhold(step, ctx):
    _run_paddown(step, ctx)
    ctx.sleep(step.get("ms", 0))
    _run_padup(step, ctx)


def _run_stick(step, ctx):
    which = step.get("stick", "left")
    _pad().stick(which, float(step.get("x", 0)), float(step.get("y", 0)))
    ms = int(step.get("ms", 0))
    if ms > 0:
        ctx.held.add(("stick", which))
        ctx.sleep(ms)
        _pad().stick(which, 0.0, 0.0)
        ctx.held.discard(("stick", which))
    else:
        ctx.held.add(("stick", which))      # stays tilted until the macro ends


def _run_move(step, ctx):
    mouse.move(int(step["x"]), int(step["y"]), absolute=True, duration=int(step.get("ms", 0)) / 1000)


def _run_moveby(step, ctx):
    _mouse_rel(int(step.get("dx", 0)), int(step.get("dy", 0)), int(step.get("ms", 0)), ctx)


def _run_scroll(step, ctx):
    mouse.wheel(int(step.get("amount", 1)))


def _run_text(step, ctx):
    keyboard.write(str(step.get("text", "")), delay=0.01)


def _run_wait(step, ctx):
    ctx.sleep(int(step.get("ms", 0)) + random.randint(0, max(0, int(step.get("rand", 0)))))


# ---------- Descriptions ----------

def _times(s):
    n = int(s.get("count", 1))
    return f"  x{n}" if n > 1 else ""


def _pad_label(button):
    return "+".join(n.upper() for n in _pad_names(button))


def _dur(ms):
    return f" over {ms}ms" if ms else ""


# ---------- The table ----------

def F(key, label, kind, default, extra=None):
    return (key, label, kind, default, extra)


KEY = F("key", "Key or combo (e.g. w, ctrl+c, num 1)", "key", "")
MBTN = F("button", "Mouse button", "choice", "left", MOUSE_BUTTONS)
PBTN = F("button", "Controller button(s) (e.g. a, lb+a)", "pad", "a")
HOLD_MS = F("ms", "Hold for (ms)", "int", 500, (10, 600000))
REPEAT = [F("count", "Repeat count", "int", 1, (1, 100000)), F("gap", "Gap between repeats (ms)", "int", 30, (0, 600000))]

STEPS = {
    "key": {"menu": "Key by name...", "fields": [KEY] + REPEAT,
            "describe": lambda s: f"Tap key: {s.get('key')}{_times(s)}", "run": _run_key},
    "keydown": {"menu": None, "fields": [KEY],
                "describe": lambda s: f"Hold down key: {s.get('key')}", "run": _run_keydown},
    "keyup": {"menu": None, "fields": [KEY],
              "describe": lambda s: f"Release key: {s.get('key')}", "run": _run_keyup},
    "keyhold": {"menu": None, "fields": [KEY, HOLD_MS],
                "describe": lambda s: f"Hold key {s.get('key')} for {s.get('ms')}ms", "run": _run_keyhold},

    "click": {"menu": "Mouse button by name...", "fields": [MBTN] + REPEAT,
              "describe": lambda s: f"Click mouse {s.get('button', 'left')}{_times(s)}", "run": _run_click},
    "mousedown": {"menu": None, "fields": [MBTN],
                  "describe": lambda s: f"Hold down mouse {s.get('button', 'left')}", "run": _run_mousedown},
    "mouseup": {"menu": None, "fields": [MBTN],
                "describe": lambda s: f"Release mouse {s.get('button', 'left')}", "run": _run_mouseup},
    "mousehold": {"menu": None, "fields": [MBTN, HOLD_MS],
                  "describe": lambda s: f"Hold mouse {s.get('button', 'left')} for {s.get('ms')}ms", "run": _run_mousehold},

    "pad": {"menu": "Controller button by name...", "fields": [PBTN] + REPEAT,
            "describe": lambda s: f"Tap controller: {_pad_label(s.get('button', 'a'))}{_times(s)}", "run": _run_pad},
    "paddown": {"menu": None, "fields": [PBTN],
                "describe": lambda s: f"Hold down controller: {_pad_label(s.get('button', 'a'))}", "run": _run_paddown},
    "padup": {"menu": None, "fields": [PBTN],
              "describe": lambda s: f"Release controller: {_pad_label(s.get('button', 'a'))}", "run": _run_padup},
    "padhold": {"menu": None, "fields": [PBTN, HOLD_MS],
                "describe": lambda s: f"Hold controller {_pad_label(s.get('button', 'a'))} for {s.get('ms')}ms", "run": _run_padhold},
    "stick": {"menu": "Controller stick...",
              "fields": [F("stick", "Stick", "choice", "left", STICKS),
                         F("x", "Left/right (-1 left ... 1 right)", "float", 0.0, (-1.0, 1.0)),
                         F("y", "Up/down (-1 down ... 1 up)", "float", 1.0, (-1.0, 1.0)),
                         F("ms", "Hold for (ms, 0 = until the macro ends)", "int", 300, (0, 600000))],
              "describe": lambda s: (f"Stick {s.get('stick')}: x={s.get('x', 0):g} y={s.get('y', 0):g}"
                                     + (f" for {s.get('ms')}ms" if s.get("ms") else " (until macro ends)")),
              "run": _run_stick},

    "move": {"menu": "Move mouse to position...", "pick_xy": True,
             "fields": [F("x", "X (pixels from screen left)", "int", 0, (-20000, 20000)),
                        F("y", "Y (pixels from screen top)", "int", 0, (-20000, 20000)),
                        F("ms", "Take (ms, 0 = instant)", "int", 0, (0, 60000))],
             "describe": lambda s: f"Move mouse to ({s.get('x')}, {s.get('y')}){_dur(s.get('ms', 0))}", "run": _run_move},
    "moveby": {"menu": "Move mouse by amount...",
               "fields": [F("dx", "Right (+) / left (-) pixels", "int", 100, (-20000, 20000)),
                          F("dy", "Down (+) / up (-) pixels", "int", 0, (-20000, 20000)),
                          F("ms", "Take (ms, 0 = instant)", "int", 0, (0, 60000))],
               "describe": lambda s: f"Move mouse by ({s.get('dx')}, {s.get('dy')}){_dur(s.get('ms', 0))}", "run": _run_moveby},
    "scroll": {"menu": "Scroll wheel...",
               "fields": [F("amount", "Notches (+ up, - down)", "int", 3, (-1000, 1000))],
               "describe": lambda s: f"Scroll wheel {'up' if s.get('amount', 1) > 0 else 'down'} {abs(s.get('amount', 1))}",
               "run": _run_scroll},
    "text": {"menu": "Type text...", "fields": [F("text", "Text to type", "text", "")],
             "describe": lambda s: f"Type: {str(s.get('text', ''))[:40]!r}", "run": _run_text},
    "wait": {"menu": "Wait...",
             "fields": [F("ms", "Wait (ms)", "int", 200, (0, 3600000)),
                        F("rand", "Plus a random extra up to (ms)", "int", 0, (0, 3600000))],
             "describe": lambda s: f"Wait {s.get('ms')}ms" + (f" (+0-{s.get('rand')}ms random)" if s.get("rand") else ""),
             "run": _run_wait},
}


# ---------- Functions (used by the editor, runner and recorder) ----------

def normalize(step: dict) -> dict:
    """Upgrades steps saved by older versions to the current type names."""
    step = dict(step)
    if step.get("type") == "hold":
        step["type"] = "keyhold" if "key" in step else "mousehold"
    return step


def default_step(step_type: str) -> dict:
    step = {"type": step_type}
    for key, _label, _kind, default, _extra in STEPS[step_type]["fields"]:
        step[key] = default
    return step


def describe(step: dict) -> str:
    step = normalize(step)
    spec = STEPS.get(step.get("type"))
    if spec is None:
        return f"(unknown step: {step.get('type')})"
    try:
        return spec["describe"](step)
    except Exception:
        return f"({step.get('type')} step, needs editing)"


_ACTION_TYPES = {
    "tap":  {"key": "key", "pad": "pad", "mouse": "click"},
    "down": {"key": "keydown", "pad": "paddown", "mouse": "mousedown"},
    "up":   {"key": "keyup", "pad": "padup", "mouse": "mouseup"},
    "hold": {"key": "keyhold", "pad": "padhold", "mouse": "mousehold"},
}


def step_for_input(text: str, action: str, ms: int = 500):
    """Turns what the hub captured ("ctrl+c", "pad:lb+pad:a", "mouse:x2") into a step.
    action is tap / down / up / hold. Returns None if nothing usable was captured."""
    tokens = [t for t in (text or "").split("+") if t]
    keys = [t for t in tokens if not t.startswith(("pad:", "mouse:"))]
    pads = [t[4:] for t in tokens if t.startswith("pad:")]
    mice = [t[6:] for t in tokens if t.startswith("mouse:")]
    if keys:
        kind, field, value = "key", "key", "+".join(keys)
    elif pads:
        kind, field, value = "pad", "button", "+".join(pads)
    elif mice:
        kind, field, value = "mouse", "button", mice[0]
    else:
        return None
    step = {"type": _ACTION_TYPES[action][kind], field: value}
    if action == "hold":
        step["ms"] = ms
    return step