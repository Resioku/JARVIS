"""
Shared text cleanup so commands can match what you said reliably.
"""
import re


# ---------- Functions ----------

def normalize(text: str) -> str:
    """Lowercase, no punctuation, single spaces. 'What's the time?!' -> "what's the time" """
    text = text.lower().replace("\u2019", "'")
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    return " ".join(text.split())