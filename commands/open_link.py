"""
VOICE COMMAND: Open link
"Open Elden Ring" launches whatever you named Elden Ring in the Links
section. Names don't have to be exact — it tolerates small mishearings.
"""
import difflib
import os

from core.config_store import load_config
from voice.textutil import normalize

# ---------- Contract ----------
NAME = "Open link"
TRIGGERS = ["open", "launch"]

# ---------- Variables ----------
SKIP_WORDS = set(TRIGGERS) | {"the", "my", "up"}


# ---------- Functions ----------

def handle(text: str) -> str:
    links = load_config().get("links", [])
    if not links:
        return "You haven't added any links yet."

    # drop "open" / "launch" / "the" from the front, what's left is the name
    words = text.split()
    while words and words[0] in SKIP_WORDS:
        words.pop(0)
    wanted = " ".join(words)
    if not wanted:
        return "Open what, sir?"

    by_name = {normalize(link["name"]): link for link in links if normalize(link["name"])}

    match = None
    for name, link in by_name.items():
        if name in wanted or wanted in name:
            match = link
            break
    if match is None:
        close = difflib.get_close_matches(wanted, list(by_name), n=1, cutoff=0.6)
        if close:
            match = by_name[close[0]]
    if match is None:
        return f"I couldn't find {wanted} in your links."

    try:
        os.startfile(match["path"])
    except Exception:
        return f"I couldn't launch {match['name']}."
    return f"Opening {match['name']}."