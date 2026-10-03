"""
GAME: Clicker
Idle/clicker built on proven formulas:
  - Cookie Clicker: building cost = base * 1.15^owned, 25/50/100... owned
    doubles a building, golden orbs, prestige that never costs you your bonus
  - Bulk buying (1x / 10x / 25x / 100x / MAX) using the exact geometric sum
  - Achievements, each worth +1% production (Cookie Clicker's milk idea)
  - Click combo for active play, crits, and a Prestige Shop with an Auto Clicker

TO MAKE A NEW GAME: copy this whole file to games/yourgame.py, change
NAME, and replace the widget's contents.
"""
import json
import math
import random
import time
from collections import deque
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QStackedWidget, QProgressBar, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer, QVariantAnimation, QPropertyAnimation, QEasingCurve, QPoint, QPointF
from PyQt6.QtGui import QFont, QCursor, QPainter, QColor, QPen, QPolygonF

SAVE_PATH = Path(__file__).resolve().parent / "_clicker_save.json"

BTN_STYLE = """
QPushButton {
    background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 8px; padding: 6px; text-align: left;
}
QPushButton:hover { background-color: #21262d; border-color: #00e5ff; }
QPushButton:disabled { color: #4d5560; border-color: #21262d; }
"""
MAX_STYLE = """
QPushButton {
    background-color: #161b22; color: #00e5ff; border: 1px solid #30363d;
    border-radius: 8px; padding: 4px; text-align: center; font-weight: bold;
}
QPushButton:hover { background-color: #21262d; border-color: #00e5ff; }
QPushButton:disabled { color: #4d5560; border-color: #21262d; }
"""
AMOUNT_STYLE = """
QPushButton {
    background-color: #161b22; color: #8b949e; border: 1px solid #30363d;
    border-radius: 6px; padding: 3px 8px; text-align: center;
}
QPushButton:hover { border-color: #00e5ff; }
QPushButton:checked { background-color: #00e5ff; color: #0d1117; font-weight: bold; }
"""
CLICK_STYLE = """
QPushButton {
    background-color: #161b22; color: #00e5ff; border: 1px solid #00e5ff;
    border-radius: 8px; padding: 10px; font-weight: bold; text-align: center;
}
QPushButton:hover { background-color: #21262d; }
QPushButton:pressed { background-color: #0d1117; }
"""
PURPLE_STYLE = """
QPushButton {
    background-color: #161b22; color: #a371f7; border: 1px solid #30363d;
    border-radius: 8px; padding: 8px; text-align: center;
}
QPushButton:hover { background-color: #21262d; border-color: #a371f7; }
QPushButton:disabled { color: #4d5560; border-color: #21262d; }
"""
SHOP_STYLE = BTN_STYLE.replace("#00e5ff", "#a371f7")
GOLD_STYLE = """
QPushButton {
    background-color: #d29922; color: #0d1117; border: 2px solid #f2cc60;
    border-radius: 22px; font-weight: bold; font-size: 18px;
}
QPushButton:hover { background-color: #f2cc60; }
"""
BAR_STYLE = """
QProgressBar { background-color: #161b22; border: 1px solid #30363d; border-radius: 4px; }
QProgressBar::chunk { background-color: #a371f7; border-radius: 3px; }
"""

# ---------- Game contract ----------
NAME = "Clicker"


def create_widget():
    return ClickerGame()


# ---------- Variables (balance knobs) ----------
COST_GROWTH = 1.15                 # Cookie Clicker's building cost growth
CLICK_UPGRADE_BASE_COST = 50
CLICK_UPGRADE_GROWTH = 1.35
CLICK_UPGRADE_BONUS = 0.05         # each click upgrade level also adds +5% to your whole click value (multiplies with the 1% of CPS part)
CLICK_CPS_SHARE = 0.01             # each click also earns 1% of your base per-second rate
MILESTONES = [25, 50, 100, 150, 200, 250, 300]   # owning this many of a building doubles its output
BUY_AMOUNTS = [1, 10, 25, 100, "MAX"]            # the selector buttons. Edit freely, "MAX" = all you can afford

ASCEND_DIVISOR = 100_000           # points = sqrt(lifetime / this)
PRESTIGE_BONUS_PER_POINT = 0.02    # +2% global production per prestige point earned, forever
ACHIEVEMENT_BONUS = 0.01           # +1% global production per achievement

# ---- Offline progress ----
OFFLINE_ENABLED = True             # False = nothing is earned while the game screen is closed
OFFLINE_RATE = 1.0                 # 1.0 = full speed, exactly like it was open the whole time
OFFLINE_CAP_SECONDS = None         # None = no limit. e.g. 8 * 3600 to stop counting after 8 hours

# ---- Clicking ----
CRIT_BASE_CHANCE = 0.05
CRIT_BASE_MULT = 5.0
AUTO_CLICKS_PER_LEVEL = 1.0        # each Auto Clicker shop level = this many clicks per second
AUTO_CLICKS_USE_COMBO = False      # True = auto clicks also build/use the combo. False = combo is for manual clicking only
CLICK_RATE_CAP = 10                # clicks/sec that earn full value. Faster than this (macros, external autoclickers) is scaled
                                   # down so total click income stops growing. Owning Auto Clicker levels raises the cap to match.
COMBO_WINDOW = 1.5                 # seconds you can pause before the combo resets
COMBO_BONUS = 0.005                # +0.5% click value per combo step
COMBO_MAX = 100                    # combo stops growing here (+50% click value)
FLOAT_MS = 900
FLOAT_RISE = 50

# ---- Golden orbs ----
GOLDEN_INTERVAL = (30, 90)
GOLDEN_LIFETIME = 12
FRENZY_MULT, FRENZY_SECONDS = 7, 30
CLICK_FRENZY_MULT, CLICK_FRENZY_SECONDS = 7, 15

TICK_MS = 250
SAVE_EVERY_TICKS = 20

BUILDINGS = [
    {"id": "intern",     "name": "Intern",           "base_cost": 15,          "cps": 0.1},
    {"id": "script",     "name": "Automated Script", "base_cost": 100,         "cps": 1},
    {"id": "server",     "name": "Server Rack",      "base_cost": 1_100,       "cps": 8},
    {"id": "datacenter", "name": "Data Center",      "base_cost": 12_000,      "cps": 47},
    {"id": "satellite",  "name": "Satellite Uplink", "base_cost": 130_000,     "cps": 260},
    {"id": "quantum",    "name": "Quantum Core",     "base_cost": 1_400_000,   "cps": 1_400},
    {"id": "neural",     "name": "Neural Net",       "base_cost": 20_000_000,  "cps": 7_800},
    {"id": "singular",   "name": "Singularity",      "base_cost": 330_000_000, "cps": 44_000},
]

# Prestige Shop: permanent upgrades. cost of next level = base * growth^level.
SHOP = [
    {"id": "autoclick",   "name": "Auto Clicker",    "desc": "+1 auto click/sec (crits too)", "base": 25, "growth": 1.30, "max": 30},
    {"id": "crit_chance", "name": "Critical Chance", "desc": "+1% crit chance",               "base": 5,  "growth": 1.25, "max": 25},
    {"id": "crit_power",  "name": "Critical Power",  "desc": "+0.5x crit damage",             "base": 10, "growth": 1.25, "max": 20},
    {"id": "fingers",     "name": "Strong Fingers",  "desc": "+10% click value",              "base": 5,  "growth": 1.25, "max": 40},
    {"id": "overclock",   "name": "Overclock",       "desc": "+5% all production",            "base": 8,  "growth": 1.25, "max": 40},
    {"id": "discount",    "name": "Bulk Discount",   "desc": "-2% building costs",            "base": 15, "growth": 1.30, "max": 15},
    {"id": "orbs",        "name": "Lucky Streak",    "desc": "-15% time between orbs",        "base": 10, "growth": 2.00, "max": 5},
    {"id": "extender",    "name": "Frenzy Extender", "desc": "+5s on every frenzy",           "base": 12, "growth": 1.60, "max": 6},
    {"id": "headstart",   "name": "Head Start",      "desc": "Start runs with free buildings", "base": 20, "growth": 1.50, "max": 10},
]
HEAD_START = {"intern": 10, "script": 5, "server": 2}   # per Head Start level, given after you Ascend

# Achievements: (id, name, description, stat, threshold). Each is worth +1% production.
ACHIEVEMENTS = [
    ("life1", "First Steps",      "Earn 1K lifetime Bytes",      "lifetime", 1e3),
    ("life2", "Pocket Change",    "Earn 1M lifetime Bytes",      "lifetime", 1e6),
    ("life3", "Big Data",         "Earn 1B lifetime Bytes",      "lifetime", 1e9),
    ("life4", "Terabyte Club",    "Earn 1T lifetime Bytes",      "lifetime", 1e12),
    ("life5", "Petabyte Pioneer", "Earn 1Qa lifetime Bytes",     "lifetime", 1e15),
    ("life6", "Beyond Measure",   "Earn 1Qi lifetime Bytes",     "lifetime", 1e18),
    ("clk1",  "Warming Up",       "Click 100 times",             "clicks", 100),
    ("clk2",  "Finger Workout",   "Click 1,000 times",           "clicks", 1_000),
    ("clk3",  "Carpal Tunnel",    "Click 10,000 times",          "clicks", 10_000),
    ("clk4",  "Click Machine",    "Click 100,000 times",         "clicks", 100_000),
    ("crt1",  "Lucky Strike",     "Land 10 crits",               "crits", 10),
    ("crt2",  "Sharpshooter",     "Land 100 crits",              "crits", 100),
    ("crt3",  "Critical Mass",    "Land 1,000 crits",            "crits", 1_000),
    ("gld1",  "Shiny!",           "Click a golden orb",          "golden", 1),
    ("gld2",  "Orb Hunter",       "Click 10 golden orbs",        "golden", 10),
    ("gld3",  "Midas Touch",      "Click 50 golden orbs",        "golden", 50),
    ("own1",  "Small Fleet",      "Own 10 of one building",      "max_owned", 10),
    ("own2",  "Fleet Manager",    "Own 50 of one building",      "max_owned", 50),
    ("own3",  "Empire",           "Own 100 of one building",     "max_owned", 100),
    ("own4",  "Monopoly",         "Own 200 of one building",     "max_owned", 200),
    ("cps1",  "Passive Income",   "Produce 100 Bytes/sec",       "cps", 1e2),
    ("cps2",  "Cash Flow",        "Produce 100K Bytes/sec",      "cps", 1e5),
    ("cps3",  "Money Printer",    "Produce 100M Bytes/sec",      "cps", 1e8),
    ("cps4",  "Economy Breaker",  "Produce 100B Bytes/sec",      "cps", 1e11),
    ("pre1",  "Reborn",           "Reach 1 prestige point",      "prestige", 1),
    ("pre2",  "Ascended",         "Reach 100 prestige points",   "prestige", 100),
    ("pre3",  "Transcendent",     "Reach 1,000 prestige points", "prestige", 1_000),
    ("pre4",  "Eternal",          "Reach 10,000 prestige points", "prestige", 10_000),
    ("shp1",  "Investor",         "Buy a shop upgrade",          "shop_total", 1),
    ("shp2",  "Big Spender",      "Own 25 shop levels",          "shop_total", 25),
    ("shp3",  "Collector",        "Own 100 shop levels",         "shop_total", 100),
]

SUFFIXES = ["", "K", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc"]


# ---------- Functions (shared math) ----------

def fmt(n):
    """1234567 -> '1.23M'. Small numbers keep a decimal so 0.1/sec still reads right."""
    n = float(n)
    if n < 1000:
        return f"{n:,.0f}" if (n >= 100 or n == int(n)) else f"{n:.1f}"
    idx = min(int(math.log10(n) // 3), len(SUFFIXES) - 1)
    return f"{n / 1000 ** idx:.2f}{SUFFIXES[idx]}"


def shop_level(state, item_id):
    return state.get("shop", {}).get(item_id, 0)


def shop_cost(item, level):
    return math.ceil(item["base"] * (item["growth"] ** level))


def points_available(state):
    return state.get("prestige_points", 0) - state.get("prestige_spent", 0)


def crit_chance(state):
    return CRIT_BASE_CHANCE + 0.01 * shop_level(state, "crit_chance")


def crit_multiplier(state):
    return CRIT_BASE_MULT + 0.5 * shop_level(state, "crit_power")


def _unit_cost(building, owned, state):
    """Cost of the very next building, before bulk math."""
    discount = 0.98 ** shop_level(state, "discount")
    return building["base_cost"] * (COST_GROWTH ** owned) * discount


def bulk_cost(building, owned, n, state):
    """Exact cost of buying n at once: a geometric series, same as Cookie Clicker's bulk buy."""
    return math.ceil(_unit_cost(building, owned, state) * (COST_GROWTH ** n - 1) / (COST_GROWTH - 1))


def max_affordable(building, owned, bank, state):
    unit = _unit_cost(building, owned, state)
    if bank < unit:
        return 0
    n = int(math.log(1 + bank * (COST_GROWTH - 1) / unit) / math.log(COST_GROWTH))
    while n > 0 and bulk_cost(building, owned, n, state) > bank:    # guard against float rounding
        n -= 1
    while bulk_cost(building, owned, n + 1, state) <= bank:
        n += 1
    return n


def click_upgrade_cost(level):
    return math.ceil(CLICK_UPGRADE_BASE_COST * (CLICK_UPGRADE_GROWTH ** level))


def milestone_mult(owned):
    return 2 ** sum(1 for m in MILESTONES if owned >= m)


def next_milestone(owned):
    return next((m for m in MILESTONES if owned < m), None)


def prestige_multiplier(state):
    """Prestige points x Overclock shop upgrade x achievements."""
    return (
        (1 + PRESTIGE_BONUS_PER_POINT * state.get("prestige_points", 0))
        * (1 + 0.05 * shop_level(state, "overclock"))
        * (1 + ACHIEVEMENT_BONUS * len(state.get("ach", [])))
    )


def base_cps(state):
    return sum(
        state["buildings"].get(b["id"], 0) * b["cps"] * milestone_mult(state["buildings"].get(b["id"], 0))
        for b in BUILDINGS
    )


def total_cps(state):
    return base_cps(state) * prestige_multiplier(state)


def click_value(state):
    return (
        (state["click_power"] + CLICK_CPS_SHARE * base_cps(state))
        * prestige_multiplier(state)
        * (1 + 0.10 * shop_level(state, "fingers"))
        * (1 + CLICK_UPGRADE_BONUS * state.get("click_level", 0))
    )


def total_earned_prestige(state):
    return int(math.sqrt(max(0, state.get("total_alltime", 0)) / ASCEND_DIVISOR))


def prestige_gain_available(state):
    return max(0, total_earned_prestige(state) - state.get("prestige_points", 0))


def prestige_threshold(points):
    """Lifetime Bytes needed to have earned this many points in total."""
    return (points ** 2) * ASCEND_DIVISOR


def stat_value(state, key):
    if key == "lifetime":
        return state.get("total_alltime", 0)
    if key == "max_owned":
        return max(state["buildings"].values(), default=0)
    if key == "prestige":
        return state.get("prestige_points", 0)
    if key == "shop_total":
        return sum(state.get("shop", {}).values())
    if key == "cps":
        return total_cps(state)
    return state.get(key, 0)      # clicks / crits / golden


def new_state():
    return {
        "score": 0, "total_alltime": 0, "click_power": 1, "click_level": 0,
        "buildings": {}, "prestige_points": 0, "prestige_spent": 0, "shop": {},
        "clicks": 0, "crits": 0, "golden": 0, "ach": [], "buy_mode": 0, "last_seen": time.time(),
    }


def _write_state(state):
    state["last_seen"] = time.time()
    SAVE_PATH.write_text(json.dumps(state), encoding="utf-8")


# ---------- Ghost cursor (decoration for the Auto Clicker) ----------

class GhostCursor(QWidget):
    """A small pointer that wanders over the click button and taps while the Auto Clicker runs.
    Purely visual - the real auto clicks happen in the game loop."""
    TIP = QPoint(2, 1)    # where the arrow's tip sits inside this widget

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(22, 30)
        self._dip = 0.0
        self._tap_anim = QVariantAnimation(self)
        self._tap_anim.setDuration(160)
        self._tap_anim.setStartValue(0.0)
        self._tap_anim.setEndValue(1.0)
        self._tap_anim.valueChanged.connect(self._set_dip)
        self._move_anim = QPropertyAnimation(self, b"pos", self)
        self._move_anim.setDuration(900)
        self._move_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def _set_dip(self, t):
        self._dip = 4 * math.sin(math.pi * float(t))      # presses down a few pixels, then back up
        self.update()

    def tap(self):
        self._tap_anim.stop()
        self._tap_anim.start()

    def glide_to(self, pos):
        self._move_anim.stop()
        self._move_anim.setStartValue(self.pos())
        self._move_anim.setEndValue(pos)
        self._move_anim.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(0, self._dip)
        points = ((2, 1), (2, 20), (6.5, 16), (10, 24.5), (13.5, 23), (10, 15), (16, 15))
        p.setPen(QPen(QColor("#0d1117"), 1.4))
        p.setBrush(QColor("#e6edf3"))
        p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))


# ---------- Widget ----------

class ClickerGame(QWidget):
    # NavStack reads this off the widget to resize the panel while the game is open
    PANEL_SIZE = (480, 700)

    def __init__(self):
        super().__init__()
        self.state = self._load()
        self._save()

        self.buffs = {}            # "frenzy"/"clickfrenzy" -> monotonic expiry time
        self.event_text = ""
        self.event_until = 0.0
        self.combo = 0
        self._last_click = 0.0
        self._auto_acc = 0.0
        self._auto_crit_next = 0.0    # earliest time the next small auto-crit text may appear
        self._orb = None
        self._ticks = 0
        self._last_tick = time.monotonic()
        self._click_times = deque()      # timestamps of clicks in the last second, for the rate cap
        self._reset_armed = False
        self._reset_timer = QTimer(self)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.timeout.connect(self._disarm_reset)
        self.buy_index = min(self.state.get("buy_mode", 0), len(BUY_AMOUNTS) - 1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.stack.addWidget(self._build_main())
        self.stack.addWidget(self._build_shop())
        self.stack.addWidget(self._build_trophies())
        self.stack.addWidget(self._build_settings())
        self.ghost = GhostCursor(self)
        self.ghost.hide()

        # ---------- Timers ----------
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(TICK_MS)

        self.golden_timer = QTimer(self)
        self.golden_timer.setSingleShot(True)
        self.golden_timer.timeout.connect(self._spawn_golden)
        self.orb_timer = QTimer(self)
        self.orb_timer.setSingleShot(True)
        self.orb_timer.timeout.connect(self._remove_orb)
        self._schedule_golden()

        # cosmetic only: a ghost cursor wanders over the click button and taps while the Auto Clicker runs
        self.auto_vis_timer = QTimer(self)
        self.auto_vis_timer.timeout.connect(self.ghost.tap)
        self.ghost_timer = QTimer(self)
        self.ghost_timer.timeout.connect(self._ghost_wander)

        # the panel deletes this widget on Back - save one last time when that happens
        self.destroyed.connect(lambda _=None, s=self.state: _write_state(s))

        self._check_achievements(silent=True)
        self._refresh()

    # ---------- Functions (building the pages) ----------

    def _build_main(self):
        main = QWidget()
        layout = QVBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        if self._offline_gain > 0:
            welcome = QLabel(f"+{fmt(self._offline_gain)} Bytes while you were away")
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

        # fixed 2x2 grid: each effect always has its own cell, so nothing shifts or runs together
        status = QWidget()
        status.setFixedHeight(36)
        grid = QGridLayout(status)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        self.slots = {}
        for key, (row, col, color) in {
            "event": (0, 0, "#f2cc60"), "combo": (0, 1, "#00e5ff"),
            "frenzy": (1, 0, "#ffa657"), "clickfrenzy": (1, 1, "#79c0ff"),
        }.items():
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
            grid.addWidget(lbl, row, col)
            self.slots[key] = lbl
        layout.addWidget(status)

        self.prestige_label = QLabel()
        self.prestige_label.setStyleSheet("color: #a371f7;")
        self.prestige_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.prestige_label)

        self.prestige_bar = QProgressBar()
        self.prestige_bar.setRange(0, 1000)
        self.prestige_bar.setTextVisible(False)
        self.prestige_bar.setFixedHeight(8)
        self.prestige_bar.setStyleSheet(BAR_STYLE)
        layout.addWidget(self.prestige_bar)

        row = QHBoxLayout()
        self.ascend_btn = QPushButton()
        self.ascend_btn.setStyleSheet(PURPLE_STYLE)
        self.ascend_btn.clicked.connect(self.ascend)
        row.addWidget(self.ascend_btn)
        self.shop_btn = QPushButton()
        self.shop_btn.setStyleSheet(PURPLE_STYLE)
        self.shop_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        row.addWidget(self.shop_btn)
        self.trophy_btn = QPushButton()
        self.trophy_btn.setStyleSheet(PURPLE_STYLE)
        self.trophy_btn.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        row.addWidget(self.trophy_btn)
        layout.addLayout(row)

        click_row = QHBoxLayout()
        self.click_btn = QPushButton("CLICK")
        self.click_btn.setFixedHeight(64)
        self.click_btn.setStyleSheet(CLICK_STYLE)
        self.click_btn.clicked.connect(self.on_click)
        click_row.addWidget(self.click_btn, 3)

        self.click_upgrade_btn = QPushButton()
        self.click_upgrade_btn.setFixedHeight(64)
        self.click_upgrade_btn.setStyleSheet(BTN_STYLE)
        self.click_upgrade_btn.clicked.connect(self.buy_click_upgrade)
        click_row.addWidget(self.click_upgrade_btn, 2)
        layout.addLayout(click_row)

        self.auto_label = QLabel()
        self.auto_label.setFixedHeight(16)
        self.auto_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.auto_label.setStyleSheet("color: #3fb950;")
        layout.addWidget(self.auto_label)

        amount_row = QHBoxLayout()
        amount_row.addWidget(QLabel("Buy:"))
        self.amount_btns = []
        for i, amount in enumerate(BUY_AMOUNTS):
            btn = QPushButton("MAX" if amount == "MAX" else f"{amount}x")
            btn.setCheckable(True)
            btn.setChecked(i == self.buy_index)
            btn.setStyleSheet(AMOUNT_STYLE)
            btn.clicked.connect(lambda checked, idx=i: self._set_buy_index(idx))
            amount_row.addWidget(btn)
            self.amount_btns.append(btn)
        amount_row.addStretch()
        settings_btn = QPushButton("Settings")
        settings_btn.setStyleSheet(AMOUNT_STYLE)
        settings_btn.clicked.connect(lambda: self.stack.setCurrentIndex(3))
        amount_row.addWidget(settings_btn)
        layout.addLayout(amount_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        buildings_layout = QVBoxLayout(container)
        buildings_layout.setSpacing(4)
        # built ONCE and updated in place - rebuilding every tick was eating clicks mid-press
        self.building_btns, self.building_max = {}, {}
        for b in BUILDINGS:
            line = QHBoxLayout()
            line.setSpacing(4)
            btn = QPushButton()
            btn.setStyleSheet(BTN_STYLE)
            btn.clicked.connect(lambda checked, bid=b["id"]: self.buy_building(bid, BUY_AMOUNTS[self.buy_index]))
            line.addWidget(btn, 1)
            maxbtn = QPushButton("MAX")
            maxbtn.setFixedWidth(64)
            maxbtn.setStyleSheet(MAX_STYLE)
            maxbtn.clicked.connect(lambda checked, bid=b["id"]: self.buy_building(bid, "MAX"))
            line.addWidget(maxbtn)
            buildings_layout.addLayout(line)
            self.building_btns[b["id"]] = btn
            self.building_max[b["id"]] = maxbtn
        scroll.setWidget(container)
        layout.addWidget(scroll)
        return main

    def _page(self, title_widget_attr):
        """Shared layout for the shop and trophies pages: Back button + header label + scroll area."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        top = QHBoxLayout()
        back = QPushButton("< Back")
        back.setStyleSheet(PURPLE_STYLE)
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        top.addWidget(back)
        header = QLabel()
        header.setStyleSheet("color: #a371f7; font-weight: bold;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        setattr(self, title_widget_attr, header)
        top.addWidget(header, 1)
        lay.addLayout(top)
        return page, lay

    def _build_shop(self):
        page, lay = self._page("shop_points_label")
        hint = QLabel("Permanent upgrades. They survive Ascending, and spending points never lowers your prestige bonus.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b949e;")
        lay.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        items = QVBoxLayout(container)
        items.setSpacing(4)
        self.shop_btns = {}
        for item in SHOP:
            btn = QPushButton()
            btn.setStyleSheet(SHOP_STYLE)
            btn.clicked.connect(lambda checked, iid=item["id"]: self.buy_shop(iid))
            items.addWidget(btn)
            self.shop_btns[item["id"]] = btn
        items.addStretch()
        scroll.setWidget(container)
        lay.addWidget(scroll)
        return page

    def _build_trophies(self):
        page, lay = self._page("trophy_header")
        self.stats_label = QLabel()
        self.stats_label.setWordWrap(True)
        self.stats_label.setStyleSheet("color: #8b949e;")
        lay.addWidget(self.stats_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        items = QVBoxLayout(container)
        items.setSpacing(3)
        self.ach_labels = {}
        for ach in ACHIEVEMENTS:
            label = QLabel()
            label.setWordWrap(True)
            items.addWidget(label)
            self.ach_labels[ach[0]] = label
        items.addStretch()
        scroll.setWidget(container)
        lay.addWidget(scroll)
        return page

    def _build_settings(self):
        page, lay = self._page("settings_header")
        self.settings_header.setText("Settings")
        info = QLabel(f"Progress is saved automatically to:\n{SAVE_PATH}")
        info.setWordWrap(True)
        info.setStyleSheet("color: #8b949e;")
        lay.addWidget(info)
        self.reset_btn = QPushButton("Reset all progress")
        self.reset_btn.setStyleSheet(PURPLE_STYLE.replace("#a371f7", "#f85149"))
        self.reset_btn.clicked.connect(self._reset_pressed)
        lay.addWidget(self.reset_btn)
        warn = QLabel("Wipes EVERYTHING: Bytes, buildings, prestige, shop upgrades and trophies. "
                      "Useful for testing the game from the very start.")
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #8b949e;")
        lay.addWidget(warn)
        lay.addStretch()
        return page

    def _reset_pressed(self):
        if not self._reset_armed:                       # first click only arms it
            self._reset_armed = True
            self.reset_btn.setText("Click again to ERASE EVERYTHING (5s)")
            self._reset_timer.start(5000)
            return
        self._do_reset()

    def _disarm_reset(self):
        self._reset_armed = False
        self.reset_btn.setText("Reset all progress")

    def _do_reset(self):
        self._reset_timer.stop()
        self._disarm_reset()
        self.state.clear()                              # mutate in place: other code holds this same dict
        self.state.update(new_state())
        self.buffs.clear()
        self.combo = 0
        self._auto_acc = 0.0
        self._click_times.clear()
        self.event_text, self.event_until = "", 0.0
        self.buy_index = 0
        for i, btn in enumerate(self.amount_btns):
            btn.setChecked(i == 0)
        self._save()
        self._refresh()
        self.stack.setCurrentIndex(0)

    # ---------- Functions (save/load) ----------

    def _load(self):
        now = time.time()
        if SAVE_PATH.exists():
            data = json.loads(SAVE_PATH.read_text(encoding="utf-8"))
            data.setdefault("buildings", {})
            data.setdefault("total_alltime", data.get("score", 0))
            data.setdefault("prestige_points", 0)
            data.setdefault("prestige_spent", 0)
            data.setdefault("shop", {})
            data.setdefault("click_power", 1)
            data.setdefault("click_level", 0)
            for key in ("clicks", "crits", "golden", "buy_mode"):
                data.setdefault(key, 0)
            data.setdefault("ach", [])

            gain = 0
            if OFFLINE_ENABLED:
                elapsed = max(0, now - data.get("last_seen", now))
                if OFFLINE_CAP_SECONDS:
                    elapsed = min(elapsed, OFFLINE_CAP_SECONDS)
                gain = elapsed * total_cps(data) * OFFLINE_RATE
            data["score"] = data.get("score", 0) + gain
            data["total_alltime"] = data.get("total_alltime", 0) + gain
            self._offline_gain = gain
            return data

        self._offline_gain = 0
        return new_state()

    def _save(self):
        _write_state(self.state)

    # ---------- Functions (floating text) ----------

    def _click_center(self):
        return self.click_btn.mapTo(self, self.click_btn.rect().center())

    def _float_text(self, text, rgb=(0, 229, 255), big=False, pos=None, size=None, rise=None):
        """Text that flies up from the cursor (or `pos`) and fades out. Re-styles the
        label's color alpha each frame instead of using a graphics effect, which can
        break translucent windows on Windows."""
        if pos is None:
            pos = self.mapFromGlobal(QCursor.pos())
        size = size or (18 if big else 13)
        rise = rise or FLOAT_RISE
        lbl = QLabel(text, self)
        lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        def style(alpha):
            lbl.setStyleSheet(
                f"background: transparent; color: rgba({rgb[0]},{rgb[1]},{rgb[2]},{alpha}); "
                f"font-size: {size}px; font-weight: bold;"
            )

        style(255)
        hint = lbl.sizeHint()
        lbl.resize(hint.width() + 10, hint.height() + 4)
        x = pos.x() - lbl.width() // 2 + random.randint(-14, 14)
        y0 = pos.y() - 12
        lbl.move(x, y0)
        lbl.show()
        lbl.raise_()

        anim = QVariantAnimation(lbl)
        anim.setDuration(FLOAT_MS)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)

        def step(t):
            t = float(t)
            lbl.move(x, int(y0 - rise * (1 - (1 - t) ** 3)))
            style(255 if t < 0.4 else max(0, int(255 * (1 - t) / 0.6)))

        anim.valueChanged.connect(step)
        anim.finished.connect(lbl.deleteLater)
        anim.start()

    # ---------- Functions (buffs and golden orbs) ----------

    def _active(self, name):
        return self.buffs.get(name, 0) > time.monotonic()

    def _prod_mult(self):
        return FRENZY_MULT if self._active("frenzy") else 1

    def _click_mult(self):
        return CLICK_FRENZY_MULT if self._active("clickfrenzy") else 1

    def _combo_mult(self):
        return 1 + min(self.combo, COMBO_MAX) * COMBO_BONUS

    def _schedule_golden(self):
        shrink = 0.85 ** shop_level(self.state, "orbs")
        self.golden_timer.start(int(random.uniform(*GOLDEN_INTERVAL) * shrink * 1000))

    def _spawn_golden(self):
        if self._orb is None:
            orb = QPushButton("*", self)
            orb.setFixedSize(44, 44)
            orb.setStyleSheet(GOLD_STYLE)
            orb.clicked.connect(self._pop_golden)
            x = random.randint(10, max(11, self.width() - 54))
            y = random.randint(60, max(61, self.height() - 54))
            orb.move(x, y)
            orb.show()
            orb.raise_()
            self._orb = orb
        self.orb_timer.start(GOLDEN_LIFETIME * 1000)

    def _remove_orb(self):
        if self._orb is not None:
            self._orb.deleteLater()
            self._orb = None
        self._schedule_golden()

    def _pop_golden(self):
        self.orb_timer.stop()
        self._remove_orb()

        s = self.state
        s["golden"] += 1
        now = time.monotonic()
        extra = 5 * shop_level(s, "extender")
        roll = random.random()
        if roll < 0.5:
            # Cookie Clicker's "Lucky": 15% of bank or 15 min of production, whichever is smaller, +13
            gain = min(s["score"] * 0.15, total_cps(s) * 900) + 13
            s["score"] += gain
            s["total_alltime"] += gain
            self.event_text = f"LUCKY! +{fmt(gain)}"
            self.event_until = now + 4
        elif roll < 0.85:
            self.buffs["frenzy"] = now + FRENZY_SECONDS + extra
        else:
            self.buffs["clickfrenzy"] = now + CLICK_FRENZY_SECONDS + extra
        self._refresh()
        self._save()

    # ---------- Functions (achievements) ----------

    def _check_achievements(self, silent=False):
        s = self.state
        for aid, name, _desc, stat, threshold in ACHIEVEMENTS:
            if aid not in s["ach"] and stat_value(s, stat) >= threshold:
                s["ach"].append(aid)
                if not silent:
                    self.event_text = f"TROPHY: {name}"
                    self.event_until = time.monotonic() + 4

    # ---------- Functions (UI refresh) ----------

    def _set_buy_index(self, idx):
        self.buy_index = idx
        self.state["buy_mode"] = idx
        for i, btn in enumerate(self.amount_btns):
            btn.setChecked(i == idx)
        self._refresh()

    def _refresh(self):
        s = self.state
        now = time.monotonic()
        rate = total_cps(s) * self._prod_mult()
        clk = click_value(s) * self._click_mult() * self._combo_mult()

        self.score_label.setText(f"{fmt(s['score'])} Bytes")
        self.click_btn.setText(f"CLICK   +{fmt(clk)}")
        self.rate_label.setText(
            f"+{fmt(clk)} / click ({crit_chance(s) * 100:.0f}% crit)   |   +{fmt(rate)} / sec"
        )
        self._sync_auto_visual()

        self.slots["event"].setText(self.event_text if self.event_until > now else "")
        self.slots["combo"].setText(f"COMBO x{self.combo}  (+{min(self.combo, COMBO_MAX) * COMBO_BONUS * 100:.0f}%)" if self.combo >= 5 else "")
        for name, label in (("frenzy", f"PRODUCTION x{FRENZY_MULT}"), ("clickfrenzy", f"CLICKS x{CLICK_FRENZY_MULT}")):
            left = self.buffs.get(name, 0) - now
            self.slots[name].setText(f"{label}  {left:.0f}s" if left > 0 else "")

        points = s["prestige_points"]
        gain = prestige_gain_available(s)
        lo, hi = prestige_threshold(points), prestige_threshold(points + 1)
        pct = points * PRESTIGE_BONUS_PER_POINT * 100
        self.prestige_label.setText(
            f"Prestige {points} (+{pct:.0f}%)  |  next at {fmt(hi)}  |  have {fmt(s['total_alltime'])}"
        )
        frac = 1.0 if gain > 0 else max(0.0, min(1.0, (s["total_alltime"] - lo) / max(1, hi - lo)))
        self.prestige_bar.setValue(int(frac * 1000))
        self.ascend_btn.setText(f"Ascend (+{gain})" if gain > 0 else "Ascend")
        self.ascend_btn.setEnabled(gain > 0)

        avail = points_available(s)
        self.shop_btn.setText(f"Shop ({fmt(avail)})")
        self.shop_points_label.setText(f"{fmt(avail)} points to spend")
        for item in SHOP:
            lvl = shop_level(s, item["id"])
            btn = self.shop_btns[item["id"]]
            if lvl >= item["max"]:
                btn.setText(f"{item['name']}  (Lv {lvl}/{item['max']})\n{item['desc']}  |  MAXED")
                btn.setEnabled(False)
            else:
                cost = shop_cost(item, lvl)
                btn.setText(f"{item['name']}  (Lv {lvl}/{item['max']})\n{item['desc']}  |  cost {fmt(cost)} pts")
                btn.setEnabled(avail >= cost)

        done = len(s["ach"])
        self.trophy_btn.setText(f"Trophies {done}/{len(ACHIEVEMENTS)}")
        self.trophy_header.setText(f"{done}/{len(ACHIEVEMENTS)} trophies  (+{done * ACHIEVEMENT_BONUS * 100:.0f}% production)")
        self.stats_label.setText(
            f"Clicks {fmt(s['clicks'])}   Crits {fmt(s['crits'])}   Golden orbs {fmt(s['golden'])}   "
            f"Lifetime {fmt(s['total_alltime'])}"
        )
        for aid, name, desc, _stat, _thr in ACHIEVEMENTS:
            got = aid in s["ach"]
            self.ach_labels[aid].setText(f"{'[x]' if got else '[ ]'} {name}: {desc}")
            self.ach_labels[aid].setStyleSheet("color: #3fb950;" if got else "color: #4d5560;")

        cost = click_upgrade_cost(s["click_level"])
        self.click_upgrade_btn.setText(f"Upgrade click power\nLv {s['click_level']}  (+1 and +{CLICK_UPGRADE_BONUS * 100:.0f}% each)\nCost: {fmt(cost)}")
        self.click_upgrade_btn.setEnabled(s["score"] >= cost)

        amount = BUY_AMOUNTS[self.buy_index]
        for b in BUILDINGS:
            owned = s["buildings"].get(b["id"], 0)
            can_max = max_affordable(b, owned, s["score"], s)
            n = max(1, can_max) if amount == "MAX" else amount
            cost = bulk_cost(b, owned, n, s)
            each = b["cps"] * milestone_mult(owned) * prestige_multiplier(s)
            nxt = next_milestone(owned)
            tail = f"  |  x2 at {nxt}" if nxt else "  |  maxed"
            btn = self.building_btns[b["id"]]
            btn.setText(f"{b['name']} ({owned})  +{n}\ncost {fmt(cost)}  |  +{fmt(each)}/sec each{tail}")
            btn.setEnabled(s["score"] >= cost)
            mx = self.building_max[b["id"]]
            mx.setText(f"MAX {can_max}" if can_max else "MAX")
            mx.setEnabled(can_max >= 1)

    # ---------- Functions (auto clicker visuals) ----------

    def _ghost_target(self):
        """A spot on the click button, kept off the centered CLICK text."""
        top_left = self.click_btn.mapTo(self, QPoint(0, 0))
        w, h = self.click_btn.width(), self.click_btn.height()
        side = random.choice(((0.08, 0.30), (0.70, 0.92)))
        x = top_left.x() + int(w * random.uniform(*side))
        y = top_left.y() + int(h * random.uniform(0.15, 0.5))
        return QPoint(x, y) - GhostCursor.TIP

    def _ghost_tip(self):
        return self.ghost.pos() + GhostCursor.TIP

    def _ghost_wander(self):
        if self.ghost.isVisible():
            self.ghost.glide_to(self._ghost_target())

    def _sync_auto_visual(self):
        s = self.state
        rate = shop_level(s, "autoclick") * AUTO_CLICKS_PER_LEVEL
        if rate <= 0:
            self.auto_label.setText("")
            self.auto_vis_timer.stop()
            self.ghost_timer.stop()
            self.ghost.hide()
            return
        # expected Bytes per second from auto clicks, counting crits and any click frenzy
        per_click = click_value(s) * self._click_mult() * (1 + crit_chance(s) * (crit_multiplier(s) - 1))
        if AUTO_CLICKS_USE_COMBO:
            per_click *= self._combo_mult()
        self.auto_label.setText(f"Auto Clicker: {rate:g} clicks/sec  =  about {fmt(rate * per_click)} Bytes/sec")
        if self.stack.currentIndex() != 0:
            self.ghost.hide()
            return
        if not self.ghost.isVisible():
            self.ghost.move(self._ghost_target())
            self.ghost.show()
            self.ghost.raise_()
        tap_ms = int(1000 / min(rate, 4))          # taps at the real rate, capped so it stays calm
        if not self.auto_vis_timer.isActive() or self.auto_vis_timer.interval() != tap_ms:
            self.auto_vis_timer.start(tap_ms)
        if not self.ghost_timer.isActive():
            self.ghost_timer.start(1600)

    # ---------- Functions (actions) ----------

    def _click_once(self, auto=False):
        """THE click. Manual clicks and Auto Clicker clicks both come through here, so they
        get the same click value, upgrades, crits, frenzy, combo and stats."""
        s = self.state
        use_combo = (not auto) or AUTO_CLICKS_USE_COMBO
        if use_combo:
            now = time.monotonic()
            self.combo = self.combo + 1 if now - self._last_click <= COMBO_WINDOW else 1
            self._last_click = now
        s["clicks"] += 1
        gain = click_value(s) * self._click_mult()
        # rate cap: however fast clicks arrive, total click income stops at the cap (owned auto clicks raise it)
        t = time.monotonic()
        self._click_times.append(t)
        while self._click_times and t - self._click_times[0] > 1.0:
            self._click_times.popleft()
        cap = max(CLICK_RATE_CAP, shop_level(s, "autoclick") * AUTO_CLICKS_PER_LEVEL)
        gain *= min(1.0, cap / len(self._click_times))
        if use_combo:
            gain *= self._combo_mult()
        crit = random.random() < crit_chance(s)
        if crit:
            gain *= crit_multiplier(s)
            s["crits"] += 1
        s["score"] += gain
        s["total_alltime"] += gain
        return gain, crit

    def on_click(self):
        gain, crit = self._click_once()
        if crit:
            self._float_text(f"CRIT! +{fmt(gain)}", (242, 204, 96), big=True)
        else:
            self._float_text(f"+{fmt(gain)}")
        self._refresh()

    def on_tick(self):
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        s = self.state

        gain = total_cps(s) * self._prod_mult() * dt
        if gain:
            s["score"] += gain
            s["total_alltime"] += gain

        level = shop_level(s, "autoclick")
        if level:
            self._auto_acc += level * AUTO_CLICKS_PER_LEVEL * dt
            n = min(int(self._auto_acc), 60)
            self._auto_acc -= int(self._auto_acc)
            crit_hit = False
            for _ in range(n):
                _value, crit = self._click_once(auto=True)
                crit_hit = crit_hit or crit
            if crit_hit and now >= self._auto_crit_next and self.stack.currentIndex() == 0:
                self._float_text("crit!", (242, 204, 96), pos=self._ghost_tip(), size=11, rise=22)
                self._auto_crit_next = now + 1.5

        if self.combo and now - self._last_click > COMBO_WINDOW:
            self.combo = 0

        self._ticks += 1
        if self._ticks % 4 == 0:
            self._check_achievements()
        if self._ticks % SAVE_EVERY_TICKS == 0:
            self._save()
        self._refresh()

    def buy_click_upgrade(self):
        cost = click_upgrade_cost(self.state["click_level"])
        if self.state["score"] >= cost:
            self.state["score"] -= cost
            self.state["click_power"] += 1
            self.state["click_level"] += 1
            self._refresh()
            self._save()

    def buy_building(self, building_id, amount):
        s = self.state
        building = next(b for b in BUILDINGS if b["id"] == building_id)
        owned = s["buildings"].get(building_id, 0)
        n = max_affordable(building, owned, s["score"], s) if amount == "MAX" else amount
        if n <= 0:
            return
        cost = bulk_cost(building, owned, n, s)
        if s["score"] >= cost:
            s["score"] -= cost
            s["buildings"][building_id] = owned + n
            self._check_achievements()
            self._refresh()
            self._save()

    def buy_shop(self, item_id):
        item = next(i for i in SHOP if i["id"] == item_id)
        lvl = shop_level(self.state, item_id)
        if lvl >= item["max"]:
            return
        cost = shop_cost(item, lvl)
        if points_available(self.state) >= cost:
            self.state["prestige_spent"] += cost
            self.state["shop"][item_id] = lvl + 1
            self._check_achievements()
            self._refresh()
            self._save()

    def ascend(self):
        s = self.state
        gain = prestige_gain_available(s)
        if gain <= 0:
            return
        s["prestige_points"] += gain
        s["score"] = 0
        s["click_power"] = 1
        s["click_level"] = 0
        lvl = shop_level(s, "headstart")
        s["buildings"] = {bid: count * lvl for bid, count in HEAD_START.items()} if lvl else {}
        self.combo = 0
        self._check_achievements()
        self._refresh()
        self._save()