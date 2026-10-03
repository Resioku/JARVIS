"""
Controller OUTPUT for macros: a virtual Xbox 360 controller that games see as
a real pad. Needs the `vgamepad` package (pip install vgamepad), which sets up
the ViGEmBus driver on Windows. Created lazily the first time a controller
step runs, so nothing here costs anything if you never use one.

Button names: a b x y lb rb lt rt back start ls rs up down left right guide
"""
import importlib.util
import logging
import threading
import time

log = logging.getLogger(__name__)

BUTTON_NAMES = ["a", "b", "x", "y", "lb", "rb", "lt", "rt", "back", "start", "ls", "rs", "up", "down", "left", "right", "guide"]


class PadUnavailable(RuntimeError):
    """Raised (with a message meant for the log) when controller output can't be used."""


_pad = None
_lock = threading.Lock()


def available() -> bool:
    """True if the vgamepad package is installed (does not touch the driver)."""
    return importlib.util.find_spec("vgamepad") is not None


class _Pad:
    def __init__(self, vg):
        self.gp = vg.VX360Gamepad()
        b = vg.XUSB_BUTTON
        self.buttons = {
            "a": b.XUSB_GAMEPAD_A, "b": b.XUSB_GAMEPAD_B, "x": b.XUSB_GAMEPAD_X, "y": b.XUSB_GAMEPAD_Y,
            "lb": b.XUSB_GAMEPAD_LEFT_SHOULDER, "rb": b.XUSB_GAMEPAD_RIGHT_SHOULDER,
            "back": b.XUSB_GAMEPAD_BACK, "start": b.XUSB_GAMEPAD_START,
            "ls": b.XUSB_GAMEPAD_LEFT_THUMB, "rs": b.XUSB_GAMEPAD_RIGHT_THUMB,
            "up": b.XUSB_GAMEPAD_DPAD_UP, "down": b.XUSB_GAMEPAD_DPAD_DOWN,
            "left": b.XUSB_GAMEPAD_DPAD_LEFT, "right": b.XUSB_GAMEPAD_DPAD_RIGHT,
            "guide": b.XUSB_GAMEPAD_GUIDE,
        }

    def press(self, name):
        if name == "lt":
            self.gp.left_trigger_float(value_float=1.0)
        elif name == "rt":
            self.gp.right_trigger_float(value_float=1.0)
        else:
            self.gp.press_button(button=self.buttons[name])
        self.gp.update()

    def release(self, name):
        if name == "lt":
            self.gp.left_trigger_float(value_float=0.0)
        elif name == "rt":
            self.gp.right_trigger_float(value_float=0.0)
        else:
            self.gp.release_button(button=self.buttons[name])
        self.gp.update()

    def stick(self, which, x, y):
        if which == "left":
            self.gp.left_joystick_float(x_value_float=x, y_value_float=y)
        else:
            self.gp.right_joystick_float(x_value_float=x, y_value_float=y)
        self.gp.update()


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