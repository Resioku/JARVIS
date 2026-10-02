"""Loads/saves the crosshair overlay's settings (offset, size, color)."""
import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "crosshair_settings.json"

DEFAULTS = {"offset_x": 0, "offset_y": 0, "size": 20, "color": "#ff3b3b"}


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    return dict(DEFAULTS)


def save_settings(settings: dict):
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")