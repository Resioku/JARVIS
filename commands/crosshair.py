"""
VOICE COMMAND: Crosshair
Toggles a small red dot centered on your screen — handy as a crosshair
overlay for games that don't have their own.
"""
NAME = "Crosshair"
TRIGGERS = ["crosshair", "cross hair"]


def handle(text: str) -> str:
    from ui.crosshair import toggle
    return toggle()