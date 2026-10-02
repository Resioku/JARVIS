"""
JARVIS
Boots the always-on-top orb and the voice assistant. Everything else
lives in its own file. See README.md for how to add sections/games/links,
and settings.py for the voice knobs.
"""
import logging
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

# ---------- Logging ----------
# Everything goes to jarvis.log next to this file (recreated each launch).
# pythonw has no console, so its prints and errors get sent to the log too.
LOG_PATH = Path(__file__).resolve().parent / "jarvis.log"
file_handler = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
handlers = [file_handler]
if sys.stderr is not None:
    handlers.append(logging.StreamHandler(sys.stderr))   # also visible when run from a terminal
else:
    sys.stdout = sys.stderr = file_handler.stream
logging.basicConfig(level=logging.INFO, handlers=handlers,
                    format="%(asctime)s %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("main")

from ui.overlay import Orb


# ---------- Functions ----------

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")   # draws clean, properly-aligned controls (e.g. spinbox arrows) consistently
    app.setQuitOnLastWindowClosed(False)  # closing the panel shouldn't kill the orb

    orb = Orb()
    orb.show()

    from ui.crosshair import init as init_crosshair
    init_crosshair()   # must be created on the GUI thread, before voice can toggle it

    app.processEvents()   # paint the orb before the heavy voice libraries load

    try:
        from core.macro_runner import register_hotkeys
        register_hotkeys()
    except ImportError:
        log.exception("`keyboard` library missing, macro hotkeys won't work. Run: pip install --user -r requirements.txt")

    try:
        from voice.assistant import get_assistant
        assistant = get_assistant()
        assistant.state_changed.connect(orb.set_state)   # orb color follows what it's doing
        app.aboutToQuit.connect(assistant.stop)
        assistant.start()
    except ImportError:
        log.exception("Voice libraries missing, running without voice. Run: pip install --user -r requirements.txt")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()