"""
Loads/saves macros.json — the list of saved macros (name, hotkey, loop
flag, steps) — plus shared voice-matching so both the "run" and "stop"
voice commands find the right macro the same way.
"""
import difflib
import json
from pathlib import Path

import jellyfish

from voice.textutil import normalize

MACROS_PATH = Path(__file__).resolve().parent.parent / "macros.json"

# words stripped out before fuzzy-matching, so "run the autoclicker macro"
# and "stop autoclicker please" both boil down to just the macro's name
FILLER_WORDS = {"run", "start", "play", "execute", "stop", "end", "the", "a", "macro", "please"}


def load_macros() -> list:
    if MACROS_PATH.exists():
        return json.loads(MACROS_PATH.read_text(encoding="utf-8"))
    return []


def save_macros(macros: list):
    MACROS_PATH.write_text(json.dumps(macros, indent=2), encoding="utf-8")


def match_macro(text: str, macros: list = None):
    """Finds which saved macro a spoken phrase refers to, or None.
    Tries an exact whole-word match first, then falls back to fuzzy
    matching on the phrase with filler words stripped — this is what
    makes multi-word or slightly misheard names still work."""
    macros = load_macros() if macros is None else macros
    if not macros:
        return None

    said = normalize(text)
    padded = f" {said} "
    exact = [m for m in macros if f" {normalize(m['name'])} " in padded]
    if exact:
        return max(exact, key=lambda m: len(m["name"]))

    stripped = " ".join(w for w in said.split() if w not in FILLER_WORDS)
    if not stripped:
        return None
    names = [normalize(m["name"]) for m in macros]

    close = difflib.get_close_matches(stripped, names, n=1, cutoff=0.5)
    if close:
        return macros[names.index(close[0])]

    # phonetic fallback: catches names that sound right but got misheard/
    # misspelled by STT (e.g. "well skate" heard as "will skid" — both
    # produce the same metaphone code, even though the letters differ a lot)
    heard_sound = jellyfish.metaphone(stripped)
    name_sounds = [jellyfish.metaphone(n) for n in names]
    if heard_sound in name_sounds:
        return macros[name_sounds.index(heard_sound)]
    close_sounds = difflib.get_close_matches(heard_sound, name_sounds, n=1, cutoff=0.6)
    if close_sounds:
        return macros[name_sounds.index(close_sounds[0])]

    return None