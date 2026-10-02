"""
Run this ONCE:  python scripts/create_shortcut.py

Creates a JARVIS.lnk shortcut on your Desktop that launches the app
silently (no console window). Afterward, right-click that shortcut and
choose "Pin to taskbar" — you can then delete the Desktop copy if you
want, the pinned version keeps working.
"""
import sys
from pathlib import Path
import win32com.client

from generate_icon import generate_icon, ICON_PATH

# ---------- Settings ----------
PROJECT_DIR = Path(__file__).resolve().parent.parent
MAIN_PY = PROJECT_DIR / "main.py"
PYTHONW = Path(sys.executable).with_name("pythonw.exe")  # same install, no console window
SHORTCUT_PATH = Path.home() / "Desktop" / "JARVIS.lnk"


# ---------- Build the shortcut ----------
def main():
    if not PYTHONW.exists():
        print(f"Couldn't find pythonw.exe next to {sys.executable} — is this a normal Python install?")
        return

    if not ICON_PATH.exists():
        generate_icon()

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(SHORTCUT_PATH))
    shortcut.TargetPath = str(PYTHONW)
    shortcut.Arguments = f'"{MAIN_PY}"'
    shortcut.WorkingDirectory = str(PROJECT_DIR)
    shortcut.IconLocation = str(ICON_PATH)
    shortcut.Save()

    print(f"Shortcut created: {SHORTCUT_PATH}")
    print("Right-click it and choose 'Pin to taskbar'.")


if __name__ == "__main__":
    main()