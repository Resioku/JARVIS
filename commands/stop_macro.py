"""
VOICE COMMAND: Stop macro
Say "stop" (optionally with a macro's name, e.g. "stop the autoclicker")
to end a looping macro. Only macros with "Loop until stopped" turned on
need this — a normal macro just finishes on its own.
"""
from core.macro_store import load_macros, match_macro

NAME = "Stop macro"
TRIGGERS = ["stop"]


def handle(text: str) -> str:
    from core.macro_runner import stop_macro_by_name, stop_all

    loop_macros = [m for m in load_macros() if m.get("loop")]
    macro = match_macro(text, loop_macros)

    if macro:
        if stop_macro_by_name(macro["name"]):
            return f"Stopped {macro['name']}, sir."
        return f"{macro['name']} isn't running, sir."

    stop_all()
    return "Stopped, sir."