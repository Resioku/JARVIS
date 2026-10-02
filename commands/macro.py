"""
VOICE COMMAND: Run macro
Every saved macro is automatically a voice trigger — say its name (with
or without "run"/"macro" around it, e.g. "run the autoclicker macro" or
just "autoclicker") to play it. Loop macros keep going until you say
"stop" (see commands/stop_macro.py). Build macros in the Macros section.
"""
from core.macro_store import load_macros, match_macro

# ---------- Contract ----------
NAME = "Run macro"
TRIGGERS = [m["name"] for m in load_macros()]   # this file is re-read fresh every time you speak, so this stays in sync


def handle(text: str) -> str:
    from core.macro_runner import trigger_macro   # imported here so voice still works if `keyboard`/`mouse` aren't installed yet

    macro = match_macro(text)
    if macro is None:
        return "I couldn't find that macro, sir."
    return trigger_macro(macro)