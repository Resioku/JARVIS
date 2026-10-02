"""
NavStack is the "screen manager" for the panel. Every section/game just
hands it a QWidget and NavStack takes care of showing it, adding a Back
button, and remembering where you came from.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStackedWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

ACCENT = "#00e5ff"

HEADER_BTN_STYLE = f"""
QPushButton {{
    background: transparent; color: {ACCENT}; border: none; font-size: 16px;
}}
QPushButton:hover {{ color: white; }}
"""


class NavStack(QWidget):
    def __init__(self):
        super().__init__()
        self._stack_data = []  # list of (widget, title) — mirrors QStackedWidget's pages
        self.on_size_hint = None   # set by Panel: called with (width, height) when a page wants a different panel size
        self.default_size = None   # set by Panel: the size to fall back to when a page doesn't request one

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ---------- Header (back button + current title) ----------
        header = QHBoxLayout()
        self.back_btn = QPushButton("<")
        self.back_btn.setStyleSheet(HEADER_BTN_STYLE)
        self.back_btn.setFixedWidth(24)
        self.back_btn.clicked.connect(self.pop)
        self.back_btn.hide()

        self.title_label = QLabel("")
        self.title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #c9d1d9;")

        header.addWidget(self.back_btn)
        header.addWidget(self.title_label)
        header.addStretch()
        layout.addLayout(header)

        # ---------- Page container ----------
        self.stacked = QStackedWidget()
        layout.addWidget(self.stacked)

    # ---------- Functions ----------

    def push(self, widget: QWidget, title: str):
        """Show a new page, remembering the previous one for Back."""
        self._stack_data.append((widget, title))
        self.stacked.addWidget(widget)
        self.stacked.setCurrentWidget(widget)
        self.title_label.setText(title)
        self.back_btn.setVisible(len(self._stack_data) > 1)
        self._apply_size_hint(widget)

    def pop(self):
        """Go back one page. Does nothing if already at the root."""
        if len(self._stack_data) <= 1:
            return
        old_widget, _ = self._stack_data.pop()
        self.stacked.removeWidget(old_widget)
        old_widget.deleteLater()

        widget, title = self._stack_data[-1]
        self.stacked.setCurrentIndex(self.stacked.count() - 1)
        self.title_label.setText(title)
        self.back_btn.setVisible(len(self._stack_data) > 1)
        self._apply_size_hint(widget)

    def _apply_size_hint(self, widget):
        """A page can set a class attribute PANEL_SIZE = (width, height)
        to make the panel wider/taller while it's shown (see sections/
        macros.py for an example). Pages without it use the default size."""
        if self.on_size_hint:
            size = getattr(widget, "PANEL_SIZE", self.default_size)
            if size:
                self.on_size_hint(*size)

    def reset_to_root(self, widget: QWidget, title: str):
        """Clear everything and start fresh at the main menu."""
        while self._stack_data:
            w, _ = self._stack_data.pop()
            self.stacked.removeWidget(w)
            w.deleteLater()
        self.push(widget, title)