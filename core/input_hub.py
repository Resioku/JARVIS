"""
One listener for ALL macro triggers and for recording: keyboard keys (numpad
kept separate from the top-row digits), mouse buttons, and XInput controllers
(Xbox pads, or anything Steam Input / DS4Windows presents as one).

Every input becomes a text "token":
    keyboard:    "x", "f5", "ctrl", "num 1", "num add", "num enter"
    mouse:       "mouse:left", "mouse:right", "mouse:middle", "mouse:x", "mouse:x2"
    controller:  "pad:a", "pad:rb", "pad:lt", "pad:up", "pad:start" ...
A trigger is tokens joined with "+", e.g. "x", "ctrl+num 1", "pad:lb+pad:a",
"mouse:x2". It fires when EXACTLY those tokens are held, and ends when any of
them is let go (that end is what "loop while held" macros listen for).

Everything that happens is written to jarvis.log (registrations, fires).
"""
import ctypes
import logging
import sys
import threading
import time

from PyQt6.QtCore import QCoreApplication, QObject, QThread, pyqtSignal, pyqtSlot

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
_MOUSE_BUTTONS = ("left", "right", "middle", "x", "x2")

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
    if name.startswith(("pad:", "mouse:")):
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
    _unfire = pyqtSignal(str)
    captured = pyqtSignal(str)    # a finished capture; "" means cancelled/cleared (Esc)

    def __init__(self):
        super().__init__()
        self.on_macro = None           # called on the GUI thread with a macro name when its trigger goes down
        self.on_macro_release = None   # ...and when its trigger is let go
        self.ignore_slots = set()      # XInput slots to ignore (our own virtual controller)
        self._lock = threading.Lock()
        self._held = []                # tokens currently down, in press order
        self._triggers = {}            # frozenset(tokens) -> macro name
        self._active = {}              # triggers currently held down
        self._capturing = False
        self._allow_esc = False
        self._muted = False
        self._peak = []
        self._raw = []                 # recorder callbacks: fn(token, is_down, time)
        self._connected = [False] * 4
        self._next_probe = [0.0] * 4
        self._started = False
        self._fire.connect(self._dispatch)
        self._unfire.connect(self._dispatch_release)

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
            self._active = {}

    def start(self):
        """Safe to call repeatedly. Starts keyboard, mouse-button and controller listening once."""
        if self._started:
            return
        self._started = True
        try:
            import keyboard
            keyboard.hook(self._on_key)
            log.info("Keyboard hook installed")
        except Exception:
            log.exception("Couldn't install the keyboard hook, hotkeys won't work")
        try:
            import mouse
            for button in _MOUSE_BUTTONS:
                for kind in ("down", "up"):
                    mouse.on_button(self._on_mouse, args=(button, kind), buttons=(button,), types=(kind,))
            log.info("Mouse button hook installed")
        except Exception:
            log.exception("Couldn't install the mouse button hook, mouse triggers won't work")
        threading.Thread(target=self._controller_loop, daemon=True, name="pad-poll").start()

    def set_muted(self, muted):
        """While muted, nothing fires macros (used while recording)."""
        with self._lock:
            self._muted = muted

    def add_raw_listener(self, fn):
        self._raw.append(fn)

    def remove_raw_listener(self, fn):
        if fn in self._raw:
            self._raw.remove(fn)

    def connected_slots(self):
        return [i for i, ok in enumerate(self._connected) if ok]

    def probe_now(self):
        """Look for newly plugged-in controllers right away instead of waiting."""
        self._next_probe = [0.0] * 4

    # ---------- capture mode (used by the macro editor) ----------

    def begin_capture(self, allow_esc=False):
        """Next key/button/combo you press and release is reported through `captured`.
        Esc cancels (reported as "") unless allow_esc. Macros don't fire while capturing."""
        with self._lock:
            self._capturing = True
            self._allow_esc = allow_esc
            self._peak = []

    def end_capture(self):
        with self._lock:
            self._capturing = False
            self._peak = []

    # ---------- core logic (also what the tests exercise) ----------

    def _notify_raw(self, token, down):
        for fn in list(self._raw):
            try:
                fn(token, down, time.monotonic())
            except Exception:
                log.exception("Input listener failed")

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
            elif not self._muted:
                combo = frozenset(self._held)
                name = self._triggers.get(combo)
                if name:
                    self._active[combo] = name
        self._notify_raw(token, True)
        if name:
            log.info("Hotkey fired: %s -> %r", combo_text(self._held), name)
            self._fire.emit(name)

    def _release(self, token):
        result = None
        ended = []
        with self._lock:
            if token in self._held:
                self._held.remove(token)
            held = set(self._held)
            for combo, name in list(self._active.items()):
                if not combo <= held:
                    del self._active[combo]
                    ended.append(name)
            if LOG_EVERY_INPUT:
                log.info("input up: %s", token)
            if self._capturing and self._peak and not self._held:
                result = combo_text(self._peak)
                self._peak = []
                self._capturing = False
        self._notify_raw(token, False)
        for name in ended:
            self._unfire.emit(name)
        if result is not None:
            log.info("Captured: %r", result)
            self.captured.emit("" if (result == "esc" and not self._allow_esc) else result)

    @pyqtSlot(str)
    def _dispatch(self, name):
        try:
            if self.on_macro:
                self.on_macro(name)
        except Exception:
            log.exception("Running macro %r from its trigger failed", name)

    @pyqtSlot(str)
    def _dispatch_release(self, name):
        try:
            if self.on_macro_release:
                self.on_macro_release(name)
        except Exception:
            log.exception("Handling the release of %r's trigger failed", name)

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

    def _on_mouse(self, button, kind):
        try:
            token = f"mouse:{button}"
            if kind == "down":
                self._press(token)
            else:
                self._release(token)
        except Exception:
            log.exception("Error handling a mouse event")

    def _controller_loop(self):
        xinput = _load_xinput()
        if xinput is None:
            log.info("XInput not available, controller triggers disabled")
            return
        log.info("Controller polling started (XInput)")
        held = [set() for _ in range(4)]
        state = _XState()
        while True:
            try:
                now = time.monotonic()
                for i in range(4):
                    if not self._connected[i] and now < self._next_probe[i]:
                        continue
                    if xinput.XInputGetState(i, ctypes.byref(state)) != 0:
                        if self._connected[i]:
                            log.info("Controller %d disconnected", i)
                        self._connected[i] = False
                        self._next_probe[i] = now + PROBE_SECONDS
                        for token in held[i]:
                            self._release(token)
                        held[i] = set()
                        continue
                    if not self._connected[i]:
                        log.info("Controller %d connected", i)
                    self._connected[i] = True
                    pad = state.Gamepad
                    down = {tok for bit, tok in _PAD_BUTTONS if pad.wButtons & bit}
                    if pad.bLeftTrigger >= TRIGGER_THRESHOLD:
                        down.add("pad:lt")
                    if pad.bRightTrigger >= TRIGGER_THRESHOLD:
                        down.add("pad:rt")
                    if i in self.ignore_slots:
                        down = set()       # our own virtual controller must never trigger macros
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
    """The one shared hub. register_hotkeys() in main.py creates it on the GUI thread at startup."""
    global _hub
    if _hub is None:
        _hub = InputHub()
        # signals only reach the GUI thread if the hub lives there, even if some
        # worker thread happened to be the first to ask for it
        app = QCoreApplication.instance()
        if app is not None and QThread.currentThread() is not app.thread():
            _hub.moveToThread(app.thread())
    return _hub