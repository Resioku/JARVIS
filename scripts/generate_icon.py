"""
Generates assets/icon.ico — the cyan "J" badge icon used for the
taskbar/Desktop shortcut. create_shortcut.py runs this automatically if
the icon doesn't exist yet; run it directly if you ever want to
redesign the icon and regenerate it.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ---------- Settings ----------
PROJECT_DIR = Path(__file__).resolve().parent.parent
ICON_PATH = PROJECT_DIR / "assets" / "icon.ico"

BG_COLOR = (13, 17, 23, 255)       # matches the orb's dark background
ACCENT_COLOR = (0, 229, 255, 255)  # matches the orb's cyan accent
SIZES = [16, 32, 48, 64, 128, 256]

FONT_CANDIDATES = (
    "segoeuib.ttf",              # Windows
    "arialbd.ttf",               # Windows fallback
    "DejaVuSans-Bold.ttf",       # fallback if neither is found
)


# ---------- Functions ----------

def generate_icon(path: Path = ICON_PATH) -> Path:
    path.parent.mkdir(exist_ok=True)

    # draw big, then let Pillow downscale for each size — much cleaner
    # edges than drawing small shapes directly at tiny resolutions
    canvas_size = 512
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.ellipse((0, 0, canvas_size, canvas_size), fill=BG_COLOR)

    ring_width = 18
    draw.ellipse(
        (ring_width, ring_width, canvas_size - ring_width, canvas_size - ring_width),
        outline=ACCENT_COLOR, width=10,
    )

    font = None
    for candidate in FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(candidate, size=290)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    text = "J"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((canvas_size - text_w) / 2 - bbox[0], (canvas_size - text_h) / 2 - bbox[1]),
        text, font=font, fill=ACCENT_COLOR,
    )

    image.save(path, sizes=[(s, s) for s in SIZES])
    return path


if __name__ == "__main__":
    out = generate_icon()
    print(f"Icon generated at {out}")