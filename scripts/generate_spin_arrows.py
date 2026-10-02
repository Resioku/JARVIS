"""
Generates the tiny up/down triangle icons used by spinbox controls
(assets/spin_up.png, assets/spin_down.png). Needed because Qt stops
drawing its own arrow glyph on a spinbox button the moment you style
that button's background via QSS — you have to supply your own.
Runs automatically the first time a section using them is opened; run
directly to regenerate (e.g. after changing the color).
"""
from pathlib import Path
from PIL import Image, ImageDraw

PROJECT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_DIR / "assets"

ARROW_COLOR = (0, 229, 255, 255)   # matches the app's cyan accent
SIZE = 16


def _triangle(path: Path, pointing: str):
    ASSETS_DIR.mkdir(exist_ok=True)
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = 4
    if pointing == "up":
        points = [(SIZE / 2, pad), (pad, SIZE - pad), (SIZE - pad, SIZE - pad)]
    else:
        points = [(pad, pad), (SIZE - pad, pad), (SIZE / 2, SIZE - pad)]
    draw.polygon(points, fill=ARROW_COLOR)
    img.save(path)


def generate():
    _triangle(ASSETS_DIR / "spin_up.png", "up")
    _triangle(ASSETS_DIR / "spin_down.png", "down")


if __name__ == "__main__":
    generate()
    print(f"Generated arrow icons in {ASSETS_DIR}")