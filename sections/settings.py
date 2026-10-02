"""
SECTION: Settings
General JARVIS settings. Empty for now — a home for future toggles.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

NAME = "Settings"


def create_widget(nav):
    return SettingsPanel()


class SettingsPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        placeholder = QLabel("Nothing here yet - future settings will live in this tab.")
        placeholder.setWordWrap(True)
        placeholder.setStyleSheet("color: #8b949e;")
        layout.addWidget(placeholder)
        layout.addStretch()