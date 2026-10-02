"""
The Orb: a small always-on-top circle you can drag anywhere on screen.
Clicking it toggles the Panel.

The Panel's main menu is auto-built from whatever files exist in
sections/ — to add a whole new top-level category (not just a new
game), copy sections/games.py as a starting point.
"""
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QPushButton, QGraphicsDropShadowEffect, QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont

from core.discovery import load_plugins
from ui.navigation import NavStack

SECTIONS_FOLDER = Path(__file__).resolve().parent.parent / "sections"

ACCENT = "#00e5ff"
BG = "#0d1117"

BTN_STYLE = """
QPushButton {
    background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 8px; padding: 8px; text-align: left;
}
QPushButton:hover { background-color: #21262d; border-color: #00e5ff; }
"""

EXIT_BTN_STYLE = """
QPushButton {
    background-color: #161b22; color: #f85149; border: 1px solid #30363d;
    border-radius: 8px; padding: 8px; text-align: center;
}
QPushButton:hover { background-color: #21262d; border-color: #f85149; }
"""


# What color the orb glows for each assistant state
STATE_COLORS = {
    "loading": "#8b949e",    # grey
    "idle": ACCENT,          # cyan
    "listening": "#3fb950",  # green
    "thinking": "#d29922",   # amber
    "speaking": "#a371f7",   # purple
    "muted": "#6e7681",      # dim grey
    "error": "#f85149",      # red
}


# ---------- Orb ----------

class Orb(QWidget):
    # The window itself is bigger than the visible circle (PADDING on
    # each side) purely so the glow effect has room to render — Windows
    # errors out (UpdateLayeredWindowIndirect) if a layered window's
    # effect tries to paint outside its own bounds.
    VISUAL_SIZE = 64
    PADDING = 40
    SIZE = VISUAL_SIZE  # kept as the "visible" size other files reason about

    def __init__(self):
        super().__init__()
        total = self.VISUAL_SIZE + self.PADDING * 2
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # keeps it off the taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(total, total)

        screen = QApplication.primaryScreen().availableGeometry()
        visual_x = screen.width() - self.VISUAL_SIZE - 40
        visual_y = 60
        self.move(visual_x - self.PADDING, visual_y - self.PADDING)

        # the actual visible circle, centered inside the padded window
        self.circle = QWidget(self)
        self.circle.setGeometry(self.PADDING, self.PADDING, self.VISUAL_SIZE, self.VISUAL_SIZE)
        self.circle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.circle.setStyleSheet(
            f"background-color: rgba(13, 17, 23, 220); border-radius: {self.VISUAL_SIZE // 2}px;"
        )

        self.label = QLabel("J", self.circle)
        self.label.setGeometry(0, 0, self.VISUAL_SIZE, self.VISUAL_SIZE)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        self.label.setStyleSheet(f"color: {ACCENT}; background: transparent;")

        glow = QGraphicsDropShadowEffect(self.circle)
        glow.setColor(QColor(ACCENT))
        glow.setBlurRadius(25)
        glow.setOffset(0, 0)
        self.circle.setGraphicsEffect(glow)

        # subtle pulse, purely cosmetic — stays well under PADDING's room
        self._pulse_step = 0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse)
        self._pulse_timer.start(60)

        self._drag_pos = None
        self._dragged = False
        self.panel = Panel(self)

    def set_state(self, state: str):
        """Recolors the glow and the letter to show what the assistant is doing."""
        color = STATE_COLORS.get(state, ACCENT)
        self.circle.graphicsEffect().setColor(QColor(color))
        self.label.setStyleSheet(f"color: {color}; background: transparent;")

    def _pulse(self):
        self._pulse_step = (self._pulse_step + 1) % 100
        self.circle.graphicsEffect().setBlurRadius(18 + 8 * abs(50 - self._pulse_step) / 50)

    # ---------- Functions (dragging) ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
            self._dragged = False

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            self._dragged = True
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            self.panel.follow_orb()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        if not self._dragged:
            self.panel.toggle()


# ---------- Panel ----------

class Panel(QWidget):
    WIDTH, HEIGHT = 360, 460

    def __init__(self, orb: Orb):
        super().__init__()
        self.orb = orb
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QWidget(self)
        container.setStyleSheet("background-color: rgba(13, 17, 23, 235); border-radius: 14px;")
        outer.addWidget(container)

        inner = QVBoxLayout(container)
        inner.setContentsMargins(12, 12, 12, 12)

        title = QLabel("J.A.R.V.I.S.")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {ACCENT}; letter-spacing: 2px;")
        inner.addWidget(title)

        self.nav = NavStack()
        self.nav.default_size = (self.WIDTH, self.HEIGHT)
        self.nav.on_size_hint = self._resize_panel
        inner.addWidget(self.nav)
        self.nav.reset_to_root(self._build_main_menu(), "Main Menu")

        self.hide()

    def _resize_panel(self, width, height):
        """Called by NavStack when a page wants a different panel size
        (e.g. Macros asking for a wider window to show its list)."""
        self.setFixedSize(width, height)
        if self.isVisible():
            self._reposition()

    def _build_main_menu(self) -> QWidget:
        """Auto-builds the top-level menu from sections/*.py."""
        menu = QWidget()
        layout = QVBoxLayout(menu)
        layout.setSpacing(6)

        sections = load_plugins(SECTIONS_FOLDER)
        for section_module in sections:
            btn = QPushButton(section_module.NAME)
            btn.setStyleSheet(BTN_STYLE)
            btn.clicked.connect(
                lambda checked, m=section_module: self.nav.push(m.create_widget(self.nav), m.NAME)
            )
            layout.addWidget(btn)

        layout.addStretch()

        exit_btn = QPushButton("Exit JARVIS")
        exit_btn.setStyleSheet(EXIT_BTN_STYLE)
        exit_btn.clicked.connect(lambda: QApplication.quit())
        layout.addWidget(exit_btn)

        return menu

    def follow_orb(self):
        if self.isVisible():
            self._reposition()

    def _reposition(self):
        # find whichever monitor the orb is currently on (handles multi-monitor setups)
        screen = QApplication.screenAt(self.orb.geometry().center()) or QApplication.primaryScreen()
        geo = screen.availableGeometry()

        visual_x = self.orb.x() + self.orb.PADDING
        visual_y = self.orb.y() + self.orb.PADDING
        orb_center_x = visual_x + self.orb.VISUAL_SIZE / 2
        orb_center_y = visual_y + self.orb.VISUAL_SIZE / 2
        screen_center_x = geo.x() + geo.width() / 2
        screen_center_y = geo.y() + geo.height() / 2

        gap = 14

        # open toward whichever side of the screen has more room (the
        # center), both horizontally and vertically — this keeps the
        # panel diagonally offset from the orb so it never covers it
        if orb_center_x < screen_center_x:
            x = visual_x + self.orb.VISUAL_SIZE + gap
        else:
            x = visual_x - self.width() - gap

        if orb_center_y < screen_center_y:
            y = visual_y + self.orb.VISUAL_SIZE + gap
        else:
            y = visual_y - self.height() - gap

        x = max(geo.x(), min(x, geo.x() + geo.width() - self.width()))
        y = max(geo.y(), min(y, geo.y() + geo.height() - self.height()))
        self.move(x, y)

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self._reposition()
            self.show()
            self.raise_()
            self.activateWindow()