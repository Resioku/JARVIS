"""
VOICE COMMAND: Stop macro
Say "stop" (optionally with a macro's name, e.g. "stop the autoclicker")
to end a running macro. Plain "stop" ends every running macro.
"""
from core.macro_store import load_macros, match_macro

NAME = "Stop macro"
TRIGGERS = ["stop"]


def handle(text: str) -> str:
    from core.macro_runner import stop_macro_by_name, stop_all, is_running

    running = [m for m in load_macros() if is_running(m["name"])]
    macro = match_macro(text, running)

    if macro:
        stop_macro_by_name(macro["name"])
        return f"Stopped {macro['name']}, sir."

    stop_all()
    return "Stopped, sir."