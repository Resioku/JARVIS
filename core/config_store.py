"""
Tiny wrapper around config.json so other files don't need to know
the file path or JSON details.
"""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
ICONS_DIR = Path(__file__).resolve().parent.parent / "icons"
ICONS_DIR.mkdir(exist_ok=True)

DEFAULT_CONFIG = {"links": []}


# ---------- Functions ----------

def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return dict(DEFAULT_CONFIG)


def save_config(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
