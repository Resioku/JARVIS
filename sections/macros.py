"""
SECTION: Macros
Build a macro by hand: "+ Add input" taps a key or mouse button, "+ Hold for
time" holds one for a set number of milliseconds, "+ Hold down" / "+ Release"
hold something across other steps, and "+ Add wait" pauses. Optionally bind a
trigger (a key, a key combo, or a controller button) and turn on "Loop until
stopped" for something like an autoclicker. Every saved macro is also a
voice command automatically.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QListWidget, QScrollArea, QInputDialog, QCheckBox
)
from PyQt6.QtGui import QKeySequence
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from core.macro_store import load_macros, save_macros

BTN_STYLE = """
QPushButton {
    background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 8px; padding: 6px;
}
QPushButton:hover { background-color: #21262d; border-color: #00e5ff; }
"""
STOP_BTN_STYLE = """
QPushButton {
    background-color: #161b22; color: #f85149; border: 1px solid #30363d;
    border-radius: 8px; padding: 6px;
}
QPushButton:hover { background-color: #21262d; border-color: #f85149; }
"""

MIN_WAIT_MS = 10   # matches core/macro_runner.py's built-in floor

# translates Qt's key-name strings into the names the `keyboard` library expects
QT_KEY_OVERRIDES = {
    "Esc": "esc", "Return": "enter", "Enter": "enter", "Space": "space",
    "Backspace": "backspace", "Delete": "delete", "Tab": "tab",
    "Up": "up", "Down": "down", "Left": "left", "Right": "right",
}

MODIFIER_KEYS = {
    Qt.Key.Key_Shift: "shift",
    Qt.Key.Key_Control: "ctrl",
    Qt.Key.Key_Alt: "alt",
    Qt.Key.Key_Meta: "windows",
}

# numpad names used when a numpad key is captured as a STEP (the `keyboard`
# library can only replay these as the matching digit/operator)
NUMPAD_KEY_NAMES = {
    Qt.Key.Key_0: "num 0", Qt.Key.Key_1: "num 1", Qt.Key.Key_2: "num 2",
    Qt.Key.Key_3: "num 3", Qt.Key.Key_4: "num 4", Qt.Key.Key_5: "num 5",
    Qt.Key.Key_6: "num 6", Qt.Key.Key_7: "num 7", Qt.Key.Key_8: "num 8",
    Qt.Key.Key_9: "num 9", Qt.Key.Key_Plus: "num add", Qt.Key.Key_Minus: "num sub",
    Qt.Key.Key_Asterisk: "num multiply", Qt.Key.Key_Slash: "num divide",
    Qt.Key.Key_Enter: "num enter",
}

SAMPLES = {
    "Blank": [],
    "Autoclicker (10 clicks)": [{"type": "click"}, {"type": "wait", "ms": 200}] * 10,
    "Copy && Paste (Ctrl+C / Ctrl+V)": [
        {"type": "key", "key": "ctrl+c"},
        {"type": "wait", "ms": 100},
        {"type": "key", "key": "ctrl+v"},
    ],
    "Hold W for 2 seconds": [{"type": "hold", "key": "w", "ms": 2000}],
}

CAPTURE_HINTS = {
    "tap": "Press any key or click any mouse button (hold Shift/Ctrl/Alt for a combo, Esc cancels)...",
    "hold": "Press the key or button to HOLD (you'll set how long next, Esc cancels)...",
    "down": "Press the key or button to HOLD DOWN until a Release step (Esc cancels)...",
    "up": "Press the key or button to RELEASE (Esc cancels)...",
}


def _qt_key_to_name(qt_key: int) -> str:
    raw = QKeySequence(qt_key).toString()
    return QT_KEY_OVERRIDES.get(raw, raw.lower())


def _resolve_key_name(qt_key: int, modifiers) -> str:
    """Like _qt_key_to_name, but checks for the numpad modifier first."""
    if modifiers & Qt.KeyboardModifier.KeypadModifier and qt_key in NUMPAD_KEY_NAMES:
        return NUMPAD_KEY_NAMES[qt_key]
    return _qt_key_to_name(qt_key)


# ---------- Section contract ----------
NAME = "Macros"


def create_widget(nav):
    return MacroList(nav)


# ---------- Widgets ----------

class MacroList(QWidget):
    # a wider panel for this page so the list and its Run/Edit/Delete
    # buttons have room to breathe - Panel reads this automatically
    PANEL_SIZE = (560, 460)

    def __init__(self, nav):
        super().__init__()
        self.nav = nav
        self._run_buttons = {}   # macro name -> its Run/Stop button, for the periodic refresh

        layout = QVBoxLayout(self)

        hint = QLabel(
            'Voice: say a macro\'s name - "Hey Jarvis, run <name>". '
            'For a looping macro, say "stop" (or "stop <name>") to end it.'
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b949e;")
        layout.addWidget(hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.scroll)

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setSpacing(6)
        self.scroll.setWidget(self.list_container)

        new_btn = QPushButton("+ New macro")
        new_btn.setStyleSheet(BTN_STYLE)
        new_btn.clicked.connect(self.new_macro)
        layout.addWidget(new_btn)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #d29922;")
        layout.addWidget(self.status_label)

        # keeps Run/Stop button labels in sync if a loop is toggled via hotkey or voice
        self._label_timer = QTimer(self)
        self._label_timer.timeout.connect(self._refresh_run_labels)
        self._label_timer.start(1000)

        self.refresh()

    def refresh(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._run_buttons = {}

        macros = load_macros()
        if not macros:
            empty = QLabel("No macros yet - create one below.")
            empty.setStyleSheet("color: #8b949e;")
            self.list_layout.addWidget(empty)
        else:
            for macro in macros:
                self.list_layout.addWidget(self._build_row(macro))

        self.list_layout.addStretch()

    def _build_row(self, macro):
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)

        label_text = macro["name"]
        if macro.get("hotkey"):
            label_text += f"  [{macro['hotkey']}]"
        if macro.get("loop"):
            label_text += "  (loop)"
        label = QLabel(label_text)
        label.setStyleSheet("color: #c9d1d9;")
        row.addWidget(label, 1)

        run_btn = QPushButton()
        run_btn.clicked.connect(lambda checked, m=macro: self.run_macro(m))
        row.addWidget(run_btn)
        self._run_buttons[macro["name"]] = run_btn

        edit_btn = QPushButton("Edit")
        edit_btn.setStyleSheet(BTN_STYLE)
        edit_btn.clicked.connect(lambda checked, m=macro: self.edit_macro(m))
        row.addWidget(edit_btn)

        del_btn = QPushButton("Delete")
        del_btn.setStyleSheet(BTN_STYLE)
        del_btn.clicked.connect(lambda checked, m=macro: self.delete_macro(m))
        row.addWidget(del_btn)

        self._style_run_button(macro, run_btn)
        return row_widget

    def _style_run_button(self, macro, btn):
        try:
            from core.macro_runner import is_running
            running = macro.get("loop") and is_running(macro["name"])
        except ImportError:
            running = False
        btn.setText("Stop" if running else "Run")
        btn.setStyleSheet(STOP_BTN_STYLE if running else BTN_STYLE)

    def _refresh_run_labels(self):
        macros = {m["name"]: m for m in load_macros()}
        for name, btn in self._run_buttons.items():
            if name in macros:
                self._style_run_button(macros[name], btn)

    def new_macro(self):
        choice, ok = QInputDialog.getItem(
            self, "New Macro", "Start from:", list(SAMPLES.keys()), 0, False
        )
        if not ok:
            return
        starter_steps = [dict(s) for s in SAMPLES[choice]]
        self.nav.push(MacroEditor(self.nav, None, starter_steps, self.refresh), "New Macro")

    def edit_macro(self, macro):
        self.nav.push(MacroEditor(self.nav, macro, list(macro["steps"]), self.refresh), macro["name"])

    def delete_macro(self, macro):
        save_macros([m for m in load_macros() if m["name"] != macro["name"]])
        self._reregister_hotkeys()
        self.refresh()

    def run_macro(self, macro):
        try:
            from core.macro_runner import is_running, trigger_macro
        except ImportError:
            self.status_label.setText("Install requirements.txt first (`keyboard`/`mouse` missing).")
            return

        # stopping a loop is instant - no need to wait or switch windows for that
        if macro.get("loop") and is_running(macro["name"]):
            self.status_label.setText(trigger_macro(macro))
            self._refresh_run_labels()
            return

        self.status_label.setText(f'Switch to the target window - running "{macro["name"]}" in 3 seconds...')
        QTimer.singleShot(3000, lambda m=macro: self._start_trigger(m))

    def _start_trigger(self, macro):
        from core.macro_runner import trigger_macro
        self.status_label.setText(trigger_macro(macro))
        self._refresh_run_labels()

    def _reregister_hotkeys(self):
        try:
            from core.macro_runner import register_hotkeys
            register_hotkeys()
        except ImportError:
            pass


class MacroEditor(QWidget):
    """Add key/click/hold/wait steps, optionally set a trigger and loop, then save."""

    PANEL_SIZE = (560, 460)
    _mouse_captured = pyqtSignal(str)   # emitted from the `mouse` library's own thread; Qt queues it safely to this widget's thread

    def __init__(self, nav, macro, starter_steps, on_saved):
        super().__init__()
        self.nav = nav
        self.on_saved = on_saved
        self.original_name = macro["name"] if macro else None
        self.steps = starter_steps
        self.hotkey = macro.get("hotkey") if macro else None
        self._listening_input = False
        self._capture_mode = "tap"       # tap / hold / down / up - what the next captured input becomes
        self._held_modifiers = []
        self._mouse_handlers = []

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._mouse_captured.connect(self._on_mouse_captured)

        # triggers (keys, combos, controller buttons) are captured by the input hub,
        # which sees exactly what will later fire the macro
        from core.input_hub import get_hub
        self._hub = get_hub()
        self._hub.captured.connect(self._on_hotkey_captured)
        self.destroyed.connect(lambda *_, hub=self._hub: hub.end_capture())

        layout = QVBoxLayout(self)

        self.name_input = QLineEdit(macro["name"] if macro else "")
        self.name_input.setPlaceholderText("Macro name")
        layout.addWidget(self.name_input)

        self.steps_list = QListWidget()
        layout.addWidget(self.steps_list)
        self._refresh_steps()

        add_row = QHBoxLayout()
        for label, mode in (("+ Add input", "tap"), ("+ Hold for time", "hold"),
                            ("+ Hold down", "down"), ("+ Release", "up")):
            btn = QPushButton(label)
            btn.setStyleSheet(BTN_STYLE)
            btn.clicked.connect(lambda checked=False, m=mode: self._start_input_capture(m))
            add_row.addWidget(btn)

        add_wait_btn = QPushButton("+ Add wait")
        add_wait_btn.setStyleSheet(BTN_STYLE)
        add_wait_btn.clicked.connect(self._add_wait)
        add_row.addWidget(add_wait_btn)
        layout.addLayout(add_row)

        move_row = QHBoxLayout()
        up_btn = QPushButton("Move up")
        up_btn.setStyleSheet(BTN_STYLE)
        up_btn.clicked.connect(self._move_up)
        move_row.addWidget(up_btn)

        down_btn = QPushButton("Move down")
        down_btn.setStyleSheet(BTN_STYLE)
        down_btn.clicked.connect(self._move_down)
        move_row.addWidget(down_btn)

        remove_btn = QPushButton("Remove step")
        remove_btn.setStyleSheet(BTN_STYLE)
        remove_btn.clicked.connect(self._remove_step)
        move_row.addWidget(remove_btn)
        layout.addLayout(move_row)

        self.loop_checkbox = QCheckBox('Loop until stopped (hotkey/voice "stop" ends it)')
        self.loop_checkbox.setStyleSheet("color: #c9d1d9;")
        if macro:
            self.loop_checkbox.setChecked(bool(macro.get("loop")))
        layout.addWidget(self.loop_checkbox)

        self.hotkey_btn = QPushButton()
        self.hotkey_btn.setStyleSheet(BTN_STYLE)
        self.hotkey_btn.clicked.connect(self._start_hotkey_capture)
        layout.addWidget(self.hotkey_btn)
        self._update_hotkey_label()

        save_btn = QPushButton("Save macro")
        save_btn.setStyleSheet(BTN_STYLE)
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #d29922;")
        layout.addWidget(self.status)

    # ---------- Functions (step list) ----------

    def _refresh_steps(self):
        self.steps_list.clear()
        for step in self.steps:
            kind = step["type"]
            who = step.get("key") or f"mouse {step.get('button', 'left')}"
            if kind == "key":
                self.steps_list.addItem(f"Key: {step['key']}")
            elif kind == "click":
                self.steps_list.addItem(f"Click ({step.get('button', 'left')})")
            elif kind in ("keydown", "mousedown"):
                self.steps_list.addItem(f"Hold down: {who}")
            elif kind in ("keyup", "mouseup"):
                self.steps_list.addItem(f"Release: {who}")
            elif kind == "hold":
                self.steps_list.addItem(f"Hold {who} for {step['ms']}ms")
            else:
                self.steps_list.addItem(f"Wait: {step['ms']}ms")

    def _add_wait(self):
        ms, ok = QInputDialog.getInt(self, "Add wait", "Delay in milliseconds:", 200, MIN_WAIT_MS, 60000)
        if ok:
            self.steps.append({"type": "wait", "ms": max(ms, MIN_WAIT_MS)})
            self._refresh_steps()

    def _move_up(self):
        i = self.steps_list.currentRow()
        if i > 0:
            self.steps[i - 1], self.steps[i] = self.steps[i], self.steps[i - 1]
            self._refresh_steps()
            self.steps_list.setCurrentRow(i - 1)

    def _move_down(self):
        i = self.steps_list.currentRow()
        if 0 <= i < len(self.steps) - 1:
            self.steps[i + 1], self.steps[i] = self.steps[i], self.steps[i + 1]
            self._refresh_steps()
            self.steps_list.setCurrentRow(i + 1)

    def _remove_step(self):
        i = self.steps_list.currentRow()
        if 0 <= i < len(self.steps):
            self.steps.pop(i)
            self._refresh_steps()

    # ---------- Functions (step capture: any key OR mouse click, modifier-aware) ----------

    def _start_input_capture(self, mode="tap"):
        self._capture_mode = mode
        self._listening_input = True
        self._held_modifiers = []
        self.status.setText(CAPTURE_HINTS[mode])
        self.setFocus()
        self._arm_mouse_capture()

    def _arm_mouse_capture(self):
        """Global mouse-click listening - a click anywhere on screen counts,
        not just clicks that land on this widget."""
        import mouse
        self._disarm_mouse_capture()
        self._mouse_handlers = [
            mouse.on_click(lambda: self._mouse_captured.emit("left")),
            mouse.on_right_click(lambda: self._mouse_captured.emit("right")),
            mouse.on_middle_click(lambda: self._mouse_captured.emit("middle")),
        ]

    def _disarm_mouse_capture(self):
        import mouse
        for handler in self._mouse_handlers:
            try:
                mouse.unhook(handler)
            except Exception:
                pass
        self._mouse_handlers = []

    def _on_mouse_captured(self, button_name):
        if not self._listening_input:
            return   # a key already finished this capture first
        self._finish_capture({"type": "click", "button": button_name})

    def _cancel_input_capture(self):
        self._disarm_mouse_capture()
        self._listening_input = False
        self._held_modifiers = []
        self.status.setText("Cancelled.")

    def _finish_capture(self, result):
        """result is a step dict: {"type": "key", "key": ...} or {"type": "click", "button": ...}."""
        self._disarm_mouse_capture()
        self._listening_input = False
        self._held_modifiers = []
        self.status.setText("")
        if self._capture_mode == "hold":
            QTimer.singleShot(0, lambda r=result: self._ask_hold_time(r))   # ask after this key event finishes
        else:
            self.steps.append(self._apply_mode(result))
            self._refresh_steps()

    def _apply_mode(self, step):
        """Turns a captured tap into a hold-down or release step when that button was used."""
        if self._capture_mode in ("down", "up"):
            prefix = "key" if step["type"] == "key" else "mouse"
            step["type"] = prefix + self._capture_mode      # keydown, keyup, mousedown, mouseup
        return step

    def _ask_hold_time(self, captured):
        ms, ok = QInputDialog.getInt(self, "Hold time", "Hold for (milliseconds):", 500, MIN_WAIT_MS, 600000)
        if not ok:
            return
        step = {"type": "hold", "ms": ms}
        if captured["type"] == "key":
            step["key"] = captured["key"]
        else:
            step["button"] = captured["button"]
        self.steps.append(step)
        self._refresh_steps()

    def keyPressEvent(self, event):
        if not self._listening_input:
            super().keyPressEvent(event)
            return
        if event.isAutoRepeat():
            return

        qt_key = event.key()

        if qt_key == Qt.Key.Key_Escape:
            self._cancel_input_capture()
            return

        if qt_key in MODIFIER_KEYS:
            name = MODIFIER_KEYS[qt_key]
            if name not in self._held_modifiers:
                self._held_modifiers.append(name)
            return   # wait to see if it's released alone, or combined with another key

        combo = "+".join(self._held_modifiers + [_resolve_key_name(qt_key, event.modifiers())])
        self._finish_capture({"type": "key", "key": combo})

    def keyReleaseEvent(self, event):
        if self._listening_input and not event.isAutoRepeat():
            qt_key = event.key()
            if qt_key in MODIFIER_KEYS:
                name = MODIFIER_KEYS[qt_key]
                if name in self._held_modifiers:
                    # released before any other key or click happened - it's a standalone step,
                    # not "shift+shift"
                    self._finish_capture({"type": "key", "key": name})
                    return
        super().keyReleaseEvent(event)

    # ---------- Functions (trigger capture, save) ----------

    def _start_hotkey_capture(self):
        self._hub.start()
        self.hotkey_btn.setText("Press a key, combo or controller button (Esc clears)...")
        self._hub.begin_capture()

    def _on_hotkey_captured(self, combo):
        self.hotkey = combo or None
        self._update_hotkey_label()

    def _update_hotkey_label(self):
        self.hotkey_btn.setText(f"Trigger: {self.hotkey} (click to change, Esc clears)" if self.hotkey else "Set trigger: key or controller button (optional)")

    def _save(self):
        self._hub.end_capture()
        self._disarm_mouse_capture()
        name = self.name_input.text().strip()
        if not name:
            self.status.setText("Give it a name first.")
            return
        if not self.steps:
            self.status.setText("Add at least one step.")
            return

        macros = [m for m in load_macros() if m["name"] not in (self.original_name, name)]
        macros.append({
            "name": name, "hotkey": self.hotkey, "loop": self.loop_checkbox.isChecked(), "steps": self.steps,
        })
        save_macros(macros)

        try:
            from core.macro_runner import register_hotkeys
            register_hotkeys()
        except ImportError:
            pass

        self.on_saved()
        self.nav.pop()