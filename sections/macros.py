"""
SECTION: Macros
Build a macro from steps (keyboard, mouse and controller), give it a trigger
(a key, a combo, a mouse button or a controller button), and choose how it
runs: once, N times, loop until stopped, or loop while the trigger is held.

Every kind of step is defined in core/macro_steps.py - the Add menu, the Edit
dialog and the step list all read that table, so new step types show up here
without touching this file.
"""
import copy

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QScrollArea, QInputDialog, QCheckBox, QDialog, QFormLayout, QSpinBox,
    QDoubleSpinBox, QComboBox, QMenu, QDialogButtonBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, QTimer

from core.macro_store import load_macros, save_macros
from core.macro_steps import STEPS, describe, normalize, default_step, step_for_input
from core.input_hub import get_hub, parse_combo
from core.macro_recorder import MacroRecorder

BTN_STYLE = """
QPushButton {
    background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 8px; padding: 6px;
}
QPushButton:hover { background-color: #21262d; border-color: #00e5ff; }
"""
STOP_BTN_STYLE = BTN_STYLE.replace("#c9d1d9", "#f85149").replace("#00e5ff", "#f85149")
REC_BTN_STYLE = BTN_STYLE.replace("#c9d1d9", "#f85149")
MENU_STYLE = """
QMenu { background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d; }
QMenu::item { padding: 6px 18px; }
QMenu::item:selected { background-color: #21262d; color: #00e5ff; }
QMenu::separator { height: 1px; background: #30363d; margin: 4px 0; }
"""
DIALOG_STYLE = """
QDialog { background-color: #161b22; }
QLabel { color: #c9d1d9; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 3px 6px;
}
"""
LIST_STYLE = """
QListWidget { background-color: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 8px; }
QListWidget::item { padding: 4px 6px; }
QListWidget::item:selected { background-color: #21262d; color: #00e5ff; }
"""

MODES = [
    ("Run once", "once"),
    ("Repeat a number of times", "repeat"),
    ("Loop until stopped (trigger toggles it)", "toggle"),
    ("Loop while the trigger is held", "hold"),
]
MODE_LABELS = {value: label for label, value in MODES}

# starter templates: name -> (steps, mode)
SAMPLES = {
    "Blank": ([], "once"),
    "Autoclicker (runs while you hold the trigger)": (
        [{"type": "click", "button": "left"}, {"type": "wait", "ms": 50, "rand": 0}], "hold"),
    "Copy && Paste (Ctrl+C / Ctrl+V)": (
        [{"type": "key", "key": "ctrl+c"}, {"type": "wait", "ms": 100, "rand": 0}, {"type": "key", "key": "ctrl+v"}], "once"),
    "Hold W for 2 seconds": ([{"type": "keyhold", "key": "w", "ms": 2000}], "once"),
    "Controller: spam A": (
        [{"type": "pad", "button": "a"}, {"type": "wait", "ms": 100, "rand": 0}], "toggle"),
}

CAPTURE_HINTS = {
    "tap": "Press a key, mouse button or controller button to TAP (Esc cancels)...",
    "hold": "Press the key, mouse button or controller button to HOLD for a set time (Esc cancels)...",
    "down": "Press the input to HOLD DOWN until a Release step (Esc cancels)...",
    "up": "Press the input you want to RELEASE (Esc cancels)...",
}
TEST_NAME = "(test run)"


def _mode_of(macro):
    mode = (macro or {}).get("mode")
    if mode in MODE_LABELS:
        return mode
    return "toggle" if (macro or {}).get("loop") else "once"


def _trigger_text(macro):
    return f"  [{macro['hotkey']}]" if macro.get("hotkey") else ""


# ---------- Section contract ----------
NAME = "Macros"


def create_widget(nav):
    return MacroList(nav)


# ---------- Widgets ----------

class MacroList(QWidget):
    PANEL_SIZE = (640, 480)

    def __init__(self, nav):
        super().__init__()
        self.nav = nav
        self._run_buttons = {}   # macro name -> its Run/Stop button, for the periodic refresh

        layout = QVBoxLayout(self)

        hint = QLabel(
            'Voice: "Hey Jarvis, run <name>". Say "stop" to end running macros. '
            "Untick a macro to disable its trigger and voice command without deleting it."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b949e;")
        layout.addWidget(hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.scroll)

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setSpacing(6)
        self.scroll.setWidget(self.list_container)

        bottom = QHBoxLayout()
        new_btn = QPushButton("+ New macro")
        new_btn.setStyleSheet(BTN_STYLE)
        new_btn.clicked.connect(self.new_macro)
        bottom.addWidget(new_btn)
        stop_btn = QPushButton("Stop all")
        stop_btn.setStyleSheet(STOP_BTN_STYLE)
        stop_btn.clicked.connect(self.stop_all)
        bottom.addWidget(stop_btn)
        layout.addLayout(bottom)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #d29922;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # keeps Run/Stop button labels in sync if a macro is started/stopped by trigger or voice
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

        enabled = QCheckBox()
        enabled.setChecked(macro.get("enabled", True))
        enabled.setToolTip("Enabled")
        enabled.toggled.connect(lambda checked, m=macro: self.set_enabled(m, checked))
        row.addWidget(enabled)

        mode = _mode_of(macro)
        suffix = {"once": "", "repeat": f"  (x{macro.get('repeat', 1)})", "toggle": "  (loop)", "hold": "  (hold)"}[mode]
        label = QLabel(macro["name"] + _trigger_text(macro) + suffix)
        label.setStyleSheet("color: #c9d1d9;" if macro.get("enabled", True) else "color: #4d5560;")
        row.addWidget(label, 1)

        run_btn = QPushButton()
        run_btn.clicked.connect(lambda checked, m=macro: self.run_macro(m))
        row.addWidget(run_btn)
        self._run_buttons[macro["name"]] = run_btn

        for text, handler in (("Edit", self.edit_macro), ("Copy", self.duplicate_macro), ("Delete", self.delete_macro)):
            btn = QPushButton(text)
            btn.setStyleSheet(BTN_STYLE)
            btn.clicked.connect(lambda checked, m=macro, h=handler: h(m))
            row.addWidget(btn)

        self._style_run_button(macro, run_btn)
        return row_widget

    def _style_run_button(self, macro, btn):
        try:
            from core.macro_runner import is_running
            running = is_running(macro["name"])
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
        choice, ok = QInputDialog.getItem(self, "New Macro", "Start from:", list(SAMPLES.keys()), 0, False)
        if not ok:
            return
        steps, mode = SAMPLES[choice]
        self.nav.push(MacroEditor(self.nav, None, [dict(s) for s in steps], self.refresh, mode), "New Macro")

    def edit_macro(self, macro):
        self.nav.push(MacroEditor(self.nav, macro, list(macro["steps"]), self.refresh), macro["name"])

    def set_enabled(self, macro, checked):
        macros = load_macros()
        for m in macros:
            if m["name"] == macro["name"]:
                m["enabled"] = checked
        save_macros(macros)
        self._reregister_hotkeys()
        self.refresh()

    def duplicate_macro(self, macro):
        macros = load_macros()
        names = {m["name"] for m in macros}
        new_name, n = f"{macro['name']} copy", 2
        while new_name in names:
            new_name, n = f"{macro['name']} copy {n}", n + 1
        clone = copy.deepcopy(macro)
        clone["name"], clone["hotkey"] = new_name, None      # no trigger, so it can't clash with the original
        index = next(i for i, m in enumerate(macros) if m["name"] == macro["name"])
        macros.insert(index + 1, clone)
        save_macros(macros)
        self.refresh()

    def delete_macro(self, macro):
        save_macros([m for m in load_macros() if m["name"] != macro["name"]])
        self._reregister_hotkeys()
        self.refresh()

    def stop_all(self):
        try:
            from core.macro_runner import stop_all
            stop_all()
            self.status_label.setText("Stopped everything.")
            self._refresh_run_labels()
        except ImportError:
            pass

    def run_macro(self, macro):
        try:
            from core.macro_runner import is_running, trigger_macro
        except ImportError:
            self.status_label.setText("Install requirements.txt first (`keyboard`/`mouse` missing).")
            return

        # stopping is instant - no need to wait or switch windows for that
        if is_running(macro["name"]):
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


class StepDialog(QDialog):
    """Add/Edit dialog for any step type. The form is built from the step's
    field list in core/macro_steps.py, so it never needs changing for new steps."""

    def __init__(self, parent, hub, step_type, step=None):
        super().__init__(parent)
        self.hub = hub
        self.step_type = step_type
        self._cap_field = None
        spec = STEPS[step_type]
        self.setWindowTitle((spec["menu"] or step_type).rstrip("."))
        self.setStyleSheet(DIALOG_STYLE)
        self.setMinimumWidth(380)
        step = step or default_step(step_type)

        form = QFormLayout()
        self.widgets = {}
        for key, label, kind, default, extra in spec["fields"]:
            value = step.get(key, default)
            if kind in ("key", "pad"):
                edit = QLineEdit(str(value))
                capture = QPushButton("Capture")
                capture.setStyleSheet(BTN_STYLE)
                capture.clicked.connect(lambda checked=False, k=key: self._capture(k))
                row = QWidget()
                h = QHBoxLayout(row)
                h.setContentsMargins(0, 0, 0, 0)
                h.addWidget(edit, 1)
                h.addWidget(capture)
                form.addRow(label, row)
                self.widgets[key] = (kind, edit)
            elif kind == "text":
                edit = QLineEdit(str(value))
                form.addRow(label, edit)
                self.widgets[key] = (kind, edit)
            elif kind == "int":
                spin = QSpinBox()
                spin.setRange(*extra)
                spin.setValue(int(value))
                form.addRow(label, spin)
                self.widgets[key] = (kind, spin)
            elif kind == "float":
                spin = QDoubleSpinBox()
                spin.setRange(*extra)
                spin.setDecimals(2)
                spin.setSingleStep(0.1)
                spin.setValue(float(value))
                form.addRow(label, spin)
                self.widgets[key] = (kind, spin)
            elif kind == "choice":
                combo = QComboBox()
                combo.addItems(extra)
                combo.setCurrentText(str(value))
                form.addRow(label, combo)
                self.widgets[key] = (kind, combo)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        if spec.get("pick_xy"):
            pick = QPushButton("Pick position by clicking on the screen")
            pick.setStyleSheet(BTN_STYLE)
            pick.clicked.connect(lambda: self._capture("__pos__"))
            layout.addWidget(pick)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #d29922;")
        layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        hub.captured.connect(self._on_captured)

    def _capture(self, field):
        self._cap_field = field
        self.note.setText("Click anywhere on the screen (Esc cancels)..." if field == "__pos__"
                          else "Press the key or button now (Esc cancels)...")
        self.hub.start()
        self.hub.begin_capture()

    def _on_captured(self, text):
        field, self._cap_field = self._cap_field, None
        if field is None:
            return
        self.note.setText("")
        if not text:
            return
        if field == "__pos__":
            if text == "mouse:left":
                import mouse
                x, y = mouse.get_position()
                self.widgets["x"][1].setValue(x)
                self.widgets["y"][1].setValue(y)
            else:
                self.note.setText("That wasn't a left click. Try again.")
            return
        kind, edit = self.widgets[field]
        tokens = [t for t in text.split("+") if t]
        if kind == "key":
            picked = [t for t in tokens if not t.startswith(("pad:", "mouse:"))]
        else:
            picked = [t[4:] for t in tokens if t.startswith("pad:")]
        if picked:
            edit.setText("+".join(picked))
        else:
            self.note.setText("That was the wrong kind of input for this field.")

    def done(self, result):
        self.hub.end_capture()
        super().done(result)

    def values(self):
        step = {"type": self.step_type}
        for key, (kind, widget) in self.widgets.items():
            if kind in ("key", "pad", "text"):
                step[key] = widget.text() if kind == "text" else widget.text().strip()
            elif kind == "int":
                step[key] = widget.value()
            elif kind == "float":
                step[key] = round(widget.value(), 2)
            else:
                step[key] = widget.currentText()
        return step


class MacroEditor(QWidget):
    PANEL_SIZE = (640, 600)

    def __init__(self, nav, macro, starter_steps, on_saved, starter_mode="once"):
        super().__init__()
        self.nav = nav
        self.on_saved = on_saved
        self.macro = macro
        self.original_name = macro["name"] if macro else None
        self.hotkey = macro.get("hotkey") if macro else None
        self._cap_target = None            # what the next hub capture is for: ("trigger",) or ("step", action)
        self._pending_test = None

        self._hub = get_hub()
        self._hub.captured.connect(self._on_captured)
        self._recorder = MacroRecorder(self._hub)
        self._recorder.finished.connect(self._on_recorded)
        self.destroyed.connect(lambda *_, h=self._hub, r=self._recorder: (h.end_capture(), r.cancel()))

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.name_input = QLineEdit(macro["name"] if macro else "")
        self.name_input.setPlaceholderText("Macro name")
        top.addWidget(self.name_input, 1)
        self.enabled_box = QCheckBox("Enabled")
        self.enabled_box.setStyleSheet("color: #c9d1d9;")
        self.enabled_box.setChecked(macro.get("enabled", True) if macro else True)
        top.addWidget(self.enabled_box)
        layout.addLayout(top)

        self.steps_list = QListWidget()
        self.steps_list.setStyleSheet(LIST_STYLE)
        self.steps_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.steps_list.itemDoubleClicked.connect(lambda item: self._edit_current())
        layout.addWidget(self.steps_list)
        for step in starter_steps:
            self.steps_list.addItem(self._make_item(step))

        hint = QLabel("New steps go after the selected one. Double-click a step to edit it, drag to reorder.")
        hint.setStyleSheet("color: #8b949e;")
        layout.addWidget(hint)

        row = QHBoxLayout()
        self.add_btn = QPushButton("+ Add step  \u25be")
        self.add_btn.setStyleSheet(BTN_STYLE)
        self.add_btn.clicked.connect(self._show_add_menu)
        row.addWidget(self.add_btn)
        self.record_btn = QPushButton("\u25cf Record")
        self.record_btn.setStyleSheet(REC_BTN_STYLE)
        self.record_btn.clicked.connect(self._toggle_record)
        row.addWidget(self.record_btn)
        for text, handler in (("Edit", self._edit_current), ("Copy", self._duplicate_step), ("Remove", self._remove_step),
                              ("Up", self._move_up), ("Down", self._move_down)):
            btn = QPushButton(text)
            btn.setStyleSheet(BTN_STYLE)
            btn.clicked.connect(lambda checked=False, h=handler: h())
            row.addWidget(btn)
        layout.addLayout(row)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Run:"))
        self.mode_box = QComboBox()
        for label, value in MODES:
            self.mode_box.addItem(label, value)
        self.mode_box.setCurrentIndex(self.mode_box.findData(_mode_of(macro) if macro else starter_mode))
        self.mode_box.currentIndexChanged.connect(self._sync_mode_ui)
        mode_row.addWidget(self.mode_box, 1)
        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(1, 100000)
        self.repeat_spin.setValue(int(macro.get("repeat", 1)) if macro else 1)
        self.repeat_spin.setSuffix(" times")
        mode_row.addWidget(self.repeat_spin)
        layout.addLayout(mode_row)

        self.hotkey_btn = QPushButton()
        self.hotkey_btn.setStyleSheet(BTN_STYLE)
        self.hotkey_btn.clicked.connect(self._start_hotkey_capture)
        layout.addWidget(self.hotkey_btn)

        only_row = QHBoxLayout()
        only_row.addWidget(QLabel("Only when the active window title contains:"))
        self.only_in = QLineEdit(macro.get("only_in", "") if macro else "")
        self.only_in.setPlaceholderText("(blank = any window)")
        only_row.addWidget(self.only_in, 1)
        layout.addLayout(only_row)

        action_row = QHBoxLayout()
        self.test_btn = QPushButton("Test run")
        self.test_btn.setStyleSheet(BTN_STYLE)
        self.test_btn.clicked.connect(self._test_run)
        action_row.addWidget(self.test_btn)
        save_btn = QPushButton("Save macro")
        save_btn.setStyleSheet(BTN_STYLE)
        save_btn.clicked.connect(self._save)
        action_row.addWidget(save_btn)
        layout.addLayout(action_row)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: #d29922;")
        layout.addWidget(self.status)

        # one-shot timer for the Test run countdown, and a ticker that flips the Test button to "Stop test"
        self._test_delay = QTimer(self)
        self._test_delay.setSingleShot(True)
        self._test_delay.timeout.connect(self._start_test)
        self._test_ticker = QTimer(self)
        self._test_ticker.timeout.connect(self._sync_test_button)
        self._test_ticker.start(500)

        self._update_hotkey_label()
        self._sync_mode_ui()

    # ---------- Functions (step list) ----------

    def _make_item(self, step):
        step = normalize(step)
        item = QListWidgetItem(describe(step))
        item.setData(Qt.ItemDataRole.UserRole, step)
        return item

    def _steps(self):
        return [normalize(self.steps_list.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.steps_list.count())]

    def _insert_row(self):
        row = self.steps_list.currentRow()
        return row + 1 if row >= 0 else self.steps_list.count()

    def _insert_step(self, step):
        row = self._insert_row()
        self.steps_list.insertItem(row, self._make_item(step))
        self.steps_list.setCurrentRow(row)

    def _edit_current(self):
        item = self.steps_list.currentItem()
        if item is None:
            self.status.setText("Select a step first.")
            return
        step = normalize(item.data(Qt.ItemDataRole.UserRole))
        if step.get("type") not in STEPS:
            self.status.setText("This step type isn't known to this version.")
            return
        dlg = StepDialog(self, self._hub, step["type"], step)
        if dlg.exec():
            new = dlg.values()
            item.setData(Qt.ItemDataRole.UserRole, new)
            item.setText(describe(new))
        dlg.deleteLater()

    def _duplicate_step(self):
        item = self.steps_list.currentItem()
        if item is not None:
            self._insert_step(copy.deepcopy(item.data(Qt.ItemDataRole.UserRole)))

    def _remove_step(self):
        row = self.steps_list.currentRow()
        if row >= 0:
            self.steps_list.takeItem(row)

    def _move_up(self):
        row = self.steps_list.currentRow()
        if row > 0:
            self.steps_list.insertItem(row - 1, self.steps_list.takeItem(row))
            self.steps_list.setCurrentRow(row - 1)

    def _move_down(self):
        row = self.steps_list.currentRow()
        if 0 <= row < self.steps_list.count() - 1:
            self.steps_list.insertItem(row + 1, self.steps_list.takeItem(row))
            self.steps_list.setCurrentRow(row + 1)

    # ---------- Functions (adding steps) ----------

    def _show_add_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        press = menu.addMenu("Press an input (key / mouse / controller)")
        for label, action in (("Tap it", "tap"), ("Hold it for a set time", "hold"),
                              ("Hold it down (until a Release step)", "down"), ("Release it", "up")):
            press.addAction(label).triggered.connect(lambda checked=False, a=action: self._capture_step(a))
        menu.addSeparator()
        for step_type, spec in STEPS.items():
            if spec.get("menu"):
                menu.addAction(spec["menu"]).triggered.connect(lambda checked=False, t=step_type: self._dialog_step(t))
        menu.exec(self.add_btn.mapToGlobal(self.add_btn.rect().bottomLeft()))

    def _dialog_step(self, step_type):
        dlg = StepDialog(self, self._hub, step_type)
        if dlg.exec():
            self._insert_step(dlg.values())
        dlg.deleteLater()

    def _capture_step(self, action):
        self._cap_target = ("step", action)
        self.status.setText(CAPTURE_HINTS[action])
        self._hub.start()
        self._hub.begin_capture()

    def _start_hotkey_capture(self):
        self._cap_target = ("trigger",)
        self.hotkey_btn.setText("Press a key, combo, mouse button or controller button (Esc clears)...")
        self._hub.start()
        self._hub.begin_capture()

    def _on_captured(self, text):
        target, self._cap_target = self._cap_target, None
        if target is None:
            return                          # the capture belonged to a dialog, not to us
        if target[0] == "trigger":
            self.hotkey = text or None
            self._update_hotkey_label()
            return
        if not text:
            self.status.setText("Cancelled.")
            return
        action, ms = target[1], 500
        if action == "hold":
            ms, ok = QInputDialog.getInt(self, "Hold time", "Hold for (milliseconds):", 500, 10, 600000)
            if not ok:
                self.status.setText("")
                return
        step = step_for_input(text, action, ms)
        if step is None:
            self.status.setText("Couldn't use that input.")
            return
        self._insert_step(step)
        self.status.setText("")

    # ---------- Functions (recording) ----------

    def _toggle_record(self):
        if self._recorder.active:
            self._recorder.stop()
            return
        self._hub.end_capture()
        self._hub.start()
        self._recorder.start()
        self.record_btn.setText("\u25a0 Stop recording (F8)")
        self.status.setText("Recording. Switch to your target and do the actions, then press F8.")

    def _on_recorded(self, steps):
        self.record_btn.setText("\u25cf Record")
        if not steps:
            self.status.setText("Nothing was recorded.")
            return
        for step in steps:
            self._insert_step(step)
        self.status.setText(f"Recorded {len(steps)} steps. Edit or remove any you don't need.")

    # ---------- Functions (options, test, save) ----------

    def _sync_mode_ui(self):
        self.repeat_spin.setEnabled(self.mode_box.currentData() == "repeat")

    def _update_hotkey_label(self):
        self.hotkey_btn.setText(
            f"Trigger: {self.hotkey}   (click to change, Esc clears)" if self.hotkey
            else "Set trigger: a key, combo, mouse button or controller button (optional)"
        )

    def _sync_test_button(self):
        try:
            from core.macro_runner import is_running
            self.test_btn.setText("Stop test" if is_running(TEST_NAME) else "Test run")
        except ImportError:
            pass

    def _test_run(self):
        try:
            from core.macro_runner import is_running, stop_macro_by_name
        except ImportError:
            self.status.setText("Install requirements.txt first (`keyboard`/`mouse` missing).")
            return
        if is_running(TEST_NAME):
            stop_macro_by_name(TEST_NAME)
            self.status.setText("Test stopped.")
            return
        steps = self._steps()
        if not steps:
            self.status.setText("Add at least one step first.")
            return
        self._pending_test = {"name": TEST_NAME, "mode": self.mode_box.currentData(),
                              "repeat": self.repeat_spin.value(), "steps": steps}
        self.status.setText("Test starts in 3 seconds - switch to your target window...")
        self._test_delay.start(3000)

    def _start_test(self):
        from core.macro_runner import trigger_macro
        if self._pending_test:
            self.status.setText(trigger_macro(self._pending_test))
            self._pending_test = None

    def _save(self):
        self._hub.end_capture()
        name = self.name_input.text().strip()
        steps = self._steps()
        if not name:
            self.status.setText("Give it a name first.")
            return
        if not steps:
            self.status.setText("Add at least one step.")
            return

        macros = load_macros()
        for other in macros:
            if other["name"] == self.original_name:
                continue
            if other["name"] == name:
                self.status.setText(f'A macro named "{name}" already exists.')
                return
            if self.hotkey and other.get("hotkey") and other.get("enabled", True) \
                    and parse_combo(other["hotkey"]) == parse_combo(self.hotkey):
                self.status.setText(f'That trigger is already used by "{other["name"]}".')
                return

        mode = self.mode_box.currentData()
        macro = dict(self.macro or {})
        macro.update({
            "name": name, "enabled": self.enabled_box.isChecked(), "hotkey": self.hotkey, "mode": mode,
            "loop": mode in ("toggle", "hold"), "repeat": self.repeat_spin.value(),
            "only_in": self.only_in.text().strip(), "steps": steps,
        })
        index = next((i for i, m in enumerate(macros) if m["name"] == self.original_name), None)
        if index is None:
            macros.append(macro)
        else:
            macros[index] = macro
        save_macros(macros)

        try:
            from core.macro_runner import register_hotkeys
            register_hotkeys()
        except ImportError:
            pass

        self.on_saved()
        self.nav.pop()