"""Loads API keys from keys.env (a file you create, never shared)."""
from pathlib import Path

KEYS_PATH = Path(__file__).resolve().parent.parent / "keys.env"
_cache = None


def _load():
    global _cache
    if _cache is not None:
        return _cache
    _cache = {}
    if KEYS_PATH.exists():
        for line in KEYS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                _cache[k.strip()] = v.strip()
    return _cache


def get_key(name: str) -> str | None:
    return _load().get(name)