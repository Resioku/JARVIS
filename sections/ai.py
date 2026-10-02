"""
SECTION: AI
Pick which AI provider handles questions, and test it with a text box.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QComboBox, QLineEdit, QPushButton, QLabel
from ai.selector import list_providers, get_active_name, set_active

BTN_STYLE = """
QPushButton { background-color:#161b22; color:#c9d1d9; border:1px solid #30363d; border-radius:8px; padding:8px; }
QPushButton:hover { background-color:#21262d; border-color:#00e5ff; }
"""

NAME = "AI"


def create_widget(nav):
    return AIPanel()


class AIPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Active AI:"))
        self.dropdown = QComboBox()
        self.providers = list_providers()
        self.dropdown.addItems([p.NAME for p in self.providers])
        active = get_active_name()
        if active in [p.NAME for p in self.providers]:
            self.dropdown.setCurrentText(active)
        self.dropdown.currentTextChanged.connect(set_active)
        layout.addWidget(self.dropdown)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a test question...")
        layout.addWidget(self.input)

        ask_btn = QPushButton("Ask")
        ask_btn.setStyleSheet(BTN_STYLE)
        ask_btn.clicked.connect(self._ask)
        layout.addWidget(ask_btn)

        self.output = QLabel("")
        self.output.setWordWrap(True)
        self.output.setStyleSheet("color:#8b949e;")
        layout.addWidget(self.output)
        layout.addStretch()

    def _ask(self):
        from ai.selector import ask_active
        self.output.setText("Thinking...")
        self.output.setText(ask_active(self.input.text()))