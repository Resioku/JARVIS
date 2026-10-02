# J.A.R.V.I.S.

A floating always-on-top "orb" that expands into a JARVIS-style panel.
Click sections in the Main Menu to drill in; a Back arrow takes you up
a level.

## Setup

1. Install Python 3.10+ (from python.org — check "Add to PATH" during install).
2. Open this folder in VS Code.
3. Open a terminal in VS Code (`` Ctrl+` ``) and run:
   ```
   pip install -r requirements.txt
   ```
4. Run it:
   ```
   python main.py
   ```

A small glowing "J" orb should appear near the top-right of your screen.
Drag it anywhere. Click it (without dragging) to open/close the panel.

## Run it silently on startup (no console window)

1. Press `Win + R`, type `shell:startup`, hit Enter — this opens your
   Windows Startup folder.
2. In that folder, create a new text file named `UITHing.bat` (make sure
   it's `.bat` not `.bat.txt` — enable file extensions in File Explorer
   if you're not sure).
3. Edit it to contain (swap in your actual path to this folder):
   ```
   start "" pythonw "C:\Path\To\UITHing\main.py"
   ```
   `pythonw` (not `python`) runs it without a console window popping up.
4. Log off/on (or just reboot) to test it.

## How everything fits together

```
main.py            -> boots the app. You'll basically never touch this.
ui/overlay.py       -> the Orb + Panel window itself
ui/navigation.py    -> handles Main Menu -> Section -> Detail + Back button
core/discovery.py   -> auto-scans a folder and loads valid plugin files
core/config_store.py -> load/save config.json
core/icon_utils.py  -> pulls the icon out of an .exe
sections/links.py   -> the "Links" section (your exe shortcuts)
sections/games.py   -> the "Games" section (auto-lists games/ folder)
games/clicker.py    -> the clicker game, and your template for new games
```

## Adding a new game

1. Copy `games/clicker.py` -> `games/mygame.py`.
2. Rename `NAME = "Clicker"` to whatever you want the button to say.
3. Replace the widget's logic with your own.
4. Run the app — it just shows up under Games. Nothing else to edit.

The only rule: your file needs a `NAME` variable and a `create_widget()`
function that returns a QWidget. That's the whole "contract."

## Adding a whole new top-level section (like "Games" or "Links")

1. Copy `sections/games.py` as a starting point (it's the simplest one).
2. Set `NAME` to your new section's label.
3. Make `create_widget(nav)` return whatever QWidget you want as that
   section's list/home view. `nav` is the NavStack — call
   `nav.push(some_widget, "Title")` to drill into detail views, and
   it'll get a Back button automatically.
4. Run the app — your new section shows up in the Main Menu.

## Adding a Link (exe shortcut) from the UI

Open the panel -> Links -> "+ Add link" -> browse to the .exe (works
for Steam games too — right-click the game in Steam -> Manage ->
Browse local files to find the actual .exe) -> give it a name. Its
icon, name, and a Launch button will appear.

## Known limitations (fine for now, worth knowing)

- Icon extraction (`core/icon_utils.py`) only works on Windows, and
  saves icons as `.bmp` — no transparency, so icons sit on a small dark
  square. Looks fine against the dark panel theme.
- The clicker game's save file lives at `games/_clicker_save.json` —
  delete it any time to reset progress.
- Voice commands aren't wired up yet — that's a good next step whenever
  you want it (the `speech_recognition` + `pyttsx3` libraries are the
  usual starting point).
