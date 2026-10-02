"""
SECTION: Assistant
Shows the voice assistant's status and a log of what it heard and said,
plus a mute button that fully releases the microphone.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit
from PyQt6.QtGui import QTextCursor

# ---------- Variables ----------
BTN_STYLE = """
QPushButton {
    background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 8px; padding: 8px;
}
QPushButton:hover { background-color: #21262d; border-color: #00e5ff; }
"""

STATUS_TEXT = {
    "loading": "Loading voice models...",
    "idle": 'Listening for "Hey Jarvis"',
    "listening": "Listening...",
    "thinking": "Thinking...",
    "speaking": "Speaking...",
    "muted": "Muted (mic is off)",
    "error": "Error - check jarvis.log",
}

# ---------- Section contract ----------
NAME = "Assistant"


def create_widget(nav):
    # imported here (not at the top) so the heavy voice libraries don't slow down startup,
    # and a missing dependency shows a message here instead of breaking the whole app
    try:
        from voice.assistant import get_assistant
    except ImportError as e:
        label = QLabel(f"Voice isn't available yet:\n{e}\n\nRun: pip install --user -r requirements.txt")
        label.setWordWrap(True)
        label.setStyleSheet("color: #8b949e;")
        return label
    return AssistantPanel(get_assistant())


# ---------- Widget ----------

class AssistantPanel(QWidget):
    def __init__(self, assistant):
        super().__init__()
        self.assistant = assistant

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)

        self.status = QLabel()
        self.status.setStyleSheet("color: #00e5ff;")
        layout.addWidget(self.status)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet(
            "background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d; border-radius: 8px;"
        )
        layout.addWidget(self.log_view)

        self.mute_btn = QPushButton()
        self.mute_btn.setStyleSheet(BTN_STYLE)
        self.mute_btn.clicked.connect(self._toggle_mute)
        layout.addWidget(self.mute_btn)

        self.log_view.setPlainText("\n".join(assistant.history))
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)
        self._on_state(assistant.state)

        assistant.state_changed.connect(self._on_state)
        assistant.log_line.connect(self.log_view.append)

    def _on_state(self, state):
        self.status.setText(STATUS_TEXT.get(state, state))
        self.mute_btn.setText("Unmute mic" if self.assistant.is_muted() else "Mute mic")

    def _toggle_mute(self):
        self.assistant.set_muted(not self.assistant.is_muted())
        self.mute_btn.setText("Unmute mic" if self.assistant.is_muted() else "Mute mic")