"""
A small always-on-top dot centered on your screen (plus your saved
offset) — a crosshair overlay for games that don't have their own, or
whose reticle doesn't sit exactly at your monitor's true center.

Created once at startup on the main/GUI thread (see main.py). toggle()
is safe to call from any thread, including the voice assistant's.
Settings are adjustable live from the Crosshair section.
"""
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QMetaObject, pyqtSlot

from core.crosshair_store import load_settings

_instance = None


class Crosshair(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # the visible dot is a CHILD widget — a bare top-level QWidget doesn't
        # paint its own stylesheet background without WA_StyledBackground
        self.dot = QWidget(self)
        self.apply_settings(self.settings)

    def apply_settings(self, settings: dict):
        """Live-updates size, color, and position from a settings dict."""
        self.settings = settings
        size = settings["size"]

        self.setFixedSize(size, size)
        self.dot.setGeometry(0, 0, size, size)
        # a thin dark outline keeps it visible against bright backgrounds too
        self.dot.setStyleSheet(
            f"background-color: {settings['color']}; border-radius: {size // 2}px; "
            f"border: 1px solid rgba(0, 0, 0, 160);"
        )

        if self.isVisible():
            self._reposition()

    def _reposition(self):
        screen = QApplication.primaryScreen().geometry()
        cx = screen.center().x() + self.settings["offset_x"]
        cy = screen.center().y() + self.settings["offset_y"]
        self.move(cx - self.width() // 2, cy - self.height() // 2)

    @pyqtSlot()
    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
            return
        self._reposition()
        self.show()

    @pyqtSlot()
    def show_at_current_settings(self):
        """Used by the settings panel so adjustments preview live while it's open."""
        self._reposition()
        if not self.isVisible():
            self.show()


# ---------- Functions ----------

def init():
    """Call once from main.py, on the GUI thread, right after the app starts."""
    global _instance
    _instance = Crosshair()


def get_instance():
    return _instance


def toggle() -> str:
    """Thread-safe — queues the actual show/hide onto the GUI thread."""
    if _instance is None:
        return "Crosshair isn't ready yet, sir."
    QMetaObject.invokeMethod(_instance, "toggle_visibility", Qt.ConnectionType.QueuedConnection)
    return "Toggling the crosshair, sir."