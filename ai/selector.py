"""
Tracks which AI provider is active and routes questions to it.
Providers are auto-discovered from this folder (NAME + ask()), same
pattern as games/ and commands/ — drop in groq.py, openai.py, etc.
"""
import json
from pathlib import Path

from core.discovery import load_plugins

AI_FOLDER = Path(__file__).resolve().parent
STATE_PATH = AI_FOLDER / "_active.json"


def list_providers():
    return load_plugins(AI_FOLDER, required_attrs=("NAME", "ask"))


def get_active_name() -> str:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text()).get("active", "")
    providers = list_providers()
    return providers[0].NAME if providers else ""


def set_active(name: str):
    STATE_PATH.write_text(json.dumps({"active": name}))


def ask_active(text: str) -> str:
    name = get_active_name()
    for module in list_providers():
        if module.NAME == name:
            return module.ask(text)
    return "No AI provider is set up yet, sir."