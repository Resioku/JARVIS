"""
Decides what to do with what you said.
1. Checks every file in commands/ (free and instant) for an exact trigger match.
2. If nothing matches exactly, tries a fuzzy/phonetic macro match as a last
   resort — macro names are short, user-made words, the most likely thing
   to come out of speech-to-text mangled (e.g. "well skate" heard as
   "well skid"). This has to live here, not in commands/macros.py, because
   the exact-trigger loop above never calls a module's handle() unless its
   name already appears verbatim in what you said.
3. If still nothing, hands it to the brain (AI).

Command files are re-read on every request, so you can edit or add one
while JARVIS is running and it takes effect on the next thing you say.
"""
import logging
from pathlib import Path

from core.discovery import load_plugins
from voice.brain import ask
from voice.textutil import normalize

log = logging.getLogger(__name__)

# ---------- Variables ----------
COMMANDS_FOLDER = Path(__file__).resolve().parent.parent / "commands"


# ---------- Functions ----------

def route(text: str) -> str:
    """Returns the sentence JARVIS should say back."""
    said = normalize(text)
    padded = f" {said} "

    best_module, best_length = None, 0
    for module in load_plugins(COMMANDS_FOLDER, required_attrs=("NAME", "TRIGGERS", "handle")):
        for trigger in module.TRIGGERS:
            phrase = normalize(trigger)
            # whole-word match; the longest (most specific) trigger wins
            if phrase and f" {phrase} " in padded and len(phrase) > best_length:
                best_module, best_length = module, len(phrase)

    if best_module:
        try:
            return best_module.handle(said) or ""
        except Exception:
            log.exception("Command %s failed", best_module.NAME)
            return "Something went wrong running that command."

    fuzzy_reply = _try_fuzzy_macro(said)
    if fuzzy_reply is not None:
        return fuzzy_reply

    return ask(text)


def _try_fuzzy_macro(said: str):
    """Last-resort check: does this sound enough like a saved macro's name
    to run it, even though no exact trigger matched? Returns None (not a
    command reply) if nothing close enough was found."""
    try:
        from core.macro_store import load_macros, match_macro
        from core.macro_runner import trigger_macro
    except ImportError:
        return None   # keyboard/mouse libs not installed — macros aren't available

    macro = match_macro(said, load_macros())
    if macro is None:
        return None
    return trigger_macro(macro)