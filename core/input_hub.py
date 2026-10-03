"""
One listener for ALL macro triggers: keyboard keys (with numpad keys kept
separate from the top-row digits) and XInput controllers (Xbox pads, or
anything Steam Input / DS4Windows presents as one).

Every input becomes a text "token":
    keyboard:    "x", "f5", "ctrl", "num 1", "num add", "num enter"
    controller:  "pad:a", "pad:rb", "pad:lt", "pad:up", "pad:start" ...
A trigger is tokens joined with "+", e.g. "x", "ctrl+num 1", "pad:lb+pad:a".
A trigger fires when EXACTLY those tokens are held (so "x" does not fire
on ctrl+x). Keyboard and controller tokens can be mixed in one trigger.

Why this replaces keyboard.add_hotkey(): that library names keypad digits
the same as top-row digits ("num 1" silently becomes "1"), so a numpad
hotkey can't be told apart from the top-row key. Here numpad keys get their
own tokens, and every registration and every fire is written to jarvis.log.
"""
import ctypes
import logging
import sys
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

log = logging.getLogger(__name__)

# ---------- Variables ----------
LOG_EVERY_INPUT = False      # True = log every single key/button seen (turn on for one run when debugging)
TRIGGER_THRESHOLD = 150      # 0-255, how far a controller trigger must be pulled to count as pressed
POLL_SECONDS = 0.008         # controller poll rate (~125 times a second)
PROBE_SECONDS = 2.0          # how often to look for a controller in an empty slot (probing is slow)

MODIFIER_ORDER = ["ctrl", "shift", "alt", "alt gr", "windows"]
_SIDED = ("ctrl", "shift", "alt", "windows")
_KEYPAD_NAMES = {
    "*": "multiply", "+": "add", "-": "sub", "/": "divide",
    ".": "decimal", "decimal": "decimal", "separator": "decimal",
}
_ALIASES = {"num plus": "num add", "num minus": "num sub", "num subtract": "num sub"}

_PAD_BUTTONS = [
    (0x0001, "pad:up"), (0x0002, "pad:down"), (0x0004, "pad:left"), (0x0008, "pad:right"),
    (0x0010, "pad:start"), (0x0020, "pad:back"), (0x0040, "pad:ls"), (0x0080, "pad:rs"),
    (0x0100, "pad:lb"), (0x0200, "pad:rb"),
    (0x1000, "pad:a"), (0x2000, "pad:b"), (0x4000, "pad:x"), (0x8000, "pad:y"),
]


# ---------- Functions (token handling) ----------

def norm_token(name):
    """Turns any key name into the one canonical token used everywhere."""
    name = (name or "").strip().lower()
    if not name:
        return None
    if name.startswith("pad:"):
        return name
    if name.startswith("num ") and name != "num lock":
        return _ALIASES.get(name, name)
    if name == "control":
        name = "ctrl"
    for base in _SIDED:
        if name in (base, "left " + base, "right " + base):
            return base
    if name == "+":
        return "plus"
    try:
        from keyboard import normalize_name
        return normalize_name(name)
    except Exception:
        return name


def key_token(name, is_keypad):
    name = (name or "").lower()
    if not name:
        return None
    if is_keypad and name != "num lock":
        return norm_token("num " + _KEYPAD_NAMES.get(name, name))
    return norm_token(name)


def parse_combo(text):
    tokens = [norm_token(t) for t in (text or "").split("+")]
    return frozenset(t for t in tokens if t)


def combo_text(tokens):
    """Modifiers first, then everything else in the order it was pressed."""
    mods = [t for t in MODIFIER_ORDER if t in tokens]
    rest = [t for t in tokens if t not in MODIFIER_ORDER]
    return "+".join(mods + rest)


# ---------- XInput (controller) structures ----------

class _Gamepad(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort), ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short),
    ]


class _XState(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_ulong), ("Gamepad", _Gamepad)]


def _load_xinput():
    if sys.platform != "win32":
        return None
    for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            return getattr(ctypes.windll, dll)
        except (OSError, AttributeError):
            continue
    return None


# ---------- The hub ----------

class InputHub(QObject):
    _fire = pyqtSignal(str)       # worker thread -> GUI thread (queued automatically)
    captured = pyqtSignal(str)    # a finished capture; "" means cancelled/cleared (Esc)

    def __init__(self):
        super().__init__()
        self.on_macro = None       # set by core/macro_runner.py: called on the GUI thread with a macro name
        self._lock = threading.Lock()
        self._held = []            # tokens currently down, in press order
        self._triggers = {}        # frozenset(tokens) -> macro name
        self._capturing = False
        self._peak = []
        self._started = False
        self._fire.connect(self._dispatch)

    # ---------- setup ----------

    def set_triggers(self, pairs):
        """pairs = [(hotkey_text, macro_name), ...]. Replaces every trigger."""
        new = {}
        for text, name in pairs:
            combo = parse_combo(text)
            if not combo:
                log.warning("Hotkey %r for macro %r has no usable keys, skipped", text, name)
                continue
            if combo in new:
                log.warning("Hotkey %r is used by both %r and %r, keeping the first", text, new[combo], name)
                continue
            new[combo] = name
            log.info("Hotkey registered: %r -> %r (tokens: %s)", text, name, sorted(combo))
        with self._lock:
            self._triggers = new

    def start(self):
        """Safe to call repeatedly. Starts the keyboard hook and controller poller once."""
        if self._started:
            return
        self._started = True
        try:
            import keyboard
            keyboard.hook(self._on_key)
            log.info("Keyboard hook installed")
        except Exception:
            log.exception("Couldn't install the keyboard hook, hotkeys won't work")
        threading.Thread(target=self._controller_loop, daemon=True, name="pad-poll").start()

    # ---------- capture mode (used by the macro editor) ----------

    def begin_capture(self):
        """Next key/button/combo you press and release is reported through `captured`.
        Macros don't fire while capturing."""
        with self._lock:
            self._capturing = True
            self._peak = []

    def end_capture(self):
        with self._lock:
            self._capturing = False
            self._peak = []

    # ---------- core logic (also what the tests exercise) ----------

    def _press(self, token):
        name = None
        with self._lock:
            if token in self._held:
                return                       # key auto-repeat
            self._held.append(token)
            if LOG_EVERY_INPUT:
                log.info("input down: %s (held: %s)", token, self._held)
            if self._capturing:
                if token not in self._peak:
                    self._peak.append(token)
                return
            name = self._triggers.get(frozenset(self._held))
        if name:
            log.info("Hotkey fired: %s -> %r", combo_text(self._held), name)
            self._fire.emit(name)

    def _release(self, token):
        result = None
        with self._lock:
            if token in self._held:
                self._held.remove(token)
            if LOG_EVERY_INPUT:
                log.info("input up: %s", token)
            if self._capturing and self._peak and not self._held:
                result = combo_text(self._peak)
                self._peak = []
                self._capturing = False
        if result is not None:
            log.info("Captured: %r", result)
            self.captured.emit("" if result == "esc" else result)

    @pyqtSlot(str)
    def _dispatch(self, name):
        try:
            if self.on_macro:
                self.on_macro(name)
        except Exception:
            log.exception("Running macro %r from its trigger failed", name)

    # ---------- input sources ----------

    def _on_key(self, event):
        # The keyboard library only prints a raw traceback if this raises, so
        # catch everything and log it properly instead.
        try:
            token = key_token(event.name, getattr(event, "is_keypad", False))
            if token is None:
                return
            if event.event_type == "down":
                self._press(token)
            else:
                self._release(token)
        except Exception:
            log.exception("Error handling a key event")

    def _controller_loop(self):
        xinput = _load_xinput()
        if xinput is None:
            log.info("XInput not available, controller triggers disabled")
            return
        log.info("Controller polling started (XInput)")
        held = [set() for _ in range(4)]
        connected = [False] * 4
        next_probe = [0.0] * 4
        state = _XState()
        while True:
            try:
                now = time.monotonic()
                for i in range(4):
                    if not connected[i] and now < next_probe[i]:
                        continue
                    if xinput.XInputGetState(i, ctypes.byref(state)) != 0:
                        if connected[i]:
                            log.info("Controller %d disconnected", i)
                        connected[i] = False
                        next_probe[i] = now + PROBE_SECONDS
                        for token in held[i]:
                            self._release(token)
                        held[i] = set()
                        continue
                    if not connected[i]:
                        log.info("Controller %d connected", i)
                    connected[i] = True
                    pad = state.Gamepad
                    down = {tok for bit, tok in _PAD_BUTTONS if pad.wButtons & bit}
                    if pad.bLeftTrigger >= TRIGGER_THRESHOLD:
                        down.add("pad:lt")
                    if pad.bRightTrigger >= TRIGGER_THRESHOLD:
                        down.add("pad:rt")
                    for token in sorted(down - held[i]):
                        self._press(token)
                    for token in sorted(held[i] - down):
                        self._release(token)
                    held[i] = down
            except Exception:
                log.exception("Controller polling error")
                time.sleep(1)
            time.sleep(POLL_SECONDS)


_hub = None


def get_hub() -> InputHub:
    """Create it on the GUI thread (main.py's register_hotkeys() call does)."""
    global _hub
    if _hub is None:
        _hub = InputHub()
    return _hub