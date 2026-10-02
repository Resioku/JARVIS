"""
SECTION: Links
Lets you point a button at any .exe (games, apps, whatever) and launch it
instantly. Icons are pulled straight from the .exe.

This file follows the section "contract": NAME + create_widget(nav).
"""
import os
from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFileDialog, QInputDialog, QFrame
)
from PyQt6.QtGui import QPixmap, QFont, QDrag, QPainter
from PyQt6.QtCore import Qt, QEvent, QMimeData

from core.config_store import load_config, save_config
from core.icon_utils import get_icon_path

BTN_STYLE = """
QPushButton {
    background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 8px; padding: 8px; text-align: left;
}
QPushButton:hover { background-color: #21262d; border-color: #00e5ff; }
"""

REORDER_MIME = "application/x-jarvis-link-index"

DRAG_OPACITY = 0.6


def _faded(pixmap: QPixmap, opacity: float = DRAG_OPACITY) -> QPixmap:
    """Returns a semi-transparent copy of pixmap, so the drop indicator
    line is visible underneath the dragged row's snapshot."""
    result = QPixmap(pixmap.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setOpacity(opacity)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return result


class DragHandle(QLabel):
    """A small grip on each row — drag this specifically to reorder,
    so it doesn't interfere with clicking the row to open it."""

    def __init__(self, index, parent=None):
        super().__init__("\u2261", parent)   # a simple stacked-lines "grip" glyph
        self.index = index
        self.setStyleSheet("color: #4d5560; padding: 0 4px;")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._press_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._press_pos is not None:
            row = self.parentWidget()
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(REORDER_MIME, str(self.index).encode())
            drag.setMimeData(mime)
            drag.setPixmap(_faded(row.grab()))                  # semi-transparent so the drop line shows through
            drag.setHotSpot(self.pos() + event.position().toPoint())

            row.hide()                                            # the list "opens up" a gap where it was
            result = drag.exec(Qt.DropAction.MoveAction)
            if result != Qt.DropAction.MoveAction:
                row.show()   # drag was cancelled/dropped elsewhere — put it back
            # on a successful drop, refresh() has already rebuilt every row, so this one is gone
            self._press_pos = None
        event.accept()

    def mouseReleaseEvent(self, event):
        self._press_pos = None
        event.accept()

# ---------- Section contract ----------
NAME = "Links"


def create_widget(nav):
    return LinksList(nav)


# ---------- Widgets ----------

class LinksList(QWidget):
    """The scrollable list of every saved link."""

    def __init__(self, nav):
        super().__init__()
        self.nav = nav

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.scroll)

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setSpacing(6)
        self.scroll.setWidget(self.list_container)

        # thin glowing line that shows exactly where a dragged row will land
        self.indicator = QFrame(self.list_container)
        self.indicator.setFixedHeight(3)
        self.indicator.setStyleSheet("background-color: #00e5ff; border-radius: 1px;")
        self.indicator.hide()

        add_row = QHBoxLayout()
        add_app_btn = QPushButton("+ Add app")
        add_app_btn.setStyleSheet(BTN_STYLE)
        add_app_btn.clicked.connect(self.add_link)
        add_row.addWidget(add_app_btn)

        add_url_btn = QPushButton("+ Add URL")
        add_url_btn.setStyleSheet(BTN_STYLE)
        add_url_btn.clicked.connect(self.add_url_link)
        add_row.addWidget(add_url_btn)
        layout.addLayout(add_row)

        hint = QLabel("...or drag a file / link here")
        hint.setStyleSheet("color: #8b949e;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        # accept drops both on empty panel space and inside the scroll area
        self.setAcceptDrops(True)
        self.scroll.setAcceptDrops(True)
        self.scroll.viewport().setAcceptDrops(True)
        self.scroll.viewport().installEventFilter(self)

        self.refresh()

    # ---------- Functions (drag and drop) ----------

    def eventFilter(self, obj, event):
        if obj is self.scroll.viewport():
            et = event.type()
            if et == QEvent.Type.DragEnter:
                event.acceptProposedAction()
                return True
            if et == QEvent.Type.DragMove:
                if event.mimeData().hasFormat(REORDER_MIME):
                    self._show_indicator(event.position().toPoint())
                event.acceptProposedAction()
                return True
            if et == QEvent.Type.DragLeave:
                self._hide_indicator()
                return True
            if et == QEvent.Type.Drop:
                self._hide_indicator()
                if event.mimeData().hasFormat(REORDER_MIME):
                    index = int(bytes(event.mimeData().data(REORDER_MIME)).decode())
                    self._reorder(index, event.position().toPoint())
                else:
                    self._handle_drop(event.mimeData())
                event.acceptProposedAction()
                return True
        return super().eventFilter(obj, event)

    def _drop_target_index(self, pos_in_viewport):
        """Which position among the link rows a drop at this point should land at."""
        pos_in_container = self.list_container.mapFrom(self.scroll.viewport(), pos_in_viewport)
        row_index = 0
        for i in range(self.list_layout.count()):
            widget = self.list_layout.itemAt(i).widget()
            if widget is None or widget is self.indicator:   # skip the trailing stretch and the indicator itself
                continue
            if pos_in_container.y() < widget.geometry().center().y():
                return row_index
            row_index += 1
        return row_index

    def _show_indicator(self, pos_in_viewport):
        target = self._drop_target_index(pos_in_viewport)
        self.list_layout.removeWidget(self.indicator)
        self.list_layout.insertWidget(target, self.indicator)
        self.indicator.show()

    def _hide_indicator(self):
        self.list_layout.removeWidget(self.indicator)
        self.indicator.hide()

    def _reorder(self, from_index, viewport_pos):
        target = self._drop_target_index(viewport_pos)
        if target > from_index:
            target -= 1   # removing the source item shifts everything after it up by one

        config = load_config()
        links = config.get("links", [])
        if not (0 <= from_index < len(links)):
            return
        item = links.pop(from_index)
        links.insert(max(0, min(target, len(links))), item)
        config["links"] = links
        save_config(config)
        self.refresh()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self._handle_drop(event.mimeData())
        event.acceptProposedAction()

    def _handle_drop(self, mime):
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    self._add_app_entry(url.toLocalFile())
                elif url.scheme() in ("http", "https"):
                    self._add_url_entry(url.toString())
        elif mime.hasText():
            text = mime.text().strip()
            if text.startswith(("http://", "https://")):
                self._add_url_entry(text)

    def refresh(self):
        # wipe current rows and rebuild from config.json
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        links = load_config().get("links", [])
        if not links:
            empty = QLabel("No links yet — add one below.")
            empty.setStyleSheet("color: #8b949e;")
            self.list_layout.addWidget(empty)
            return

        for i, entry in enumerate(links):
            row = QPushButton()
            row.setFixedHeight(44)
            row.setStyleSheet(BTN_STYLE)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(6, 4, 6, 4)

            icon_label = QLabel()
            icon_path = entry.get("icon")
            if icon_path and Path(icon_path).exists():
                icon_label.setPixmap(QPixmap(icon_path).scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio))
            else:
                icon_label.setText("🔗" if entry.get("type") == "url" else "*")
            row_layout.addWidget(icon_label)

            name_label = QLabel(entry["name"])
            name_label.setStyleSheet("color: #c9d1d9; background: transparent; border: none;")
            row_layout.addWidget(name_label)
            row_layout.addStretch()
            row_layout.addWidget(DragHandle(i, row))

            row.clicked.connect(lambda checked, e=entry: self.open_detail(e))
            self.list_layout.addWidget(row)

        self.list_layout.addStretch()

    def open_detail(self, entry):
        self.nav.push(LinkDetail(self.nav, entry, self.refresh), entry["name"])

    def add_link(self):
        exe_path, _ = QFileDialog.getOpenFileName(self, "Choose an app or game .exe", filter="Executables (*.exe);;All files (*.*)")
        if exe_path:
            self._add_app_entry(exe_path)

    def _add_app_entry(self, exe_path):
        default_name = Path(exe_path).stem
        name, ok = QInputDialog.getText(self, "Name this link", "Display name:", text=default_name)
        if not ok or not name:
            return

        icon_path = get_icon_path(exe_path, name)

        config = load_config()
        config.setdefault("links", []).append({"name": name, "path": exe_path, "icon": icon_path, "type": "app"})
        save_config(config)
        self.refresh()

    def add_url_link(self):
        url, ok = QInputDialog.getText(self, "Add a URL", "Paste the link (e.g. a YouTube video):")
        if ok and url.strip():
            self._add_url_entry(url.strip())

    def _add_url_entry(self, url):
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        guessed_name = urlparse(url).netloc.replace("www.", "") or url
        name, ok = QInputDialog.getText(self, "Name this link", "Display name:", text=guessed_name)
        if not ok or not name:
            return

        config = load_config()
        config.setdefault("links", []).append({"name": name, "path": url, "icon": None, "type": "url"})
        save_config(config)
        self.refresh()


class LinkDetail(QWidget):
    """Big icon + name + Launch/Remove, shown after clicking a link."""

    def __init__(self, nav, entry: dict, on_removed):
        super().__init__()
        self.nav = nav
        self.entry = entry
        self.on_removed = on_removed

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)

        icon_label = QLabel()
        icon_path = entry.get("icon")
        if icon_path and Path(icon_path).exists():
            icon_label.setPixmap(QPixmap(icon_path).scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            icon_label.setText("🔗" if entry.get("type") == "url" else "*")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        name_label = QLabel(entry["name"])
        name_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        name_label.setStyleSheet("color: #c9d1d9;")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)

        launch_btn = QPushButton("Launch")
        launch_btn.setStyleSheet(BTN_STYLE)
        launch_btn.clicked.connect(self.launch)
        layout.addWidget(launch_btn)

        remove_btn = QPushButton("Remove link")
        remove_btn.setStyleSheet(BTN_STYLE)
        remove_btn.clicked.connect(self.remove)
        layout.addWidget(remove_btn)

    def launch(self):
        try:
            os.startfile(self.entry["path"])
        except Exception as e:
            print(f"[links] Failed to launch {self.entry['path']}: {e}")

    def remove(self):
        config = load_config()
        config["links"] = [l for l in config.get("links", []) if l["name"] != self.entry["name"]]
        save_config(config)
        self.on_removed()
        self.nav.pop()