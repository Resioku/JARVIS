"""
SECTION: Games
Auto-scans the games/ folder — every file in there that follows the
plugin contract (NAME + create_widget) shows up here automatically.
To add a new game: copy games/clicker.py, rename it, edit the logic.
Nothing in this file ever needs to change.
"""
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from core.discovery import load_plugins

GAMES_FOLDER = Path(__file__).resolve().parent.parent / "games"

BTN_STYLE = """
QPushButton {
    background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 8px; padding: 8px; text-align: left;
}
QPushButton:hover { background-color: #21262d; border-color: #00e5ff; }
"""

# ---------- Section contract ----------
NAME = "Games"


def create_widget(nav):
    return GamesList(nav)


# ---------- Widget ----------

class GamesList(QWidget):
    def __init__(self, nav):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        games = load_plugins(GAMES_FOLDER)
        if not games:
            empty = QLabel("No games found in /games.")
            empty.setStyleSheet("color: #8b949e;")
            layout.addWidget(empty)
            return

        for game_module in games:
            btn = QPushButton(game_module.NAME)
            btn.setStyleSheet(BTN_STYLE)
            btn.clicked.connect(lambda checked, m=game_module: nav.push(m.create_widget(), m.NAME))
            layout.addWidget(btn)

        layout.addStretch()
