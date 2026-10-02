"""Fallback for anything no command in commands/ matched."""
from ai.selector import ask_active


def ask(text: str) -> str:
    return ask_active(text)