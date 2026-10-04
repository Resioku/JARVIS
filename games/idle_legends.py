"""
GAME: Idle Legends
An idle RPG. Your hero fights on their own through ten zones of monsters and
bosses. You choose a class, spend stat points, hunt gear drops (six rarities
with random affixes, enhancing and reforging), unlock auto-cast skills, train
for gold, and Rebirth for Soul Shards that buy permanent perks.

Inspired by the usual idle-RPG loop: exponential enemy scaling vs exponential
gear drops, boss-gated stages, prestige with a shard shop, and trophies.

Layout: everything is data-driven from the tables below (CLASSES, SKILLS,
AFFIX, TRAIN, PERKS, ACHIEVEMENTS, ZONES), so balance and content are easy to
change. The Engine class has no UI code in it.
"""
import json
import math
import random
import time
from collections import defaultdict
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedWidget,
    QProgressBar, QTextEdit, QListWidget, QListWidgetItem, QComboBox, QCheckBox, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QLinearGradient, QPainterPath

SAVE_PATH = Path(__file__).resolve().parent / "_idle_legends_save.json"

NAME = "Idle Legends"


def create_widget():
    return IdleLegends()


# ---------- Balance knobs ----------
MOBS_PER_STAGE = 5               # normal enemies before the stage boss appears
INV_CAP = 30                     # backpack size
OFFLINE_ENABLED = True
OFFLINE_RATE = 0.5               # share of normal kills earned while the game screen is closed
OFFLINE_CAP_SECONDS = 8 * 3600
REBIRTH_MIN_STAGE = 25           # best stage needed this life to Rebirth
TICK_MS = 100
ENEMY_HP_GROWTH = 1.27           # enemy health per stage. Gear grows 1.17x per stage, so enemies slowly outpace you
ENEMY_ATK_GROWTH = 1.20
ENEMY_GOLD_GROWTH = 1.17
ENEMY_XP_GROWTH = 1.14

# ---------- Content tables ----------
RARITIES = [("Common", "#9da7b3"), ("Uncommon", "#3fb950"), ("Rare", "#58a6ff"),
            ("Epic", "#a371f7"), ("Legendary", "#ff9f1a"), ("Mythic", "#ff4d6d")]
RARITY_MULT = [1.0, 1.25, 1.6, 2.1, 2.8, 3.8]
RARITY_WEIGHTS = [60, 28, 9, 2.5, 0.45, 0.05]
PREFIX = [
    ["Rusty", "Worn", "Plain", "Crude"], ["Sturdy", "Fine", "Polished", "Keen"],
    ["Runed", "Gleaming", "Tempered", "Warded"], ["Arcane", "Savage", "Royal", "Blessed"],
    ["Dragonforged", "Celestial", "Stormbound", "Ancient"], ["Voidforged", "Eternal", "Godslayer's", "Astral"],
]
# slot id, label, main stat, main multiplier, base names
SLOTS = [
    ("weapon", "Weapon", "atk", 3.0, ["Blade", "Axe", "Staff", "Dagger", "Mace"]),
    ("helmet", "Helmet", "hp", 10.0, ["Helm", "Hood", "Crown", "Cap"]),
    ("chest", "Chest", "hp", 18.0, ["Plate", "Robe", "Mail", "Vest"]),
    ("gloves", "Gloves", "atk", 1.6, ["Gauntlets", "Gloves", "Wraps"]),
    ("boots", "Boots", "def", 2.2, ["Greaves", "Boots", "Sandals"]),
    ("ring", "Ring", "atk", 1.4, ["Ring", "Band", "Signet"]),
    ("amulet", "Amulet", "def", 2.8, ["Amulet", "Pendant", "Talisman"]),
]
SLOT_INFO = {s[0]: s for s in SLOTS}
MAIN_LABEL = {"atk": "Attack", "hp": "Health", "def": "Defense"}

# key: (label, min, max)  - all values are percent (regen is % of max HP per second)
AFFIX = {
    "atk_pct": ("Attack", 5, 12), "hp_pct": ("Health", 5, 12), "def_pct": ("Defense", 5, 12),
    "crit": ("Crit Chance", 1, 3), "critdmg": ("Crit Damage", 8, 20), "aspd": ("Attack Speed", 3, 8),
    "gold": ("Gold Find", 5, 15), "xp": ("XP Gain", 5, 15), "drop": ("Drop Rate", 5, 12),
    "skill": ("Skill Power", 6, 15), "regen": ("HP Regen", 0.2, 0.6), "lifesteal": ("Lifesteal", 1, 3),
    "cdr": ("Cooldown Speed", 3, 8),
}

CLASSES = {
    "warrior": {"name": "Warrior", "icon": "\U0001F6E1", "desc": "+25% HP, +15% Defense. Hard to kill.",
                "mods": {"hp_pct": 25, "def_pct": 15}},
    "mage": {"name": "Mage", "icon": "\U0001F52E", "desc": "+30% Skill Power, +10% Cooldown Speed. Skills hit hard.",
             "mods": {"skill": 30, "cdr": 10}},
    "rogue": {"name": "Rogue", "icon": "\U0001F5E1", "desc": "+8% Crit, +15% Attack Speed. Fast and deadly.",
              "mods": {"crit": 8, "aspd": 15}},
}

STAT_KEYS = ["str", "vit", "dex", "int", "luk"]
STAT_INFO = {
    "str": ("Strength", "+1.5% Attack"), "vit": ("Vitality", "+1.5% HP, +1% Defense"),
    "dex": ("Dexterity", "+0.12% Crit, +0.25% Atk Speed, +0.4% Crit Dmg"),
    "int": ("Intellect", "+1.5% Skill Power, +0.1% Cooldown Speed"),
    "luk": ("Luck", "+0.8% Gold, +0.5% Drops, +0.3% XP"),
}
STAT_PCT = {
    "str": {"atk_pct": 1.5}, "vit": {"hp_pct": 1.5, "def_pct": 1.0},
    "dex": {"crit": 0.12, "aspd": 0.25, "critdmg": 0.4}, "int": {"skill": 1.5, "cdr": 0.1},
    "luk": {"gold": 0.8, "drop": 0.5, "xp": 0.3},
}
AUTO_WEIGHTS = {
    "off": None,
    "balanced": {"str": 3, "vit": 3, "dex": 1, "int": 1, "luk": 1},
    "attack": {"str": 4, "dex": 2, "vit": 1, "int": 1, "luk": 0.5},
    "tank": {"vit": 4, "str": 2, "dex": 1, "int": 0.5, "luk": 0.5},
}

# id, name, unlock level, cooldown, kind, power, description
SKILLS = [
    ("strike", "Power Strike", 1, 6, "dmg", 2.5, "Hit for {p}% Attack"),
    ("fire", "Fireball", 5, 10, "dmg", 4.5, "Burn for {p}% Attack"),
    ("mend", "Mend", 10, 18, "heal", 0.30, "Heal {p}% max HP"),
    ("skin", "Iron Skin", 15, 24, "shield", 0.5, "Take {p}% less damage for 6s"),
    ("exec", "Execute", 22, 14, "exec", 3.0, "Hit for {p}% Attack, x2.7 if foe is under 30% HP"),
    ("rage", "Berserk", 30, 40, "rage", 0, "+60% attack speed, +40% damage for 10s"),
    ("meteor", "Meteor", 40, 30, "dmg", 15.0, "Crush for {p}% Attack"),
    ("warp", "Time Warp", 50, 60, "warp", 0, "Instantly recharge every other skill"),
]
SKILL_BY_ID = {s[0]: s for s in SKILLS}
SKILL_MAX = 25

# id, name, effect text, stat, percent per level, base cost
TRAIN = [
    ("t_atk", "Weapon Drills", "+3% Attack", "atk_pct", 3, 40),
    ("t_hp", "Conditioning", "+3% Health", "hp_pct", 3, 40),
    ("t_def", "Shield Wall", "+3% Defense", "def_pct", 3, 60),
    ("t_gold", "Treasure Sense", "+3% Gold", "gold", 3, 80),
    ("t_xp", "Scholar", "+3% XP", "xp", 3, 80),
    ("t_crit", "Keen Eye", "+0.2% Crit Chance", "crit", 0.2, 150),
    ("t_aspd", "Fleet Footing", "+0.5% Attack Speed", "aspd", 0.5, 150),
]
TRAIN_GROWTH = 1.15

# id, name, effect text, stat, per level, base shard cost, max level
PERKS = [
    ("p_atk", "Ancient Might", "+10% Attack", "atk_pct", 10, 3, 50),
    ("p_hp", "Fortitude", "+10% Health", "hp_pct", 10, 3, 50),
    ("p_gold", "Greed", "+15% Gold", "gold", 15, 3, 50),
    ("p_xp", "Wisdom", "+10% XP", "xp", 10, 3, 50),
    ("p_drop", "Fortune", "+8% Drop Rate", "drop", 8, 4, 30),
    ("p_skill", "Arcana", "+10% Skill Power", "skill", 10, 4, 30),
    ("p_start", "Time Rift", "Start each life 8% further along your best stage", None, 0, 6, 10),
    ("p_cash", "Head Start", "Start each life with bonus gold", None, 0, 4, 10),
    ("p_off", "Dream Walker", "+10% offline efficiency", None, 0, 5, 5),
]
PERK_GROWTH = 1.45

# id, name, description, stat, threshold. Each trophy gives +1% damage and gold.
ACHIEVEMENTS = [
    ("k1", "First Blood", "Defeat 10 monsters", "kills", 10), ("k2", "Monster Hunter", "Defeat 500 monsters", "kills", 500),
    ("k3", "Exterminator", "Defeat 10,000 monsters", "kills", 10_000), ("k4", "Genocide", "Defeat 100,000 monsters", "kills", 100_000),
    ("b1", "Boss Slayer", "Defeat 10 bosses", "bosses", 10), ("b2", "Boss Hunter", "Defeat 200 bosses", "bosses", 200),
    ("b3", "Boss Rush", "Defeat 2,000 bosses", "bosses", 2_000),
    ("s1", "Adventurer", "Reach stage 10", "best_all", 10), ("s2", "Veteran", "Reach stage 30", "best_all", 30),
    ("s3", "Champion", "Reach stage 60", "best_all", 60), ("s4", "Legend", "Reach stage 100", "best_all", 100),
    ("s5", "Mythic", "Reach stage 150", "best_all", 150),
    ("l1", "Apprentice", "Reach level 10", "level", 10), ("l2", "Seasoned", "Reach level 30", "level", 30),
    ("l3", "Master", "Reach level 60", "level", 60), ("l4", "Grandmaster", "Reach level 100", "level", 100),
    ("i1", "Looter", "Find 50 items", "items", 50), ("i2", "Hoarder", "Find 1,000 items", "items", 1_000),
    ("i3", "Dragon's Hoard", "Find 10,000 items", "items", 10_000),
    ("c1", "Sharp Eyes", "Land 100 crits", "crits", 100), ("c2", "Critical Mass", "Land 5,000 crits", "crits", 5_000),
    ("g1", "Rich", "Earn 1M gold in total", "gold", 1e6), ("g2", "Tycoon", "Earn 1B gold in total", "gold", 1e9),
    ("g3", "Dragon Wealth", "Earn 1T gold in total", "gold", 1e12),
    ("r1", "Reborn", "Rebirth once", "rebirths", 1), ("r2", "Eternal Cycle", "Rebirth 10 times", "rebirths", 10),
    ("r3", "Soul Collector", "Earn 500 Soul Shards", "shards_total", 500),
    ("t1", "Tap Happy", "Smite 200 times", "smites", 200),
]

# name, (sky top, sky bottom), mobs [(name, emoji)], boss (name, emoji)
ZONES = [
    ("Whispering Meadow", ("#2d6a4f", "#1b4332"), [("Field Rat", "\U0001F400"), ("Wild Boar", "\U0001F417"), ("Giant Bee", "\U0001F41D"), ("Mud Slime", "\U0001F9A0")], ("Elder Stag", "\U0001F98C")),
    ("Goblin Warrens", ("#5c4a2a", "#2b2215"), [("Goblin", "\U0001F47A"), ("Cave Bat", "\U0001F987"), ("Giant Spider", "\U0001F577"), ("Hobgoblin", "\U0001F479")], ("Goblin King", "\U0001F451")),
    ("Cursed Crypt", ("#3a2d4f", "#1a1426"), [("Skeleton", "\U0001F480"), ("Zombie", "\U0001F9DF"), ("Ghost", "\U0001F47B"), ("Bone Rat", "\U0001F400")], ("Lich", "\u2620")),
    ("Ember Caverns", ("#7a2e1d", "#2e0f08"), [("Fire Imp", "\U0001F608"), ("Lava Crab", "\U0001F980"), ("Salamander", "\U0001F98E"), ("Magma Bat", "\U0001F987")], ("Ifrit", "\U0001F30B")),
    ("Frostpeak", ("#2b5876", "#14273a"), [("Ice Wolf", "\U0001F43A"), ("Yeti", "\U0001F98D"), ("Snow Owl", "\U0001F989"), ("Frost Wisp", "\u2744")], ("Frost Wyrm", "\U0001F409")),
    ("Sunken Ruins", ("#1d4e5f", "#0b222b"), [("Drowned", "\U0001F9DC"), ("Giant Crab", "\U0001F980"), ("Sea Serpent", "\U0001F40D"), ("Octopus", "\U0001F419")], ("Kraken", "\U0001F991")),
    ("Sky Citadel", ("#4a5a8a", "#1c2340"), [("Harpy", "\U0001F985"), ("Stone Golem", "\U0001F5FF"), ("Storm Spirit", "\u26A1"), ("Griffon", "\U0001F981")], ("Sky Titan", "\U0001F329")),
    ("Shadow Forest", ("#1f3a2f", "#0a1511"), [("Dire Wolf", "\U0001F43A"), ("Shade", "\U0001F464"), ("Treant", "\U0001F333"), ("Night Owl", "\U0001F989")], ("Nightmare", "\U0001F434")),
    ("Desert Tomb", ("#8a6a2a", "#3a2a0f"), [("Scarab", "\U0001F41B"), ("Mummy", "\U0001F915"), ("Sand Viper", "\U0001F40D"), ("Scorpion", "\U0001F982")], ("Pharaoh", "\U0001F3FA")),
    ("Void Rift", ("#3b1d5e", "#0d0617"), [("Void Eye", "\U0001F441"), ("Rift Walker", "\U0001F300"), ("Star Eater", "\u2B50"), ("Abyss Maw", "\U0001F573")], ("The Devourer", "\U0001F30C")),
]

SUFFIXES = ["", "K", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc"]


# ---------- Functions (math and data, no UI) ----------

def fmt(n):
    n = float(n)
    if n < 1000:
        return f"{n:,.0f}" if (n >= 100 or n == int(n)) else f"{n:.1f}"
    idx = min(int(math.log10(n) // 3), len(SUFFIXES) - 1)
    return f"{n / 1000 ** idx:.2f}{SUFFIXES[idx]}"


def new_state():
    return {
        "cls": None, "level": 1, "xp": 0.0, "points": 0, "stats": {k: 0 for k in STAT_KEYS}, "sp": 0, "skills": {},
        "gold": 0.0, "scrap": 0, "shards": 0, "shards_total": 0, "rebirths": 0,
        "stage": 1, "kills": 0, "best": 1, "best_all": 1,
        "equipped": {s[0]: None for s in SLOTS}, "inv": [], "train": {}, "perks": {}, "ach": [],
        "auto_adv": True, "auto_eq": True, "auto_sell": 1, "auto_stats": "balanced", "buy_mode": 0,
        "st": {"kills": 0, "bosses": 0, "items": 0, "crits": 0, "gold": 0.0, "smites": 0},
        "uid": 1, "last_seen": time.time(),
    }


def item_main(it):
    return it["main"] * (1 + 0.08 * it["plus"])


def item_main_stat(it):
    return SLOT_INFO[it["slot"]][2]


def sell_value(it):
    return round(it["main"] * 2.2 * (1 + it["rarity"]) * (1 + 0.5 * it["plus"]))


def enhance_cost(it):
    return round(18 * 1.17 ** it["ilvl"] * 1.35 ** it["plus"] * math.sqrt(it["rarity"] + 1))


def reforge_cost(it):
    return 3 * (it["rarity"] + 1)


def roll_affix(key, ilvl, rarity, rng):
    _label, lo, hi = AFFIX[key]
    q = min(1.0, rng.random() * 0.7 + rarity * 0.06)
    return round((lo + (hi - lo) * q) * (1 + ilvl / 150), 2 if hi < 1 else 1)


def make_item(slot, ilvl, rarity, rng, uid):
    _id, _label, stat, mult, bases = SLOT_INFO[slot]
    main = mult * 1.17 ** ilvl * RARITY_MULT[rarity]
    keys = rng.sample(list(AFFIX), rarity)
    return {
        "uid": uid, "slot": slot, "rarity": rarity, "ilvl": ilvl, "plus": 0, "main": main,
        "aff": [[k, roll_affix(k, ilvl, rarity, rng)] for k in keys],
        "name": f"{rng.choice(PREFIX[rarity])} {rng.choice(bases)}",
    }


def roll_rarity(rng, drop, min_rarity):
    weights = [w * (drop ** (i / 2)) if i >= 2 else w for i, w in enumerate(RARITY_WEIGHTS)]
    pick = rng.random() * sum(weights)
    for i, w in enumerate(weights):
        pick -= w
        if pick <= 0:
            return max(i, min_rarity)
    return max(len(weights) - 1, min_rarity)


def zone_of(g):
    return ZONES[((g - 1) // 10) % len(ZONES)], ((g - 1) // 10) // len(ZONES)


def enemy_for(g, boss, zboss, rng):
    zone, _cycle = zone_of(g)
    hp, atk = 30 * ENEMY_HP_GROWTH ** (g - 1), 5 * ENEMY_ATK_GROWTH ** (g - 1)
    gold, xp = 4 * ENEMY_GOLD_GROWTH ** (g - 1), 5 * ENEMY_XP_GROWTH ** (g - 1)
    if boss:
        hp, atk, gold, xp = hp * 6, atk * 1.4, gold * 6, xp * 5
    if zboss:
        hp, atk, gold, xp = hp * 1.8, atk * 1.2, gold * 3, xp * 3
    name, emoji = zone[3] if boss else rng.choice(zone[2])
    if zboss:
        name = f"{name} (Zone Boss)"
    return {"name": name, "emoji": emoji, "hp": hp, "atk": atk, "gold": gold, "xp": xp, "boss": boss, "zboss": zboss}


def xp_needed(level):
    return 40 * 1.27 ** (level - 1)


def derive(s, equipped=None):
    """Every combat number, from level, stats, gear, class, training, perks and trophies."""
    eq = s["equipped"] if equipped is None else equipped
    flat = {"atk": 0.0, "hp": 0.0, "def": 0.0}
    pct = defaultdict(float)
    for it in eq.values():
        if it:
            flat[item_main_stat(it)] += item_main(it)
            for k, v in it["aff"]:
                pct[k] += v
    for stat, n in s["stats"].items():
        for k, per in STAT_PCT[stat].items():
            pct[k] += per * n
    for k, v in CLASSES.get(s["cls"], {"mods": {}})["mods"].items():
        pct[k] += v
    for _id, _n, _e, stat, per, _c in TRAIN:
        pct[stat] += per * s["train"].get(_id, 0)
    for pid, _n, _e, stat, per, _c, _m in PERKS:
        if stat:
            pct[stat] += per * s["perks"].get(pid, 0)
    lvl = s["level"]
    ach = 1 + 0.01 * len(s["ach"])
    shard = 1 + 0.02 * s["shards_total"]
    d = {
        "atk": (6 + 2.5 * lvl + flat["atk"]) * (1 + pct["atk_pct"] / 100) * ach * shard,
        "hp": (60 + 12 * lvl + flat["hp"]) * (1 + pct["hp_pct"] / 100) * (1 + 0.01 * s["shards_total"]),
        "def": (lvl + flat["def"]) * (1 + pct["def_pct"] / 100),
        "crit": min(0.75, 0.05 + pct["crit"] / 100), "critdmg": 1.5 + pct["critdmg"] / 100,
        "aspd": min(3.5, 1 + pct["aspd"] / 100), "skill": 1 + pct["skill"] / 100,
        "cdr": min(0.5, pct["cdr"] / 100), "gold": (1 + pct["gold"] / 100) * ach, "xp": 1 + pct["xp"] / 100,
        "drop": 1 + pct["drop"] / 100, "regen": 0.005 + pct["regen"] / 100, "lifesteal": pct["lifesteal"] / 100,
    }
    return d


def combat_power(d, ref_atk):
    red = min(0.8, d["def"] / (d["def"] + 5 * ref_atk))
    return d["atk"] * d["aspd"] * (1 + d["crit"] * (d["critdmg"] - 1)) * math.sqrt(d["hp"] / (1 - red))


def train_cost(base, level):
    return base * TRAIN_GROWTH ** level


def train_bulk(base, level, n):
    return math.ceil(base * TRAIN_GROWTH ** level * (TRAIN_GROWTH ** n - 1) / (TRAIN_GROWTH - 1))


def train_max(base, level, gold):
    first = base * TRAIN_GROWTH ** level
    if gold < first:
        return 0
    n = int(math.log(1 + gold * (TRAIN_GROWTH - 1) / first) / math.log(TRAIN_GROWTH))
    while n > 0 and train_bulk(base, level, n) > gold:
        n -= 1
    while train_bulk(base, level, n + 1) <= gold:
        n += 1
    return n


def perk_cost(perk, level):
    return math.ceil(perk[5] * PERK_GROWTH ** level)


def stat_value(s, key):
    if key == "level":
        return s["level"]
    if key in ("best_all", "rebirths", "shards_total"):
        return s[key]
    return s["st"].get(key, 0)


# ---------- Engine ----------

class Engine:
    """All game rules. The UI calls tick() and the action methods, and reads `events`."""

    def __init__(self, state, rng=None):
        self.s = state
        self.rng = rng or random.Random()
        self.events = []
        self.enemy = None
        self.e_hp = 0.0
        self.cd = {}
        self.buffs = {}
        self.atk_t = self.en_t = 0.0
        self.spawn_t = 0.3
        self.recover = 0.0
        self.smite_cd = 0.0
        self.dirty = True
        self.d = derive(state)
        self.hp = self.d["hp"]
        self._unlock_skills()

    # ----- helpers -----
    def refresh(self):
        self.d = derive(self.s)
        self.dirty = False

    def ev(self, *e):
        self.events.append(e)

    def skill_level(self, sid):
        return self.s["skills"].get(sid, 0)

    def skill_power(self, sk):
        return (1 + 0.15 * (self.skill_level(sk[0]) - 1)) * self.d["skill"]

    def _unlock_skills(self):
        for sk in SKILLS:
            if self.s["level"] >= sk[2] and self.skill_level(sk[0]) == 0:
                self.s["skills"][sk[0]] = 1
                self.ev("unlock", sk[1])

    def ref_atk(self):
        return enemy_for(self.s["stage"], False, False, self.rng)["atk"]

    def power(self, equipped=None):
        return combat_power(derive(self.s, equipped), self.ref_atk())

    # ----- spawning and combat -----
    def spawn(self):
        s = self.s
        boss = s["kills"] >= MOBS_PER_STAGE
        self.enemy = enemy_for(s["stage"], boss, boss and s["stage"] % 10 == 0, self.rng)
        self.e_hp = self.enemy["hp"]
        self.en_t = 0.0
        self.ev("spawn", self.enemy)

    def tick(self, dt):
        s = self.s
        if self.dirty:
            self.refresh()
        d = self.d
        self.smite_cd = max(0.0, self.smite_cd - dt)
        if self.recover > 0:
            self.recover -= dt
            if self.recover <= 0:
                self.hp = d["hp"]
                self.spawn_t = 0.3
            return
        self.hp = min(d["hp"], self.hp + d["hp"] * d["regen"] * dt)
        if self.enemy is None:
            self.spawn_t -= dt
            if self.spawn_t > 0:
                return
            self.spawn()
        for k in list(self.buffs):
            self.buffs[k] -= dt
            if self.buffs[k] <= 0:
                del self.buffs[k]
        for sk in SKILLS:
            if self.skill_level(sk[0]):
                self.cd[sk[0]] = max(0.0, self.cd.get(sk[0], 0.0) - dt * (1 + d["cdr"]))
        self._autocast()
        rage = "rage" in self.buffs
        self.atk_t += dt * d["aspd"] * (1.6 if rage else 1.0)
        while self.atk_t >= 1 and self.enemy:
            self.atk_t -= 1
            dmg = d["atk"] * self.rng.uniform(0.9, 1.1) * (1.4 if rage else 1.0)
            crit = self.rng.random() < d["crit"]
            if crit:
                dmg *= d["critdmg"]
                s["st"]["crits"] += 1
            self.hit(dmg, crit, "hit")
        if self.enemy:
            self.en_t += dt
            interval = 1.1 if self.enemy["boss"] else 1.4
            while self.en_t >= interval and self.enemy:
                self.en_t -= interval
                self._enemy_attack()

    def hit(self, dmg, crit, kind):
        self.e_hp -= dmg
        self.ev("hit", dmg, crit, kind)
        if self.d["lifesteal"] and kind == "hit":
            self.hp = min(self.d["hp"], self.hp + dmg * self.d["lifesteal"])
        if self.e_hp <= 0 and self.enemy:
            self._kill()

    def smite(self):
        if not self.enemy or self.smite_cd > 0:
            return
        self.smite_cd = 0.35
        self.s["st"]["smites"] += 1
        self.hit(self.d["atk"] * 1.5, False, "smite")

    def _enemy_attack(self):
        e, d = self.enemy, self.d
        red = min(0.8, d["def"] / (d["def"] + 5 * e["atk"]))
        dmg = e["atk"] * self.rng.uniform(0.85, 1.15) * (1 - red)
        if "skin" in self.buffs:
            dmg *= 1 - 0.5 * self.skill_power(SKILL_BY_ID["skin"]) / self.d["skill"]
        self.hp -= dmg
        self.ev("hurt", dmg)
        if self.hp <= 0:
            self._die()

    def _die(self):
        s = self.s
        self.hp = 0
        self.enemy = None
        self.buffs.clear()
        s["stage"] = max(1, s["stage"] - 1)
        s["kills"] = 0
        s["auto_adv"] = False
        self.recover = 3.0
        self.ev("death", s["stage"])

    def _autocast(self):
        e, d = self.enemy, self.d
        if not e:
            return
        low_hp = self.hp < 0.55 * d["hp"]
        for sk in SKILLS:
            sid = sk[0]
            if not self.skill_level(sid) or self.cd.get(sid, 0) > 0:
                continue
            kind = sk[4]
            if kind == "heal" and not low_hp:
                continue
            if kind == "shield" and not (e["boss"] or self.hp < 0.8 * d["hp"]):
                continue
            if kind == "warp" and sum(1 for k, v in self.cd.items() if v > 5 and k != "warp") < 2:
                continue
            if kind == "rage" and "rage" in self.buffs:
                continue
            self._cast(sk)
            if not self.enemy:
                return

    def _cast(self, sk):
        sid, name, _lvl, cd, kind, power, _desc = sk
        d, pw = self.d, self.skill_power(sk)
        self.cd[sid] = cd
        self.ev("skill", name)
        rage = 1.4 if "rage" in self.buffs else 1.0
        if kind == "dmg":
            self.hit(d["atk"] * power * pw * rage, False, "skill")
        elif kind == "exec":
            mult = power * 2.7 if self.e_hp < 0.3 * self.enemy["hp"] else power
            self.hit(d["atk"] * mult * pw * rage, False, "skill")
        elif kind == "heal":
            amount = d["hp"] * power * pw
            self.hp = min(d["hp"], self.hp + amount)
            self.ev("heal", amount)
        elif kind == "shield":
            self.buffs["skin"] = 6.0
        elif kind == "rage":
            self.buffs["rage"] = 10.0
        elif kind == "warp":
            for k in self.cd:
                if k != "warp":
                    self.cd[k] = 0.0

    def _kill(self):
        s, e, d = self.s, self.enemy, self.d
        gold, xp = e["gold"] * d["gold"], e["xp"] * d["xp"]
        s["gold"] += gold
        s["st"]["gold"] += gold
        s["st"]["kills"] += 1
        self.ev("kill", e, gold, xp)
        self._add_xp(xp)
        if e["boss"]:
            drops, min_r = (2, 2) if e["zboss"] else (1, 1)
        else:
            drops, min_r = (1 if self.rng.random() < 0.12 * d["drop"] else 0), 0
        for _ in range(drops):
            self._drop_item(min_r)
        self.enemy = None
        self.spawn_t = 0.35
        if e["boss"]:
            s["st"]["bosses"] += 1
            s["kills"] = 0
            if s["auto_adv"]:
                s["stage"] += 1
                s["best"] = max(s["best"], s["stage"])
                s["best_all"] = max(s["best_all"], s["stage"])
                self.ev("stage", s["stage"])
        else:
            s["kills"] += 1

    def _add_xp(self, xp):
        s = self.s
        s["xp"] += xp
        leveled = False
        while s["xp"] >= xp_needed(s["level"]):
            s["xp"] -= xp_needed(s["level"])
            s["level"] += 1
            s["points"] += 3
            s["sp"] += 1
            leveled = True
            self._auto_assign()
        if leveled:
            self.dirty = True
            self.refresh()
            self.hp = self.d["hp"]
            self._unlock_skills()
            self.ev("levelup", s["level"])

    def _auto_assign(self):
        weights = AUTO_WEIGHTS.get(self.s["auto_stats"])
        if not weights:
            return
        while self.s["points"] > 0:
            key = min(weights, key=lambda k: (self.s["stats"][k] + 1) / weights[k])
            self.s["stats"][key] += 1
            self.s["points"] -= 1

    # ----- loot -----
    def _drop_item(self, min_rarity):
        s = self.s
        rarity = roll_rarity(self.rng, self.d["drop"], min_rarity)
        slot = self.rng.choice(SLOTS)[0]
        ilvl = s["stage"] + self.rng.randint(0, 2)
        item = make_item(slot, ilvl, rarity, self.rng, s["uid"])
        s["uid"] += 1
        s["st"]["items"] += 1
        self.ev("loot", item)
        cur = s["equipped"][slot]
        if s["auto_eq"] and (cur is None or self._better(item, slot)):
            self.equip_item(item)
        elif rarity < s["auto_sell"] or len(s["inv"]) >= INV_CAP:
            gold = sell_value(item) * self.d["gold"]
            s["gold"] += gold
            self.ev("sold", item, gold)
        else:
            s["inv"].append(item)

    def _better(self, item, slot):
        eq = dict(self.s["equipped"])
        eq[slot] = item
        return self.power(eq) > self.power() * 1.005

    def equip_item(self, item):
        s = self.s
        slot = item["slot"]
        old = s["equipped"][slot]
        s["inv"] = [i for i in s["inv"] if i["uid"] != item["uid"]]
        s["equipped"][slot] = item
        if old:
            if len(s["inv"]) < INV_CAP and old["rarity"] >= s["auto_sell"]:
                s["inv"].append(old)
            else:
                s["gold"] += sell_value(old) * self.d["gold"]
        self.dirty = True

    def unequip(self, slot):
        s = self.s
        item = s["equipped"][slot]
        if item and len(s["inv"]) < INV_CAP:
            s["equipped"][slot] = None
            s["inv"].append(item)
            self.dirty = True

    def sell(self, uid):
        s = self.s
        item = next((i for i in s["inv"] if i["uid"] == uid), None)
        if item:
            s["inv"].remove(item)
            s["gold"] += sell_value(item) * self.d["gold"]

    def salvage(self, uid):
        s = self.s
        item = next((i for i in s["inv"] if i["uid"] == uid), None)
        if item:
            s["inv"].remove(item)
            s["scrap"] += item["rarity"] + 1 + item["plus"]

    def sell_below(self, rarity):
        for item in [i for i in self.s["inv"] if i["rarity"] < rarity]:
            self.sell(item["uid"])

    def enhance(self, slot):
        item = self.s["equipped"][slot]
        if item and item["plus"] < 20 and self.s["gold"] >= enhance_cost(item):
            self.s["gold"] -= enhance_cost(item)
            item["plus"] += 1
            self.dirty = True

    def reforge(self, slot):
        s = self.s
        item = s["equipped"][slot]
        if item and item["aff"] and s["scrap"] >= reforge_cost(item):
            s["scrap"] -= reforge_cost(item)
            keys = self.rng.sample(list(AFFIX), len(item["aff"]))
            item["aff"] = [[k, roll_affix(k, item["ilvl"], item["rarity"], self.rng)] for k in keys]
            self.dirty = True

    # ----- spending -----
    def spend_stat(self, key, n):
        s = self.s
        n = min(n, s["points"])
        if n > 0:
            s["stats"][key] += n
            s["points"] -= n
            self.dirty = True

    def upgrade_skill(self, sid):
        s = self.s
        if 0 < self.skill_level(sid) < SKILL_MAX and s["sp"] > 0:
            s["sp"] -= 1
            s["skills"][sid] += 1

    def buy_train(self, tid, amount):
        s = self.s
        t = next(x for x in TRAIN if x[0] == tid)
        level = s["train"].get(tid, 0)
        n = train_max(t[5], level, s["gold"]) if amount == "MAX" else amount
        if n > 0 and s["gold"] >= train_bulk(t[5], level, n):
            s["gold"] -= train_bulk(t[5], level, n)
            s["train"][tid] = level + n
            self.dirty = True

    def buy_perk(self, pid):
        s = self.s
        perk = next(p for p in PERKS if p[0] == pid)
        level = s["perks"].get(pid, 0)
        cost = perk_cost(perk, level)
        if level < perk[6] and s["shards"] >= cost:
            s["shards"] -= cost
            s["perks"][pid] = level + 1
            self.dirty = True

    # ----- prestige -----
    def rebirth_gain(self):
        return int(self.s["best"] ** 1.6 / 8)

    def can_rebirth(self):
        return self.s["best"] >= REBIRTH_MIN_STAGE

    def rebirth(self, cls):
        s = self.s
        if not self.can_rebirth():
            return
        gain = self.rebirth_gain()
        keep = {k: s[k] for k in ("shards", "shards_total", "rebirths", "best_all", "perks", "ach", "st",
                                  "auto_eq", "auto_sell", "auto_stats", "buy_mode", "uid")}
        fresh = new_state()
        fresh.update(keep)
        fresh["cls"] = cls
        fresh["shards"] += gain
        fresh["shards_total"] += gain
        fresh["rebirths"] += 1
        start = max(1, int(s["best_all"] * 0.08 * s["perks"].get("p_start", 0)))
        fresh["stage"] = fresh["best"] = start
        fresh["gold"] = 200.0 * 3 ** s["perks"].get("p_cash", 0) if s["perks"].get("p_cash") else 0.0
        s.clear()
        s.update(fresh)
        self.enemy = None
        self.buffs.clear()
        self.cd.clear()
        self.recover = 0.0
        self.spawn_t = 0.3
        self.refresh()
        self.hp = self.d["hp"]
        self._unlock_skills()
        self.ev("rebirth", gain)

    def reset_all(self):
        self.s.clear()
        self.s.update(new_state())
        self.enemy = None
        self.buffs.clear()
        self.cd.clear()
        self.recover = 0.0
        self.refresh()
        self.hp = self.d["hp"]
        self._unlock_skills()

    # ----- trophies and offline -----
    def check_achievements(self):
        s = self.s
        for aid, name, _desc, stat, threshold in ACHIEVEMENTS:
            if aid not in s["ach"] and stat_value(s, stat) >= threshold:
                s["ach"].append(aid)
                self.dirty = True
                self.ev("ach", name)

    def dps_estimate(self):
        d = self.d
        return d["atk"] * d["aspd"] * (1 + d["crit"] * (d["critdmg"] - 1)) * 1.15

    def offline(self, seconds):
        """Returns (gold, xp, kills) earned while away, after applying them."""
        s = self.s
        if not OFFLINE_ENABLED or s["cls"] is None or seconds < 30:
            return 0.0, 0.0, 0
        seconds = min(seconds, OFFLINE_CAP_SECONDS)
        self.refresh()
        d = self.d
        e = enemy_for(s["stage"], False, False, self.rng)
        ttk = e["hp"] / max(self.dps_estimate(), 1e-9) + 0.6
        red = min(0.8, d["def"] / (d["def"] + 5 * e["atk"]))
        taken_per_sec = e["atk"] * (1 - red) / 1.4
        if d["hp"] < taken_per_sec * ttk * 2.5:
            return 0.0, 0.0, 0                          # the hero couldn't have survived this stage unattended
        rate = OFFLINE_RATE * (1 + 0.1 * s["perks"].get("p_off", 0))
        kills = int(seconds / ttk * rate)
        gold, xp = kills * e["gold"] * d["gold"], kills * e["xp"] * d["xp"]
        s["gold"] += gold
        s["st"]["gold"] += gold
        s["st"]["kills"] += kills
        self._add_xp(xp)
        return gold, xp, kills


# ---------- Save / load ----------

def load_state():
    state = new_state()
    if SAVE_PATH.exists():
        try:
            data = json.loads(SAVE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        for k, v in data.items():
            if k in state:
                state[k] = v
        for k, v in new_state()["stats"].items():
            state["stats"].setdefault(k, v)
        for k, v in new_state()["st"].items():
            state["st"].setdefault(k, v)
        for slot in SLOT_INFO:
            state["equipped"].setdefault(slot, None)
    return state


def save_state(state):
    state["last_seen"] = time.time()
    SAVE_PATH.write_text(json.dumps(state), encoding="utf-8")


# ---------- UI ----------

BTN = """
QPushButton { background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d; border-radius: 8px; padding: 6px; text-align: left; }
QPushButton:hover { background-color: #21262d; border-color: #00e5ff; }
QPushButton:disabled { color: #4d5560; border-color: #21262d; }
"""
BTN_C = BTN.replace("text-align: left;", "text-align: center;")
TAB = """
QPushButton { background-color: #161b22; color: #8b949e; border: 1px solid #30363d; border-radius: 6px; padding: 5px 2px; text-align: center; }
QPushButton:hover { border-color: #00e5ff; }
QPushButton:checked { background-color: #00e5ff; color: #0d1117; font-weight: bold; }
"""
GOLD_BTN = BTN_C.replace("#c9d1d9", "#f2cc60").replace("#00e5ff", "#f2cc60")
RED_BTN = BTN_C.replace("#c9d1d9", "#f85149").replace("#00e5ff", "#f85149")
PURPLE_BTN = BTN_C.replace("#c9d1d9", "#a371f7").replace("#00e5ff", "#a371f7")
BAR = "QProgressBar {{ background-color: #161b22; border: 1px solid #30363d; border-radius: 4px; }} QProgressBar::chunk {{ background-color: {c}; border-radius: 3px; }}"
LIST = "QListWidget { background-color: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 8px; } QListWidget::item { padding: 3px 5px; } QListWidget::item:selected { background-color: #21262d; }"
COMBO = "QComboBox { background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 3px 6px; }"
TEXT_BOX = "QTextEdit { background-color: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 8px; }"


def rcolor(r):
    return RARITIES[r][1]


def item_html(it, compare=None):
    name = f"{it['name']}" + (f" +{it['plus']}" if it["plus"] else "")
    lines = [f'<b><span style="color:{rcolor(it["rarity"])}">[{RARITIES[it["rarity"]][0]}] {name}</span></b>',
             f"{SLOT_INFO[it['slot']][1]}  |  Item level {it['ilvl']}",
             f"<span style='color:#c9d1d9'>+{fmt(item_main(it))} {MAIN_LABEL[item_main_stat(it)]}</span>"]
    for k, v in it["aff"]:
        suffix = "%/s" if k == "regen" else "%"
        lines.append(f"<span style='color:#8bb8ff'>+{v:g}{suffix} {AFFIX[k][0]}</span>")
    if compare is not None:
        color = "#3fb950" if compare > 0 else ("#f85149" if compare < 0 else "#8b949e")
        lines.append(f"<span style='color:{color}'>{compare * 100:+.1f}% power if equipped</span>")
    return "<br>".join(lines)


class BattleView(QWidget):
    """Draws the arena: hero, enemy, health bars, floating numbers and hit effects."""

    def __init__(self, eng):
        super().__init__()
        self.eng = eng
        self.setFixedHeight(220)
        self.texts = []
        self.lunge = self.flash = self.shake = 0.0
        self.pulse = 0.0

    def add_text(self, text, side, color, size=13):
        self.texts.append({"t": text, "side": side, "x": random.randint(-26, 26), "age": 0.0, "color": color, "size": size})
        del self.texts[:-40]

    def advance(self, dt):
        self.pulse += dt
        self.lunge = max(0.0, self.lunge - dt * 5)
        self.flash = max(0.0, self.flash - dt * 6)
        self.shake = max(0.0, self.shake - dt * 8)
        for t in self.texts:
            t["age"] += dt
        self.texts = [t for t in self.texts if t["age"] < 0.9]
        self.update()

    def paintEvent(self, event):
        eng, s = self.eng, self.eng.s
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        zone, _ = zone_of(s["stage"])
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), 12, 12)
        p.setClipPath(clip)
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor(zone[1][0]))
        grad.setColorAt(1, QColor(zone[1][1]))
        p.fillRect(0, 0, w, h, grad)
        p.fillRect(0, int(h * 0.74), w, h, QColor(0, 0, 0, 90))
        if self.shake:
            p.translate(random.uniform(-1, 1) * self.shake * 4, random.uniform(-1, 1) * self.shake * 4)
        cls = CLASSES.get(s["cls"])
        hero_x, enemy_x, base_y = w * 0.22 + self.lunge * 26, w * 0.78, h * 0.60
        emoji = QFont("Segoe UI Emoji", 38)
        p.setFont(emoji)
        p.setPen(QColor("white"))
        p.drawText(QRectF(hero_x - 45, base_y - 45, 90, 90), Qt.AlignmentFlag.AlignCenter, cls["icon"] if cls else "?")
        e = eng.enemy
        if e:
            size = 54 if e["boss"] else 40
            if e["boss"]:
                glow = int(60 + 40 * math.sin(self.pulse * 4))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 60, 60, glow))
                p.drawEllipse(QRectF(enemy_x - 55, base_y - 55, 110, 110))
            p.setFont(QFont("Segoe UI Emoji", size))
            p.setPen(QColor("white"))
            p.drawText(QRectF(enemy_x - 60, base_y - 60, 120, 120), Qt.AlignmentFlag.AlignCenter, e["emoji"])
            if self.flash:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, int(150 * self.flash)))
                p.drawEllipse(QRectF(enemy_x - 36, base_y - 36, 72, 72))
        self._bar(p, hero_x - 55, h * 0.10, 110, eng.hp / max(1, eng.d["hp"]), "#3fb950", f"{fmt(max(0, eng.hp))}/{fmt(eng.d['hp'])}")
        if e:
            self._bar(p, enemy_x - 55, h * 0.10, 110, max(0, eng.e_hp) / e["hp"], "#f85149", f"{fmt(max(0, eng.e_hp))}")
            p.setPen(QColor("#ffcc66" if e["boss"] else "#c9d1d9"))
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.drawText(QRectF(enemy_x - 80, h * 0.10 + 20, 160, 16), Qt.AlignmentFlag.AlignCenter, e["name"])
        if eng.recover > 0:
            p.setPen(QColor("#f85149"))
            p.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            p.drawText(QRectF(0, h * 0.40, w, 30), Qt.AlignmentFlag.AlignCenter, f"Defeated... recovering ({eng.recover:.0f}s)")
        for t in self.texts:
            side_x = hero_x if t["side"] == "hero" else enemy_x
            life = t["age"] / 0.9
            c = QColor(t["color"])
            c.setAlpha(int(255 * (1 - life ** 2)))
            p.setPen(c)
            p.setFont(QFont("Segoe UI", t["size"], QFont.Weight.Bold))
            p.drawText(QRectF(side_x - 70 + t["x"], base_y - 55 - 60 * life, 140, 24), Qt.AlignmentFlag.AlignCenter, t["t"])

    @staticmethod
    def _bar(p, x, y, width, frac, color, label):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRoundedRect(QRectF(x, y, width, 14), 5, 5)
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(x, y, max(0.0, min(1.0, frac)) * width, 14), 5, 5)
        p.setPen(QColor("white"))
        p.setFont(QFont("Segoe UI", 7))
        p.drawText(QRectF(x, y, width, 14), Qt.AlignmentFlag.AlignCenter, label)


class IdleLegends(QWidget):
    PANEL_SIZE = (540, 760)

    def __init__(self):
        super().__init__()
        self.eng = Engine(load_state())
        s = self.eng.s
        self.offline_report = ""
        away = time.time() - s["last_seen"]
        gold, xp, kills = self.eng.offline(away)
        if kills:
            self.offline_report = f"Away {away / 60:.0f} min: {kills:,} kills, +{fmt(gold)} gold, +{fmt(xp)} XP"
        self.eng._unlock_skills()
        self.eng.refresh()
        self.eng.hp = self.eng.d["hp"]
        self.eng.events.clear()
        save_state(s)

        self.banner_text, self.banner_until = self.offline_report, time.monotonic() + 6
        self.armed = None
        self.sel = None                      # ("inv", uid) or ("eq", slot)
        self.inv_sig = None
        self._ticks = 0
        self._last = time.monotonic()
        self._last_dt = 0.1

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(5)
        tabs = QHBoxLayout()
        tabs.setSpacing(3)
        self.tab_btns = []
        for i, label in enumerate(["Battle", "Hero", "Gear", "Train", "Rebirth", "More"]):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(TAB)
            btn.clicked.connect(lambda checked, idx=i: self._show(idx))
            tabs.addWidget(btn)
            self.tab_btns.append(btn)
        outer.addLayout(tabs)
        self.banner = QLabel()
        self.banner.setFixedHeight(18)
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setStyleSheet("color: #f2cc60; font-weight: bold;")
        outer.addWidget(self.banner)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        for builder in (self._build_battle, self._build_hero, self._build_gear, self._build_train,
                        self._build_rebirth, self._build_more, self._build_class_pick):
            self.stack.addWidget(builder())

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(TICK_MS)
        self.anim = QTimer(self)
        self.anim.timeout.connect(self._animate)
        self.anim.start(33)
        self.destroyed.connect(lambda _=None, st=s: save_state(st))
        self._show(0 if s["cls"] else 6)
        self._refresh_all()

    # ---------- page builders ----------

    def _scroll(self, inner):
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sc.setStyleSheet("background: transparent; border: none;")
        sc.setWidget(inner)
        return sc

    def _label(self, color="#8b949e", wrap=True, bold=False):
        lbl = QLabel()
        lbl.setWordWrap(wrap)
        lbl.setStyleSheet(f"color: {color};" + (" font-weight: bold;" if bold else ""))
        return lbl

    def _build_battle(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        self.zone_label = self._label("#c9d1d9", bold=True)
        self.zone_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.zone_label)
        self.view = BattleView(self.eng)
        lay.addWidget(self.view)
        self.pips_label = self._label("#8b949e")
        self.pips_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.pips_label)
        self.level_label = self._label("#00e5ff", bold=True)
        self.level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.level_label)
        self.xp_bar = QProgressBar()
        self.xp_bar.setRange(0, 1000)
        self.xp_bar.setTextVisible(False)
        self.xp_bar.setFixedHeight(8)
        self.xp_bar.setStyleSheet(BAR.format(c="#00e5ff"))
        lay.addWidget(self.xp_bar)
        self.money_label = self._label("#f2cc60", bold=True)
        self.money_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.money_label)

        grid = QGridLayout()
        grid.setSpacing(4)
        self.skill_cells = {}
        for i, sk in enumerate(SKILLS):
            cell = QWidget()
            v = QVBoxLayout(cell)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(1)
            name = QLabel(sk[1])
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setTextVisible(False)
            bar.setFixedHeight(6)
            bar.setStyleSheet(BAR.format(c="#a371f7"))
            v.addWidget(name)
            v.addWidget(bar)
            grid.addWidget(cell, i // 4, i % 4)
            self.skill_cells[sk[0]] = (name, bar)
        lay.addLayout(grid)

        row = QHBoxLayout()
        self.adv_btn = QPushButton()
        self.adv_btn.setStyleSheet(BTN_C)
        self.adv_btn.clicked.connect(self._toggle_adv)
        row.addWidget(self.adv_btn)
        self.smite_btn = QPushButton("SMITE (tap!)")
        self.smite_btn.setStyleSheet(GOLD_BTN)
        self.smite_btn.setFixedHeight(34)
        self.smite_btn.clicked.connect(self._smite)
        row.addWidget(self.smite_btn, 1)
        lay.addLayout(row)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(TEXT_BOX)
        self.log.document().setMaximumBlockCount(80)
        lay.addWidget(self.log, 1)
        return page

    def _build_hero(self):
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setSpacing(6)
        self.hero_header = self._label("#00e5ff", bold=True)
        lay.addWidget(self.hero_header)
        row = QHBoxLayout()
        row.addWidget(self._label("#8b949e", wrap=False))
        row.itemAt(0).widget().setText("Auto-assign points:")
        self.auto_box = QComboBox()
        self.auto_box.setStyleSheet(COMBO)
        self.auto_box.addItems(list(AUTO_WEIGHTS))
        self.auto_box.setCurrentText(self.eng.s["auto_stats"])
        self.auto_box.currentTextChanged.connect(lambda t: self.eng.s.__setitem__("auto_stats", t))
        row.addWidget(self.auto_box)
        row.addStretch()
        lay.addLayout(row)
        self.stat_rows = {}
        for key in STAT_KEYS:
            r = QHBoxLayout()
            lbl = self._label("#c9d1d9", wrap=False)
            lbl.setMinimumWidth(250)
            r.addWidget(lbl, 1)
            for n in (1, 5, 25):
                b = QPushButton(f"+{n}")
                b.setFixedWidth(46)
                b.setStyleSheet(BTN_C)
                b.clicked.connect(lambda checked, k=key, amt=n: self._spend(k, amt))
                r.addWidget(b)
            lay.addLayout(r)
            self.stat_rows[key] = lbl
        self.derived_label = self._label("#8b949e")
        lay.addWidget(self.derived_label)
        self.skill_points_label = self._label("#a371f7", bold=True)
        lay.addWidget(self.skill_points_label)
        self.skill_rows = {}
        for sk in SKILLS:
            r = QHBoxLayout()
            lbl = self._label("#c9d1d9")
            r.addWidget(lbl, 1)
            b = QPushButton("Upgrade")
            b.setFixedWidth(74)
            b.setStyleSheet(PURPLE_BTN)
            b.clicked.connect(lambda checked, sid=sk[0]: self._upgrade_skill(sid))
            r.addWidget(b)
            lay.addLayout(r)
            self.skill_rows[sk[0]] = (lbl, b)
        lay.addStretch()
        return self._scroll(inner)

    def _build_gear(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        grid = QGridLayout()
        grid.setSpacing(4)
        self.slot_btns = {}
        for i, slot in enumerate(SLOTS):
            b = QPushButton()
            b.setStyleSheet(BTN)
            b.setMinimumHeight(40)
            b.clicked.connect(lambda checked, sl=slot[0]: self._select(("eq", sl)))
            grid.addWidget(b, i // 2, i % 2)
            self.slot_btns[slot[0]] = b
        lay.addLayout(grid)
        opts = QHBoxLayout()
        self.eq_check = QCheckBox("Auto-equip upgrades")
        self.eq_check.setStyleSheet("color: #c9d1d9;")
        self.eq_check.setChecked(self.eng.s["auto_eq"])
        self.eq_check.toggled.connect(lambda c: self.eng.s.__setitem__("auto_eq", c))
        opts.addWidget(self.eq_check)
        opts.addWidget(self._label("#8b949e", wrap=False))
        opts.itemAt(1).widget().setText("Auto-sell below:")
        self.sell_box = QComboBox()
        self.sell_box.setStyleSheet(COMBO)
        self.sell_box.addItems([r[0] for r in RARITIES])
        self.sell_box.setCurrentIndex(self.eng.s["auto_sell"])
        self.sell_box.currentIndexChanged.connect(lambda i: self.eng.s.__setitem__("auto_sell", i))
        opts.addWidget(self.sell_box)
        lay.addLayout(opts)
        self.inv_list = QListWidget()
        self.inv_list.setStyleSheet(LIST)
        self.inv_list.itemClicked.connect(lambda item: self._select(("inv", item.data(Qt.ItemDataRole.UserRole))))
        lay.addWidget(self.inv_list, 1)
        self.detail = QLabel()
        self.detail.setTextFormat(Qt.TextFormat.RichText)
        self.detail.setWordWrap(True)
        self.detail.setMinimumHeight(110)
        self.detail.setStyleSheet("color: #c9d1d9; background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 6px;")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.detail)
        r1, r2 = QHBoxLayout(), QHBoxLayout()
        self.act_btns = {}
        for row, key, label, handler in (
            (r1, "equip", "Equip", self._equip_sel), (r1, "sell", "Sell", self._sell_sel), (r1, "salvage", "Salvage", self._salvage_sel),
            (r2, "enhance", "Enhance", self._enhance_sel), (r2, "reforge", "Reforge", self._reforge_sel), (r2, "unequip", "Unequip", self._unequip_sel),
        ):
            b = QPushButton(label)
            b.setStyleSheet(BTN_C)
            b.clicked.connect(lambda checked, h=handler: h())
            row.addWidget(b)
            self.act_btns[key] = b
        lay.addLayout(r1)
        lay.addLayout(r2)
        self.sellbelow_btn = QPushButton("Sell everything in the backpack below the auto-sell rarity")
        self.sellbelow_btn.setStyleSheet(BTN_C)
        self.sellbelow_btn.clicked.connect(lambda: (self.eng.sell_below(self.eng.s["auto_sell"]), self._refresh_all()))
        lay.addWidget(self.sellbelow_btn)
        return page

    def _build_train(self):
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setSpacing(5)
        lay.addWidget(self._label("#8b949e"))
        lay.itemAt(0).widget().setText("Spend gold on training. Training resets when you Rebirth.")
        row = QHBoxLayout()
        row.addWidget(self._label("#8b949e", wrap=False))
        row.itemAt(0).widget().setText("Buy:")
        self.buy_btns = []
        for i, amount in enumerate([1, 10, 25, 100, "MAX"]):
            b = QPushButton("MAX" if amount == "MAX" else f"{amount}x")
            b.setCheckable(True)
            b.setChecked(i == self.eng.s["buy_mode"])
            b.setStyleSheet(TAB)
            b.clicked.connect(lambda checked, idx=i: self._set_buy(idx))
            row.addWidget(b)
            self.buy_btns.append(b)
        row.addStretch()
        lay.addLayout(row)
        self.train_btns = {}
        for t in TRAIN:
            b = QPushButton()
            b.setStyleSheet(BTN)
            b.clicked.connect(lambda checked, tid=t[0]: self._buy_train(tid))
            lay.addWidget(b)
            self.train_btns[t[0]] = b
        lay.addStretch()
        return self._scroll(inner)

    def _build_rebirth(self):
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setSpacing(6)
        self.rebirth_info = self._label("#c9d1d9")
        lay.addWidget(self.rebirth_info)
        row = QHBoxLayout()
        row.addWidget(self._label("#8b949e", wrap=False))
        row.itemAt(0).widget().setText("Next class:")
        self.class_box = QComboBox()
        self.class_box.setStyleSheet(COMBO)
        for key, c in CLASSES.items():
            self.class_box.addItem(f"{c['name']}", key)
        row.addWidget(self.class_box)
        row.addStretch()
        lay.addLayout(row)
        self.rebirth_btn = QPushButton()
        self.rebirth_btn.setStyleSheet(PURPLE_BTN)
        self.rebirth_btn.setMinimumHeight(40)
        self.rebirth_btn.clicked.connect(self._rebirth)
        lay.addWidget(self.rebirth_btn)
        self.shards_label = self._label("#a371f7", bold=True)
        lay.addWidget(self.shards_label)
        self.perk_btns = {}
        for p in PERKS:
            b = QPushButton()
            b.setStyleSheet(BTN.replace("#00e5ff", "#a371f7"))
            b.clicked.connect(lambda checked, pid=p[0]: self._buy_perk(pid))
            lay.addWidget(b)
            self.perk_btns[p[0]] = b
        lay.addStretch()
        return self._scroll(inner)

    def _build_more(self):
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setSpacing(4)
        self.stats_label = self._label("#c9d1d9")
        lay.addWidget(self.stats_label)
        self.trophy_header = self._label("#f2cc60", bold=True)
        lay.addWidget(self.trophy_header)
        self.ach_labels = {}
        for a in ACHIEVEMENTS:
            lbl = self._label("#4d5560")
            lay.addWidget(lbl)
            self.ach_labels[a[0]] = lbl
        self.reset_btn = QPushButton()
        self.reset_btn.setStyleSheet(RED_BTN)
        self.reset_btn.clicked.connect(self._reset)
        lay.addWidget(self.reset_btn)
        lay.addWidget(self._label("#8b949e"))
        lay.itemAt(lay.count() - 1).widget().setText(f"Saved automatically to {SAVE_PATH}. Reset wipes everything, including shards and trophies.")
        lay.addStretch()
        return self._scroll(inner)

    def _build_class_pick(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        title = self._label("#00e5ff", bold=True)
        title.setText("Choose your class")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        for key, c in CLASSES.items():
            b = QPushButton(f"{c['icon']}  {c['name']}\n{c['desc']}")
            b.setStyleSheet(BTN)
            b.setMinimumHeight(64)
            b.clicked.connect(lambda checked, k=key: self._choose_class(k))
            lay.addWidget(b)
        lay.addStretch()
        return page

    # ---------- actions ----------

    def _show(self, idx):
        if idx != 6 and self.eng.s["cls"] is None:
            idx = 6
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.tab_btns):
            b.setChecked(i == idx)
        self._refresh_all()

    def _choose_class(self, key):
        self.eng.s["cls"] = key
        self.eng.dirty = True
        self.eng.refresh()
        self.eng.hp = self.eng.d["hp"]
        self._show(0)

    def _toggle_adv(self):
        s = self.eng.s
        s["auto_adv"] = not s["auto_adv"]
        self._refresh_all()

    def _smite(self):
        self.eng.smite()
        self._handle_events()

    def _spend(self, key, n):
        self.eng.spend_stat(key, n)
        self._refresh_all()

    def _upgrade_skill(self, sid):
        self.eng.upgrade_skill(sid)
        self._refresh_all()

    def _select(self, sel):
        self.sel = sel
        self._refresh_all()

    def _sel_item(self):
        if not self.sel:
            return None
        kind, ref = self.sel
        if kind == "eq":
            return self.eng.s["equipped"].get(ref)
        return next((i for i in self.eng.s["inv"] if i["uid"] == ref), None)

    def _equip_sel(self):
        item = self._sel_item()
        if item and self.sel[0] == "inv":
            self.eng.equip_item(item)
            self.sel = ("eq", item["slot"])
            self.eng.refresh()
            self._refresh_all()

    def _sell_sel(self):
        if self.sel and self.sel[0] == "inv":
            self.eng.sell(self.sel[1])
            self.sel = None
            self._refresh_all()

    def _salvage_sel(self):
        if self.sel and self.sel[0] == "inv":
            self.eng.salvage(self.sel[1])
            self.sel = None
            self._refresh_all()

    def _enhance_sel(self):
        if self.sel and self.sel[0] == "eq":
            self.eng.enhance(self.sel[1])
            self._refresh_all()

    def _reforge_sel(self):
        if self.sel and self.sel[0] == "eq":
            self.eng.reforge(self.sel[1])
            self._refresh_all()

    def _unequip_sel(self):
        if self.sel and self.sel[0] == "eq":
            self.eng.unequip(self.sel[1])
            self.sel = None
            self._refresh_all()

    def _set_buy(self, idx):
        self.eng.s["buy_mode"] = idx
        for i, b in enumerate(self.buy_btns):
            b.setChecked(i == idx)
        self._refresh_all()

    def _buy_train(self, tid):
        self.eng.buy_train(tid, [1, 10, 25, 100, "MAX"][self.eng.s["buy_mode"]])
        self._refresh_all()

    def _buy_perk(self, pid):
        self.eng.buy_perk(pid)
        self._refresh_all()

    def _confirm(self, key):
        """First click arms a dangerous button, second click (within 4s) does it."""
        if self.armed == key:
            self.armed = None
            return True
        self.armed = key
        QTimer.singleShot(4000, lambda: setattr(self, "armed", None) if self.armed == key else None)
        self._refresh_all()
        return False

    def _rebirth(self):
        if self.eng.can_rebirth() and self._confirm("rebirth"):
            self.eng.rebirth(self.class_box.currentData())
            self._handle_events()
            self.sel = None
            self._show(0)

    def _reset(self):
        if self._confirm("reset"):
            self.eng.reset_all()
            self.sel = None
            self._show(6)

    # ---------- tick and events ----------

    def on_tick(self):
        now = time.monotonic()
        dt = min(0.5, now - self._last)
        self._last = now
        self._last_dt = dt
        if self.eng.s["cls"] is None:
            return
        self.eng.tick(dt)
        self._ticks += 1
        if self._ticks % 10 == 0:
            self.eng.check_achievements()
        if self._ticks % 100 == 0:
            save_state(self.eng.s)
        self._handle_events()
        self._refresh_all()

    def _animate(self):
        self.view.advance(0.033)

    def _banner(self, text, seconds=3.5):
        self.banner_text, self.banner_until = text, time.monotonic() + seconds

    def _log(self, html):
        self.log.append(html)

    def _handle_events(self):
        v = self.view
        for ev in self.eng.events:
            kind = ev[0]
            if kind == "hit":
                _k, dmg, crit, source = ev
                if source == "skill":
                    v.add_text(fmt(dmg), "enemy", "#c792ff", 16)
                elif source == "smite":
                    v.add_text(fmt(dmg), "enemy", "#f2cc60", 14)
                else:
                    v.add_text(fmt(dmg), "enemy", "#ffd866" if crit else "#ffffff", 17 if crit else 12)
                v.flash, v.lunge = 1.0, 1.0
                if crit:
                    v.shake = max(v.shake, 0.5)
            elif kind == "hurt":
                v.add_text(f"-{fmt(ev[1])}", "hero", "#ff6b6b", 11)
            elif kind == "heal":
                v.add_text(f"+{fmt(ev[1])}", "hero", "#56d364", 14)
            elif kind == "skill":
                v.add_text(ev[1], "hero", "#79c0ff", 11)
                self._log(f'<span style="color:#79c0ff">Cast {ev[1]}</span>')
            elif kind == "kill":
                e, gold = ev[1], ev[2]
                v.add_text(f"+{fmt(gold)}g", "enemy", "#f2cc60", 10)
                if e["boss"]:
                    v.shake = 1.0
                    self._log(f'<span style="color:#ffcc66">Defeated {e["name"]}! +{fmt(gold)} gold</span>')
            elif kind == "loot":
                it = ev[1]
                if it["rarity"] >= 2:
                    self._log(f'<span style="color:{rcolor(it["rarity"])}">Found [{RARITIES[it["rarity"]][0]}] {it["name"]}</span>')
                if it["rarity"] >= 4:
                    self._banner(f"LEGENDARY DROP: {it['name']}!" if it["rarity"] == 4 else f"MYTHIC DROP: {it['name']}!!", 5)
            elif kind == "levelup":
                self._log(f'<span style="color:#00e5ff">Level up! You are now level {ev[1]}</span>')
                self._banner(f"LEVEL UP! {ev[1]}")
            elif kind == "unlock":
                self._log(f'<span style="color:#a371f7">New skill unlocked: {ev[1]}</span>')
                self._banner(f"NEW SKILL: {ev[1]}")
            elif kind == "stage":
                self._log(f'<span style="color:#8b949e">Advanced to stage {ev[1]}</span>')
            elif kind == "death":
                self._log(f'<span style="color:#f85149">You were defeated. Retreated to stage {ev[1]}. Auto-advance is off.</span>')
                self._banner("DEFEATED - farm a bit, then press Advance", 5)
            elif kind == "ach":
                self._log(f'<span style="color:#f2cc60">Trophy unlocked: {ev[1]}</span>')
                self._banner(f"TROPHY: {ev[1]}")
            elif kind == "rebirth":
                self._banner(f"REBORN! +{ev[1]} Soul Shards", 5)
        self.eng.events.clear()

    # ---------- refresh ----------

    def _refresh_all(self):
        s, eng = self.eng.s, self.eng
        if s["cls"] is None:
            return
        if eng.dirty:
            eng.refresh()
        now = time.monotonic()
        self.banner.setText(self.banner_text if self.banner_until > now else "")
        page = self.stack.currentIndex()
        {0: self._refresh_battle, 1: self._refresh_hero, 2: self._refresh_gear, 3: self._refresh_train,
         4: self._refresh_rebirth, 5: self._refresh_more}.get(page, lambda: None)()

    def _refresh_battle(self):
        s, eng, d = self.eng.s, self.eng, self.eng.d
        zone, cycle = zone_of(s["stage"])
        title = zone[0] + (f" (Hard {cycle + 1})" if cycle else "")
        zstage = (s["stage"] - 1) % 10 + 1
        self.zone_label.setText(f"{title}  -  Stage {s['stage']}  ({zstage}/10)")
        done = min(s["kills"], MOBS_PER_STAGE)
        boss = "BOSS" if (eng.enemy and eng.enemy["boss"]) else "boss"
        self.pips_label.setText("  ".join(["\u25cf"] * done + ["\u25cb"] * (MOBS_PER_STAGE - done)) + f"   {boss}")
        need = xp_needed(s["level"])
        cls = CLASSES[s["cls"]]
        self.level_label.setText(f"{cls['icon']} {cls['name']}  Lv {s['level']}   ({fmt(s['xp'])} / {fmt(need)} XP)")
        self.xp_bar.setValue(int(1000 * s["xp"] / need))
        self.money_label.setText(f"Gold {fmt(s['gold'])}    Scrap {s['scrap']}    Shards {s['shards']}    DPS ~{fmt(eng.dps_estimate())}")
        for sk in SKILLS:
            name, bar = self.skill_cells[sk[0]]
            lvl = eng.skill_level(sk[0])
            if not lvl:
                name.setText(f"Lv {sk[2]}")
                name.setStyleSheet("color: #4d5560; font-size: 9px;")
                bar.setValue(0)
            else:
                ready = eng.cd.get(sk[0], 0) <= 0
                name.setText(sk[1])
                name.setStyleSheet(f"color: {'#c9d1d9' if ready else '#8b949e'}; font-size: 9px;")
                bar.setValue(int(1000 * (1 - eng.cd.get(sk[0], 0) / sk[3])))
        self.adv_btn.setText("Auto-advance: ON" if s["auto_adv"] else "Advance: OFF (click to push on)")
        self.adv_btn.setStyleSheet(BTN_C if s["auto_adv"] else RED_BTN)

    def _refresh_hero(self):
        s, eng, d = self.eng.s, self.eng, self.eng.d
        cls = CLASSES[s["cls"]]
        self.hero_header.setText(f"{cls['icon']} {cls['name']}  Level {s['level']}    Stat points: {s['points']}")
        for key in STAT_KEYS:
            n, desc = STAT_INFO[key]
            self.stat_rows[key].setText(f"{n}: {s['stats'][key]}\n{desc}")
        self.derived_label.setText(
            f"Attack {fmt(d['atk'])}   Health {fmt(d['hp'])}   Defense {fmt(d['def'])}\n"
            f"Crit {d['crit'] * 100:.1f}% (x{d['critdmg']:.2f})   Attack speed {d['aspd']:.2f}/s   Regen {d['regen'] * 100:.2f}%/s\n"
            f"Skill power x{d['skill']:.2f}   Cooldown speed +{d['cdr'] * 100:.0f}%   Lifesteal {d['lifesteal'] * 100:.1f}%\n"
            f"Gold x{d['gold']:.2f}   XP x{d['xp']:.2f}   Drops x{d['drop']:.2f}\n"
            f"Soul Shard bonus x{1 + 0.02 * s['shards_total']:.2f} damage   Trophy bonus +{len(s['ach'])}%"
        )
        self.skill_points_label.setText(f"Skills (auto-cast)   Skill points: {s['sp']}")
        for sk in SKILLS:
            lbl, btn = self.skill_rows[sk[0]]
            lvl = eng.skill_level(sk[0])
            if not lvl:
                lbl.setText(f"{sk[1]}  -  unlocks at level {sk[2]}")
                lbl.setStyleSheet("color: #4d5560;")
                btn.setEnabled(False)
            else:
                p = 100 * sk[5] * eng.skill_power(sk) if sk[4] in ("dmg", "exec", "heal", "shield") else 0
                desc = sk[6].format(p=f"{p:.0f}")
                lbl.setText(f"{sk[1]}  Lv {lvl}/{SKILL_MAX}  ({sk[3]}s)\n{desc}")
                lbl.setStyleSheet("color: #c9d1d9;")
                btn.setEnabled(s["sp"] > 0 and lvl < SKILL_MAX)

    def _refresh_gear(self):
        s, eng = self.eng.s, self.eng
        for slot in SLOTS:
            it = s["equipped"][slot[0]]
            b = self.slot_btns[slot[0]]
            if it:
                b.setText(f"{slot[1]}: {it['name']}" + (f" +{it['plus']}" if it["plus"] else ""))
                b.setStyleSheet(BTN.replace("#c9d1d9", rcolor(it["rarity"])))
            else:
                b.setText(f"{slot[1]}: (empty)")
                b.setStyleSheet(BTN.replace("#c9d1d9", "#4d5560"))
        sig = tuple(i["uid"] for i in s["inv"]) + (self.sel,)
        if sig != self.inv_sig:
            self.inv_sig = sig
            self.inv_list.clear()
            for it in sorted(s["inv"], key=lambda i: (-i["rarity"], -i["ilvl"])):
                row = QListWidgetItem(f"[{RARITIES[it['rarity']][0]}] {it['name']}  (ilvl {it['ilvl']}, {SLOT_INFO[it['slot']][1]})")
                row.setForeground(QColor(rcolor(it["rarity"])))
                row.setData(Qt.ItemDataRole.UserRole, it["uid"])
                self.inv_list.addItem(row)
        item = self._sel_item()
        for key, b in self.act_btns.items():
            b.setEnabled(False)
        if item is None:
            self.detail.setText(f"Backpack {len(s['inv'])}/{INV_CAP}    Scrap {s['scrap']}    Gold {fmt(s['gold'])}<br>Select an item to see details.")
            return
        if self.sel[0] == "inv":
            eq = dict(s["equipped"])
            eq[item["slot"]] = item
            base = eng.power()
            delta = (eng.power(eq) / base - 1) if base else 0
            cur = s["equipped"][item["slot"]]
            extra = f"<br><span style='color:#8b949e'>Replaces: {cur['name']}</span>" if cur else ""
            self.detail.setText(item_html(item, delta) + extra + f"<br>Sells for {fmt(sell_value(item) * eng.d['gold'])} gold")
            for key in ("equip", "sell", "salvage"):
                self.act_btns[key].setEnabled(True)
            self.act_btns["salvage"].setText(f"Salvage (+{item['rarity'] + 1 + item['plus']} scrap)")
        else:
            self.detail.setText(item_html(item))
            cost, rc = enhance_cost(item), reforge_cost(item)
            self.act_btns["enhance"].setText(f"Enhance +{item['plus'] + 1} ({fmt(cost)}g)" if item["plus"] < 20 else "Enhance (MAX)")
            self.act_btns["enhance"].setEnabled(item["plus"] < 20 and s["gold"] >= cost)
            self.act_btns["reforge"].setText(f"Reforge ({rc} scrap)")
            self.act_btns["reforge"].setEnabled(bool(item["aff"]) and s["scrap"] >= rc)
            self.act_btns["unequip"].setEnabled(len(s["inv"]) < INV_CAP)

    def _refresh_train(self):
        s = self.eng.s
        amount = [1, 10, 25, 100, "MAX"][s["buy_mode"]]
        for tid, name, effect, _stat, _per, base in TRAIN:
            level = s["train"].get(tid, 0)
            can = train_max(base, level, s["gold"])
            n = max(1, can) if amount == "MAX" else amount
            cost = train_bulk(base, level, n)
            b = self.train_btns[tid]
            b.setText(f"{name}  (Lv {level})   {effect} each\n+{n} for {fmt(cost)} gold")
            b.setEnabled(s["gold"] >= cost)

    def _refresh_rebirth(self):
        s, eng = self.eng.s, self.eng
        gain = eng.rebirth_gain()
        if eng.can_rebirth():
            self.rebirth_info.setText(
                f"Rebirth resets your level, stats, skills, gear, gold and training, but keeps Soul Shards, perks, trophies "
                f"and records. Each shard you ever earn gives +2% damage and +1% HP forever.\n\n"
                f"Best stage this life: {s['best']}.  You would earn {gain} Soul Shards.")
            self.rebirth_btn.setEnabled(True)
            self.rebirth_btn.setText("Click again to REBIRTH" if self.armed == "rebirth" else f"REBIRTH  (+{gain} Soul Shards)")
        else:
            self.rebirth_info.setText(f"Reach stage {REBIRTH_MIN_STAGE} to unlock Rebirth. Best stage this life: {s['best']}.\n"
                                      f"Rebirth gives Soul Shards for permanent damage and perks.")
            self.rebirth_btn.setEnabled(False)
            self.rebirth_btn.setText(f"Locked (stage {REBIRTH_MIN_STAGE})")
        self.shards_label.setText(f"Soul Shards: {s['shards']}   (earned in total: {s['shards_total']}, rebirths: {s['rebirths']})")
        for perk in PERKS:
            pid, name, effect, _stat, _per, _base, mx = perk
            level = s["perks"].get(pid, 0)
            b = self.perk_btns[pid]
            if level >= mx:
                b.setText(f"{name}  (Lv {level}/{mx})\n{effect}  |  MAXED")
                b.setEnabled(False)
            else:
                cost = perk_cost(perk, level)
                b.setText(f"{name}  (Lv {level}/{mx})\n{effect}  |  cost {cost} shards")
                b.setEnabled(s["shards"] >= cost)

    def _refresh_more(self):
        s = self.eng.s
        st = s["st"]
        self.stats_label.setText(
            f"Monsters defeated {fmt(st['kills'])}   Bosses {fmt(st['bosses'])}   Items found {fmt(st['items'])}\n"
            f"Crits {fmt(st['crits'])}   Smites {fmt(st['smites'])}   Gold earned {fmt(st['gold'])}\n"
            f"Best stage ever {s['best_all']}   Rebirths {s['rebirths']}")
        self.trophy_header.setText(f"Trophies {len(s['ach'])}/{len(ACHIEVEMENTS)}  (+1% damage and gold each)")
        for aid, name, desc, _stat, _thr in ACHIEVEMENTS:
            got = aid in s["ach"]
            self.ach_labels[aid].setText(f"{'[x]' if got else '[ ]'} {name}: {desc}")
            self.ach_labels[aid].setStyleSheet("color: #3fb950;" if got else "color: #4d5560;")
        self.reset_btn.setText("Click again to ERASE EVERYTHING" if self.armed == "reset" else "Reset all progress")