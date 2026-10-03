"""
GAME: Clicker
An idle/clicker game built on Cookie Clicker's core math:
  - building cost = base * 1.15^owned
  - owning 25/50/100/... of a building doubles its output (milestones)
  - a click is worth a slice of your per-second rate, so clicking never dies
  - clicks can crit, with the damage floating up from your cursor
  - golden orbs pop up at random: lucky bonus, production frenzy, click frenzy
  - Ascend for permanent prestige points (sqrt scaled, +2% production each),
    then SPEND points in the Prestige Shop on permanent upgrades. Spending
    never lowers your prestige bonus, only the points you can still spend.

TO MAKE A NEW GAME: copy this whole file to games/yourgame.py, change
NAME, and replace the widget's contents.
"""
import json
import math
import random
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedWidget
)
from PyQt6.QtCore import Qt, QTimer, QVariantAnimation
from PyQt6.QtGui import QFont, QCursor

SAVE_PATH = Path(__file__).resolve().parent / "_clicker_save.json"

BTN_STYLE = """
QPushButton {
    background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 8px; padding: 6px; text-align: left;
}
QPushButton:hover { background-color: #21262d; border-color: #00e5ff; }
QPushButton:disabled { color: #4d5560; border-color: #21262d; }
"""
CLICK_STYLE = """
QPushButton {
    background-color: #161b22; color: #00e5ff; border: 1px solid #00e5ff;
    border-radius: 8px; padding: 10px; font-weight: bold; text-align: center;
}
QPushButton:hover { background-color: #21262d; }
QPushButton:pressed { background-color: #0d1117; }
"""
ASCEND_STYLE = """
QPushButton {
    background-color: #161b22; color: #a371f7; border: 1px solid #30363d;
    border-radius: 8px; padding: 8px; text-align: center;
}
QPushButton:hover { background-color: #21262d; border-color: #a371f7; }
QPushButton:disabled { color: #4d5560; border-color: #21262d; }
"""
SHOP_STYLE = """
QPushButton {
    background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 8px; padding: 6px; text-align: left;
}
QPushButton:hover { background-color: #21262d; border-color: #a371f7; }
QPushButton:disabled { color: #4d5560; border-color: #21262d; }
"""
GOLD_STYLE = """
QPushButton {
    background-color: #d29922; color: #0d1117; border: 2px solid #f2cc60;
    border-radius: 22px; font-weight: bold; font-size: 18px;
}
QPushButton:hover { background-color: #f2cc60; }
"""

# ---------- Game contract ----------
NAME = "Clicker"
PANEL_SIZE = (400, 580)   # a bit bigger than the default panel so the shop and buildings have room


def create_widget():
    return ClickerGame()


# ---------- Variables (balance knobs) ----------
COST_GROWTH = 1.15                 # Cookie Clicker's building cost growth
CLICK_UPGRADE_BASE_COST = 50
CLICK_UPGRADE_GROWTH = 1.25
CLICK_CPS_SHARE = 0.01             # each click also earns 1% of your base per-second rate
MILESTONES = [25, 50, 100, 150, 200, 250, 300]   # owning this many of a building doubles its output

ASCEND_DIVISOR = 100_000           # points = sqrt(lifetime / this)
PRESTIGE_BONUS_PER_POINT = 0.02    # +2% global production per prestige point earned, forever

# ---- Offline progress ----
OFFLINE_ENABLED = True             # False = nothing is earned while the game screen is closed
OFFLINE_RATE = 1.0                 # 1.0 = full speed, exactly like it was open the whole time
OFFLINE_CAP_SECONDS = None         # None = no limit. e.g. 8 * 3600 to stop counting after 8 hours

# ---- Clicking ----
CRIT_BASE_CHANCE = 0.05            # 5% of clicks crit before shop upgrades
CRIT_BASE_MULT = 5.0               # crits hit for x5 before shop upgrades
FLOAT_MS = 900                     # how long the floating "+123" text lives
FLOAT_RISE = 70                    # how many pixels it floats upward

# ---- Golden orbs ----
GOLDEN_INTERVAL = (30, 90)         # seconds between orbs (only counts while the game is open)
GOLDEN_LIFETIME = 12               # seconds an orb stays clickable
FRENZY_MULT, FRENZY_SECONDS = 7, 30                # production x7
CLICK_FRENZY_MULT, CLICK_FRENZY_SECONDS = 20, 15   # click value x20

TICK_MS = 250                      # game loop speed, so numbers visibly flow
SAVE_EVERY_TICKS = 20              # save every 5 seconds (plus on every purchase)

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

# Prestige Shop: permanent upgrades bought with prestige points.
# cost of next level = base * growth^level. max=None would mean uncapped.
SHOP = [
    {"id": "crit_chance", "name": "Critical Chance", "desc": "+1% crit chance",       "base": 5,  "growth": 1.25, "max": 25},
    {"id": "crit_power",  "name": "Critical Power",  "desc": "+0.5x crit damage",     "base": 10, "growth": 1.25, "max": 20},
    {"id": "fingers",     "name": "Strong Fingers",  "desc": "+10% click value",      "base": 5,  "growth": 1.25, "max": 40},
    {"id": "overclock",   "name": "Overclock",       "desc": "+5% all production",    "base": 8,  "growth": 1.25, "max": 40},
    {"id": "discount",    "name": "Bulk Discount",   "desc": "-2% building costs",    "base": 15, "growth": 1.30, "max": 15},
    {"id": "orbs",        "name": "Lucky Streak",    "desc": "-15% time between orbs", "base": 10, "growth": 2.00, "max": 5},
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


def building_cost(building, owned, state=None):
    discount = 0.98 ** shop_level(state, "discount") if state else 1.0
    return math.ceil(building["base_cost"] * (COST_GROWTH ** owned) * discount)


def click_upgrade_cost(level):
    return math.ceil(CLICK_UPGRADE_BASE_COST * (CLICK_UPGRADE_GROWTH ** level))


def milestone_mult(owned):
    return 2 ** sum(1 for m in MILESTONES if owned >= m)


def next_milestone(owned):
    return next((m for m in MILESTONES if owned < m), None)


def prestige_multiplier(state):
    """Prestige bonus from points earned, times the Overclock shop upgrade."""
    return (1 + PRESTIGE_BONUS_PER_POINT * state.get("prestige_points", 0)) * (1 + 0.05 * shop_level(state, "overclock"))


def base_cps(state):
    """Per-second output from buildings (with milestone doublers), before prestige."""
    return sum(
        state["buildings"].get(b["id"], 0) * b["cps"] * milestone_mult(state["buildings"].get(b["id"], 0))
        for b in BUILDINGS
    )


def total_cps(state):
    return base_cps(state) * prestige_multiplier(state)


def click_value(state):
    """Flat click power plus a slice of your passive rate, so clicks stay relevant late game."""
    return (
        (state["click_power"] + CLICK_CPS_SHARE * base_cps(state))
        * prestige_multiplier(state)
        * (1 + 0.10 * shop_level(state, "fingers"))
    )


def total_earned_prestige(state):
    """Prestige points your lifetime Bytes have ever earned (cumulative, sqrt scaled)."""
    return int(math.sqrt(max(0, state.get("total_alltime", 0)) / ASCEND_DIVISOR))


def prestige_gain_available(state):
    return max(0, total_earned_prestige(state) - state.get("prestige_points", 0))


def next_prestige_threshold(state):
    target = state.get("prestige_points", 0) + 1
    return (target ** 2) * ASCEND_DIVISOR


def _write_state(state):
    state["last_seen"] = time.time()
    SAVE_PATH.write_text(json.dumps(state), encoding="utf-8")


# ---------- Widget ----------

class ClickerGame(QWidget):
    def __init__(self):
        super().__init__()
        self.state = self._load()
        self._save()

        self.buffs = {}            # "frenzy"/"clickfrenzy" -> monotonic expiry time
        self.event_text = ""
        self.event_until = 0.0
        self._orb = None
        self._ticks = 0
        self._last_tick = time.monotonic()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        # ---------- Main page ----------
        main = QWidget()
        layout = QVBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

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

        self.buff_label = QLabel()
        self.buff_label.setFixedHeight(18)
        self.buff_label.setStyleSheet("color: #f2cc60; font-weight: bold;")
        self.buff_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.buff_label)

        self.prestige_label = QLabel()
        self.prestige_label.setStyleSheet("color: #a371f7;")
        self.prestige_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.prestige_label)

        prestige_row = QHBoxLayout()
        self.ascend_btn = QPushButton()
        self.ascend_btn.setStyleSheet(ASCEND_STYLE)
        self.ascend_btn.clicked.connect(self.ascend)
        prestige_row.addWidget(self.ascend_btn)

        self.shop_btn = QPushButton()
        self.shop_btn.setStyleSheet(ASCEND_STYLE)
        self.shop_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        prestige_row.addWidget(self.shop_btn)
        layout.addLayout(prestige_row)

        click_btn = QPushButton("Click me")
        click_btn.setStyleSheet(CLICK_STYLE)
        click_btn.clicked.connect(self.on_click)
        layout.addWidget(click_btn)

        self.click_upgrade_btn = QPushButton()
        self.click_upgrade_btn.setStyleSheet(BTN_STYLE)
        self.click_upgrade_btn.clicked.connect(self.buy_click_upgrade)
        layout.addWidget(self.click_upgrade_btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        buildings_layout = QVBoxLayout(container)
        buildings_layout.setSpacing(4)
        # built ONCE and updated in place - rebuilding every tick was eating clicks mid-press
        self.building_btns = {}
        for b in BUILDINGS:
            btn = QPushButton()
            btn.setStyleSheet(BTN_STYLE)
            btn.clicked.connect(lambda checked, bid=b["id"]: self.buy_building(bid))
            buildings_layout.addWidget(btn)
            self.building_btns[b["id"]] = btn
        scroll.setWidget(container)
        layout.addWidget(scroll)

        self.stack.addWidget(main)
        self.stack.addWidget(self._build_shop())

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

        # the panel deletes this widget on Back - save one last time when that happens
        self.destroyed.connect(lambda _=None, s=self.state: _write_state(s))

        self._refresh()

    def _build_shop(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        top = QHBoxLayout()
        back = QPushButton("< Back")
        back.setStyleSheet(ASCEND_STYLE)
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        top.addWidget(back)
        self.shop_points_label = QLabel()
        self.shop_points_label.setStyleSheet("color: #a371f7; font-weight: bold;")
        self.shop_points_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self.shop_points_label, 1)
        lay.addLayout(top)

        hint = QLabel("Permanent upgrades. They survive Ascending, and spending points never lowers your prestige bonus.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b949e;")
        lay.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        items_layout = QVBoxLayout(container)
        items_layout.setSpacing(4)
        self.shop_btns = {}
        for item in SHOP:
            btn = QPushButton()
            btn.setStyleSheet(SHOP_STYLE)
            btn.clicked.connect(lambda checked, iid=item["id"]: self.buy_shop(iid))
            items_layout.addWidget(btn)
            self.shop_btns[item["id"]] = btn
        items_layout.addStretch()
        scroll.setWidget(container)
        lay.addWidget(scroll)
        return page

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
        return {
            "score": 0, "total_alltime": 0, "click_power": 1, "click_level": 0,
            "buildings": {}, "prestige_points": 0, "prestige_spent": 0, "shop": {}, "last_seen": now,
        }

    def _save(self):
        _write_state(self.state)

    # ---------- Functions (floating text) ----------

    def _float_text(self, text, rgb=(0, 229, 255), big=False):
        """Text that flies up from the cursor and fades out. Drawn by re-styling
        the label's color alpha each frame (no graphics effect, which can break
        translucent windows on Windows)."""
        pos = self.mapFromGlobal(QCursor.pos())
        size = 18 if big else 13
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
        y0 = pos.y() - 28
        lbl.move(x, y0)
        lbl.show()
        lbl.raise_()

        anim = QVariantAnimation(lbl)
        anim.setDuration(FLOAT_MS)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)

        def step(t):
            t = float(t)
            lbl.move(x, int(y0 - FLOAT_RISE * (1 - (1 - t) ** 3)))   # fast start, eases out
            style(255 if t < 0.4 else max(0, int(255 * (1 - t) / 0.6)))   # holds, then fades

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
        now = time.monotonic()
        roll = random.random()
        if roll < 0.5:
            # Cookie Clicker's "Lucky": 15% of bank or 15 min of production, whichever is smaller, +13
            gain = min(s["score"] * 0.15, total_cps(s) * 900) + 13
            s["score"] += gain
            s["total_alltime"] += gain
            self.event_text = f"LUCKY! +{fmt(gain)}"
            self.event_until = now + 4
        elif roll < 0.85:
            self.buffs["frenzy"] = now + FRENZY_SECONDS
        else:
            self.buffs["clickfrenzy"] = now + CLICK_FRENZY_SECONDS
        self._refresh()
        self._save()

    # ---------- Functions (UI refresh) ----------

    def _refresh(self):
        s = self.state
        mult = self._prod_mult()
        rate = total_cps(s) * mult
        clk = click_value(s) * self._click_mult()

        self.score_label.setText(f"{fmt(s['score'])} Bytes")
        self.rate_label.setText(
            f"+{fmt(clk)} / click ({crit_chance(s) * 100:.0f}% crit)   |   +{fmt(rate)} / sec"
        )

        now = time.monotonic()
        parts = []
        if self.event_until > now:
            parts.append(self.event_text)
        for name, label in (("frenzy", f"FRENZY x{FRENZY_MULT}"), ("clickfrenzy", f"CLICK FRENZY x{CLICK_FRENZY_MULT}")):
            left = self.buffs.get(name, 0) - now
            if left > 0:
                parts.append(f"{label} {left:.0f}s")
        self.buff_label.setText("  |  ".join(parts))

        gain = prestige_gain_available(s)
        needed = next_prestige_threshold(s)
        pct = s["prestige_points"] * PRESTIGE_BONUS_PER_POINT * 100
        self.prestige_label.setText(
            f"Prestige {s['prestige_points']} (+{pct:.0f}%)  |  next at {fmt(needed)} lifetime ({fmt(s['total_alltime'])})"
        )
        self.ascend_btn.setText(f"Ascend (+{gain})" if gain > 0 else "Ascend (keep earning)")
        self.ascend_btn.setEnabled(gain > 0)

        avail = points_available(s)
        self.shop_btn.setText(f"Prestige Shop ({fmt(avail)} pts)")
        self.shop_points_label.setText(f"{fmt(avail)} points to spend")
        for item in SHOP:
            lvl = shop_level(s, item["id"])
            btn = self.shop_btns[item["id"]]
            if item["max"] is not None and lvl >= item["max"]:
                btn.setText(f"{item['name']}  (Lv {lvl}/{item['max']})\n{item['desc']}  |  MAXED")
                btn.setEnabled(False)
            else:
                cost = shop_cost(item, lvl)
                cap = f"/{item['max']}" if item["max"] is not None else ""
                btn.setText(f"{item['name']}  (Lv {lvl}{cap})\n{item['desc']}  |  cost {fmt(cost)} pts")
                btn.setEnabled(avail >= cost)

        cost = click_upgrade_cost(s["click_level"])
        self.click_upgrade_btn.setText(f"Upgrade click power +1 (cost: {fmt(cost)})")
        self.click_upgrade_btn.setEnabled(s["score"] >= cost)

        for b in BUILDINGS:
            owned = s["buildings"].get(b["id"], 0)
            cost = building_cost(b, owned, s)
            each = b["cps"] * milestone_mult(owned) * prestige_multiplier(s)
            nxt = next_milestone(owned)
            tail = f"  |  x2 at {nxt}" if nxt else "  |  maxed"
            btn = self.building_btns[b["id"]]
            btn.setText(f"{b['name']} ({owned})\ncost {fmt(cost)}  |  +{fmt(each)}/sec each{tail}")
            btn.setEnabled(s["score"] >= cost)

    # ---------- Functions (actions) ----------

    def on_click(self):
        s = self.state
        gain = click_value(s) * self._click_mult()
        crit = random.random() < crit_chance(s)
        if crit:
            gain *= crit_multiplier(s)
        s["score"] += gain
        s["total_alltime"] += gain
        if crit:
            self._float_text(f"CRIT! +{fmt(gain)}", (242, 204, 96), big=True)
        else:
            self._float_text(f"+{fmt(gain)}")
        self._refresh()

    def on_tick(self):
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now

        gain = total_cps(self.state) * self._prod_mult() * dt
        if gain:
            self.state["score"] += gain
            self.state["total_alltime"] += gain

        self._ticks += 1
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

    def buy_building(self, building_id):
        building = next(b for b in BUILDINGS if b["id"] == building_id)
        owned = self.state["buildings"].get(building_id, 0)
        cost = building_cost(building, owned, self.state)
        if self.state["score"] >= cost:
            self.state["score"] -= cost
            self.state["buildings"][building_id] = owned + 1
            self._refresh()
            self._save()

    def buy_shop(self, item_id):
        item = next(i for i in SHOP if i["id"] == item_id)
        lvl = shop_level(self.state, item_id)
        if item["max"] is not None and lvl >= item["max"]:
            return
        cost = shop_cost(item, lvl)
        if points_available(self.state) >= cost:
            self.state["prestige_spent"] += cost
            self.state["shop"][item_id] = lvl + 1
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