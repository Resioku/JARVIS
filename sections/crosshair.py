"""
SECTION: Crosshair
Adjust the on-screen crosshair overlay: position offset (since a game's
own reticle might not sit exactly at your monitor's true center), size,
and color. Changes preview live. Say "Hey Jarvis, crosshair" to toggle
it on/off any time, from anywhere.
"""
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QColorDialog
)

from core.crosshair_store import load_settings, save_settings
from ui.crosshair import get_instance, toggle

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
if not (_ASSETS_DIR / "spin_up.png").exists():
    from scripts.generate_spin_arrows import generate as _generate_spin_arrows
    _generate_spin_arrows()
_UP_ICON = (_ASSETS_DIR / "spin_up.png").as_posix()
_DOWN_ICON = (_ASSETS_DIR / "spin_down.png").as_posix()

BTN_STYLE = """
QPushButton {
    background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 8px; padding: 6px;
}
QPushButton:hover { background-color: #21262d; border-color: #00e5ff; }
"""

SPIN_STYLE = f"""
QSpinBox {{
    background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 6px; padding: 2px 4px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 18px; background-color: #21262d;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background-color: #30363d; }}
QSpinBox::up-arrow {{ image: url({_UP_ICON}); width: 8px; height: 8px; }}
QSpinBox::down-arrow {{ image: url({_DOWN_ICON}); width: 8px; height: 8px; }}
"""

NAME = "Crosshair"


def create_widget(nav):
    return CrosshairSettings()


class CrosshairSettings(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.crosshair = get_instance()
        self.spinboxes = {}

        layout = QVBoxLayout(self)

        hint = QLabel(
            'Say "Hey Jarvis, crosshair" to toggle it on/off. If it doesn\'t '
            "line up with a game's own reticle, nudge the offset below."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b949e;")
        layout.addWidget(hint)

        toggle_btn = QPushButton("Show / hide crosshair")
        toggle_btn.setStyleSheet(BTN_STYLE)
        toggle_btn.clicked.connect(lambda: toggle())
        layout.addWidget(toggle_btn)

        layout.addWidget(self._labeled_row("Horizontal offset", "offset_x", -1000, 1000))
        layout.addWidget(self._labeled_row("Vertical offset", "offset_y", -1000, 1000))
        layout.addWidget(self._labeled_row("Size", "size", 4, 100))

        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Color:"))
        self.color_btn = QPushButton()
        self.color_btn.setFixedWidth(60)
        self._update_color_btn()
        self.color_btn.clicked.connect(self._pick_color)
        color_row.addWidget(self.color_btn)
        color_row.addStretch()
        layout.addLayout(color_row)

        reset_btn = QPushButton("Reset to screen center")
        reset_btn.setStyleSheet(BTN_STYLE)
        reset_btn.clicked.connect(self._reset)
        layout.addWidget(reset_btn)

        layout.addStretch()

    def _labeled_row(self, label_text, key, minimum, maximum):
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(label_text))

        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(self.settings[key])
        spin.setFixedWidth(90)   # a stretched-wide spinbox was throwing off the up/down button hit area
        spin.setStyleSheet(SPIN_STYLE)
        spin.valueChanged.connect(lambda v, k=key: self._update(k, v))
        row.addWidget(spin)
        row.addStretch()
        self.spinboxes[key] = spin
        return row_widget

    def _update(self, key, value):
        self.settings[key] = value
        save_settings(self.settings)
        self._apply_live()

    def _pick_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.settings["color"] = color.name()
            save_settings(self.settings)
            self._update_color_btn()
            self._apply_live()

    def _update_color_btn(self):
        self.color_btn.setStyleSheet(f"background-color: {self.settings['color']}; border-radius: 4px;")

    def _reset(self):
        self.settings["offset_x"] = 0
        self.settings["offset_y"] = 0
        save_settings(self.settings)
        self.spinboxes["offset_x"].setValue(0)   # triggers _update via valueChanged, which also applies + saves
        self.spinboxes["offset_y"].setValue(0)

    def _apply_live(self):
        """Previews the change immediately, showing the crosshair if it was hidden."""
        if self.crosshair:
            self.crosshair.apply_settings(self.settings)
            self.crosshair.show_at_current_settings()