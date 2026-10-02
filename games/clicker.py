"""
GAME: Clicker
An idle/clicker game modeled on Cookie Clicker's core loop: buy buildings
for passive income (1.15x cost growth per purchase — same rate Cookie
Clicker uses, since our old 1.6x made real progress nearly impossible),
then Ascend for a permanent bonus once a run slows down.

TO MAKE A NEW GAME: copy this whole file to games/yourgame.py, change
NAME, and replace the widget's contents.
"""
import json
import math
import time
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QScrollArea
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

SAVE_PATH = Path(__file__).resolve().parent / "_clicker_save.json"

BTN_STYLE = """
QPushButton {
    background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 8px; padding: 6px; text-align: left;
}
QPushButton:hover { background-color: #21262d; border-color: #00e5ff; }
QPushButton:disabled { color: #4d5560; border-color: #21262d; }
"""
ASCEND_STYLE = """
QPushButton {
    background-color: #161b22; color: #a371f7; border: 1px solid #30363d;
    border-radius: 8px; padding: 8px; text-align: center;
}
QPushButton:hover { background-color: #21262d; border-color: #a371f7; }
QPushButton:disabled { color: #4d5560; border-color: #21262d; }
"""

# ---------- Game contract ----------
NAME = "Clicker"


def create_widget():
    return ClickerGame()


# ---------- Variables (balance knobs) ----------
COST_GROWTH = 1.15          # Cookie Clicker's own growth rate — far gentler than our old 1.6
CLICK_UPGRADE_BASE_COST = 20
ASCEND_DIVISOR = 100_000     # lifetime points needed per prestige point (sqrt-scaled, like Cookie Clicker)
PRESTIGE_BONUS_PER_POINT = 0.02   # +2% global production per prestige point, forever

BUILDINGS = [
    {"id": "intern",     "name": "Intern",           "base_cost": 15,        "cps": 0.1},
    {"id": "script",     "name": "Automated Script", "base_cost": 100,       "cps": 1},
    {"id": "server",     "name": "Server Rack",      "base_cost": 1_100,     "cps": 8},
    {"id": "datacenter", "name": "Data Center",      "base_cost": 12_000,    "cps": 47},
    {"id": "satellite",  "name": "Satellite Uplink", "base_cost": 130_000,   "cps": 260},
    {"id": "quantum",    "name": "Quantum Core",     "base_cost": 1_400_000, "cps": 1400},
]


# ---------- Functions (shared math) ----------

def building_cost(building, owned):
    return math.ceil(building["base_cost"] * (COST_GROWTH ** owned))


def click_upgrade_cost(level):
    return math.ceil(CLICK_UPGRADE_BASE_COST * (COST_GROWTH ** level))


def prestige_multiplier(state):
    return 1 + PRESTIGE_BONUS_PER_POINT * state.get("prestige_points", 0)


def total_cps(state):
    per_second = sum(state["buildings"].get(b["id"], 0) * b["cps"] for b in BUILDINGS)
    return per_second * prestige_multiplier(state)


def total_earned_prestige(state):
    """Total prestige points your lifetime Bytes have ever earned (cumulative)."""
    return int(math.sqrt(max(0, state.get("total_alltime", 0)) / ASCEND_DIVISOR))


def prestige_gain_available(state):
    """Points you'd actually gain by ascending right now (total earned minus what you already banked)."""
    return max(0, total_earned_prestige(state) - state.get("prestige_points", 0))


def next_prestige_threshold(state):
    """Lifetime Bytes needed to unlock your next prestige point."""
    target = state.get("prestige_points", 0) + 1
    return (target ** 2) * ASCEND_DIVISOR


# ---------- Widget ----------

class ClickerGame(QWidget):
    def __init__(self):
        super().__init__()
        self.state = self._load()
        self._save()

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        if self._offline_gain > 0:
            welcome = QLabel(f"+{self._offline_gain:,.0f} Bytes while you were away")
            welcome.setStyleSheet("color: #3fb950;")
            welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(welcome)
            QTimer.singleShot(4000, welcome.deleteLater)

        self.score_label = QLabel()
        self.score_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.score_label.setStyleSheet("color: #00e5ff;")
        self.score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.score_label)

        self.rate_label = QLabel()
        self.rate_label.setStyleSheet("color: #8b949e;")
        self.rate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.rate_label)

        self.prestige_label = QLabel()
        self.prestige_label.setStyleSheet("color: #a371f7;")
        self.prestige_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.prestige_label)

        self.ascend_btn = QPushButton()
        self.ascend_btn.setStyleSheet(ASCEND_STYLE)
        self.ascend_btn.clicked.connect(self.ascend)
        layout.addWidget(self.ascend_btn)

        click_btn = QPushButton("Click me")
        click_btn.setStyleSheet(BTN_STYLE)
        click_btn.clicked.connect(self.on_click)
        layout.addWidget(click_btn)

        self.click_upgrade_btn = QPushButton()
        self.click_upgrade_btn.setStyleSheet(BTN_STYLE)
        self.click_upgrade_btn.clicked.connect(self.buy_click_upgrade)
        layout.addWidget(self.click_upgrade_btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        self.buildings_container = QWidget()
        self.buildings_layout = QVBoxLayout(self.buildings_container)
        self.buildings_layout.setSpacing(4)
        scroll.setWidget(self.buildings_container)
        layout.addWidget(scroll)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(1000)

        self._refresh()

    # ---------- Functions (save/load) ----------

    def _load(self):
        now = time.time()
        if SAVE_PATH.exists():
            data = json.loads(SAVE_PATH.read_text(encoding="utf-8"))
            data.setdefault("buildings", {})
            data.setdefault("total_alltime", data.get("score", 0))
            data.setdefault("prestige_points", 0)
            data.setdefault("click_power", 1)
            data.setdefault("click_level", 0)

            elapsed_ticks = int(max(0, now - data.get("last_seen", now)))
            gain = elapsed_ticks * total_cps(data)
            data["score"] = data.get("score", 0) + gain
            data["total_alltime"] = data.get("total_alltime", 0) + gain
            self._offline_gain = gain
            return data

        self._offline_gain = 0
        return {
            "score": 0, "total_alltime": 0, "click_power": 1, "click_level": 0,
            "buildings": {}, "prestige_points": 0, "last_seen": now,
        }

    def _save(self):
        self.state["last_seen"] = time.time()
        SAVE_PATH.write_text(json.dumps(self.state), encoding="utf-8")

    # ---------- Functions (UI refresh) ----------

    def _refresh(self):
        s = self.state
        mult = prestige_multiplier(s)
        rate = total_cps(s)
        click_value = s["click_power"] * mult

        self.score_label.setText(f"{s['score']:,.0f} Bytes")
        self.rate_label.setText(f"+{click_value:,.1f} / click   |   +{rate:,.1f} / sec")

        gain = prestige_gain_available(s)
        needed = next_prestige_threshold(s)
        self.prestige_label.setText(
            f"Prestige: {s['prestige_points']} (+{s['prestige_points'] * PRESTIGE_BONUS_PER_POINT * 100:.0f}% bonus)\n"
            f"Next point at {needed:,.0f} lifetime Bytes (have {s['total_alltime']:,.0f})"
        )
        self.ascend_btn.setText(f"Ascend for +{gain} prestige" if gain > 0 else "Ascend (keep earning Bytes)")
        self.ascend_btn.setEnabled(gain > 0)

        cost = click_upgrade_cost(s["click_level"])
        self.click_upgrade_btn.setText(f"Upgrade click power (cost: {cost:,.0f})")
        self.click_upgrade_btn.setEnabled(s["score"] >= cost)

        self._rebuild_buildings()

    def _rebuild_buildings(self):
        while self.buildings_layout.count():
            item = self.buildings_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for b in BUILDINGS:
            owned = self.state["buildings"].get(b["id"], 0)
            cost = building_cost(b, owned)
            btn = QPushButton(f"{b['name']} ({owned})\ncost {cost:,.0f}  |  +{b['cps']}/sec each")
            btn.setStyleSheet(BTN_STYLE)
            btn.setEnabled(self.state["score"] >= cost)
            btn.clicked.connect(lambda checked, bid=b["id"]: self.buy_building(bid))
            self.buildings_layout.addWidget(btn)

    # ---------- Functions (actions) ----------

    def on_click(self):
        gain = self.state["click_power"] * prestige_multiplier(self.state)
        self.state["score"] += gain
        self.state["total_alltime"] += gain
        self._refresh()
        self._save()

    def on_tick(self):
        rate = total_cps(self.state)
        if rate:
            self.state["score"] += rate
            self.state["total_alltime"] += rate
            self._refresh()
            self._save()

    def buy_click_upgrade(self):
        cost = click_upgrade_cost(self.state["click_level"])
        if self.state["score"] >= cost:
            self.state["score"] -= cost
            self.state["click_power"] += 1
            self.state["click_level"] += 1
            self._refresh()
            self._save()

    def buy_building(self, building_id):
        building = next(b for b in BUILDINGS if b["id"] == building_id)
        owned = self.state["buildings"].get(building_id, 0)
        cost = building_cost(building, owned)
        if self.state["score"] >= cost:
            self.state["score"] -= cost
            self.state["buildings"][building_id] = owned + 1
            self._refresh()
            self._save()

    def ascend(self):
        gain = prestige_gain_available(self.state)
        if gain <= 0:
            return
        self.state["prestige_points"] += gain
        self.state["score"] = 0
        self.state["buildings"] = {}
        self.state["click_power"] = 1
        self.state["click_level"] = 0
        self._refresh()
        self._save()