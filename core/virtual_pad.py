"""
Controller OUTPUT for macros, through a virtual Xbox 360 controller
(`vgamepad` package + the ViGEmBus driver).

IMPORTANT - why this exists the way it does: keyboard and mouse have one
shared input stream that any program can add to, which is why keyboard/mouse
macros "just work". Controllers don't: each pad is its own device and Windows
has no way to add presses to a real one. So macros press buttons on a
VIRTUAL controller, and a game only sees them if it is reading that virtual
controller.

Two modes:
  - Normal: the virtual controller only carries macro presses. Works for games
    that listen to every controller, or when no real controller is plugged in.
  - Passthrough (settings.PAD_PASSTHROUGH = True): the virtual controller ALSO
    mirrors your real controller (sticks, triggers, buttons), with macro
    presses added on top. Hide the real controller from the game with HidHide
    and the game plays through the virtual one: your real inputs and your
    macros arrive together, as if it were one controller.

Button names: a b x y lb rb lt rt back start ls rs up down left right guide
"""
import importlib.util
import logging
import threading
import time

log = logging.getLogger(__name__)

BUTTON_NAMES = ["a", "b", "x", "y", "lb", "rb", "lt", "rt", "back", "start", "ls", "rs", "up", "down", "left", "right", "guide"]
FORWARD_SLEEP = 0.004          # passthrough polls the real controller about 250 times a second

# the standard XInput button bits (the same values vgamepad uses)
MASKS = {
    "up": 0x0001, "down": 0x0002, "left": 0x0004, "right": 0x0008, "start": 0x0010, "back": 0x0020,
    "ls": 0x0040, "rs": 0x0080, "lb": 0x0100, "rb": 0x0200, "guide": 0x0400,
    "a": 0x1000, "b": 0x2000, "x": 0x4000, "y": 0x8000,
}


class PadUnavailable(RuntimeError):
    """Raised (with a message meant for the log) when controller output can't be used."""


_pad = None
_lock = threading.Lock()
_forwarding = False
_forward_stop = threading.Event()


def available() -> bool:
    """True if the vgamepad package is installed (does not touch the driver)."""
    return importlib.util.find_spec("vgamepad") is not None


def _short(value):
    return int(max(-1.0, min(1.0, float(value))) * 32767)


class _Pad:
    """The virtual controller. Its output is always: real controller (when passing through)
    combined with whatever macros are currently holding."""

    def __init__(self, vg):
        self.gp = vg.VX360Gamepad()
        self.lock = threading.RLock()
        self.buttons = set()                              # held by macros
        self.sticks = {"left": (0.0, 0.0), "right": (0.0, 0.0)}
        self.real = None                                  # (buttons, lt, rt, lx, ly, rx, ry) of the real pad, or None
        self._last = None

    def set_real(self, real):
        with self.lock:
            self.real = real
            self._send()

    def _send(self):
        with self.lock:
            buttons, lt, rt, lx, ly, rx, ry = self.real or (0, 0, 0, 0, 0, 0, 0)
            for name in self.buttons:
                if name == "lt":
                    lt = 255
                elif name == "rt":
                    rt = 255
                else:
                    buttons |= MASKS[name]
            sx, sy = self.sticks["left"]
            if sx or sy:                                   # a macro tilting a stick wins over the real stick
                lx, ly = _short(sx), _short(sy)
            sx, sy = self.sticks["right"]
            if sx or sy:
                rx, ry = _short(sx), _short(sy)
            packet = (buttons, lt, rt, lx, ly, rx, ry)
            if packet == self._last:
                return
            self._last = packet
            rep = self.gp.report
            rep.wButtons, rep.bLeftTrigger, rep.bRightTrigger = buttons, lt, rt
            rep.sThumbLX, rep.sThumbLY, rep.sThumbRX, rep.sThumbRY = lx, ly, rx, ry
            self.gp.update()

    def press(self, name):
        if name not in MASKS and name not in ("lt", "rt"):
            raise PadUnavailable(f"Unknown controller button '{name}'")
        with self.lock:
            self.buttons.add(name)
            self._send()

    def release(self, name):
        with self.lock:
            self.buttons.discard(name)
            self._send()

    def stick(self, which, x, y):
        with self.lock:
            self.sticks[which] = (float(x), float(y))
            self._send()


def _get():
    global _pad
    with _lock:
        if _pad is not None:
            return _pad
        try:
            import vgamepad as vg
        except ImportError as e:
            raise PadUnavailable("Controller steps need the 'vgamepad' package: pip install vgamepad") from e

        # remember which XInput slots exist, so we can tell which one is OUR virtual pad
        # and keep it from triggering macros
        from core.input_hub import get_hub
        hub = get_hub()
        before = set(hub.connected_slots())
        try:
            _pad = _Pad(vg)
        except Exception as e:
            raise PadUnavailable(f"Couldn't create the virtual controller ({e}). Is the ViGEmBus driver installed?") from e
        hub.probe_now()
        time.sleep(0.4)
        new = set(hub.connected_slots()) - before
        hub.ignore_slots |= new
        log.info("Virtual controller created (XInput slot(s) %s ignored for triggers)", sorted(new) or "unknown")
        return _pad


def press(name):
    _get().press(name)


def release(name):
    _get().release(name)


def stick(which, x, y):
    _get().stick(which, x, y)


# ---------- Passthrough ----------

def _forward_loop(pad):
    import ctypes
    from core.input_hub import _XState, _load_xinput, get_hub
    xinput = _load_xinput()
    if xinput is None:
        log.error("Passthrough needs XInput (Windows)")
        return
    hub = get_hub()
    state = _XState()
    log.info("Controller passthrough is ON: your real controller is mirrored through the virtual one")
    last_slot = None
    while not _forward_stop.is_set():
        try:
            real = None
            candidates = [i for i in hub.connected_slots() if i not in hub.ignore_slots]
            if candidates and xinput.XInputGetState(candidates[0], ctypes.byref(state)) == 0:
                g = state.Gamepad
                real = (g.wButtons, g.bLeftTrigger, g.bRightTrigger, g.sThumbLX, g.sThumbLY, g.sThumbRX, g.sThumbRY)
                if candidates[0] != last_slot:
                    last_slot = candidates[0]
                    log.info("Passthrough is mirroring the real controller in XInput slot %d", last_slot)
            pad.set_real(real)
        except Exception:
            log.exception("Passthrough error")
            time.sleep(1)
        time.sleep(FORWARD_SLEEP)


def start_passthrough():
    """Creates the virtual controller now and starts mirroring the real one through it.
    Safe to call repeatedly."""
    global _forwarding
    if _forwarding:
        return
    pad = _get()                       # raises PadUnavailable with a clear message if it can't
    _forwarding = True
    _forward_stop.clear()
    threading.Thread(target=_forward_loop, args=(pad,), daemon=True, name="pad-passthrough").start()