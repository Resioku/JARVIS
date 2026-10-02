"""
Pulls the icon baked into a Windows .exe (or .lnk shortcut target) so
Links can show the real app/game icon instead of a generic placeholder.
Requires pywin32 (Windows only).
"""
import re
from pathlib import Path

from core.config_store import ICONS_DIR

try:
    import win32gui
    import win32ui
    import win32con
    import win32api
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


# ---------- Functions ----------

def _safe_filename(name: str) -> str:
    """Turns a display name into a filesystem-safe cache filename."""
    return re.sub(r"[^\w\-]+", "_", name).strip("_").lower() or "icon"


def get_icon_path(exe_path: str, display_name: str, size: int = 64) -> str | None:
    """
    Extracts the icon for exe_path, saves it to /icons/<name>.bmp,
    and returns that cache path (or None if extraction failed / unsupported).
    Re-uses the cached file if it already exists.
    """
    cache_path = ICONS_DIR / f"{_safe_filename(display_name)}.bmp"
    if cache_path.exists():
        return str(cache_path)

    if not WIN32_AVAILABLE:
        return None

    try:
        large, small = win32gui.ExtractIconEx(exe_path, 0)
        hicon = large[0] if large else (small[0] if small else None)
        for h in large[1:] if large else []:
            win32gui.DestroyIcon(h)
        if large:
            for h in small:
                win32gui.DestroyIcon(h)
        elif small:
            for h in small[1:]:
                win32gui.DestroyIcon(h)

        if hicon is None:
            return None

        # draw the icon onto an in-memory bitmap, then save it to disk.
        # DrawIcon draws at the icon's native size (often 32x32) regardless
        # of the bitmap size, leaving the rest blank — DrawIconEx lets us
        # stretch it to fill the full canvas instead.
        hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(hdc, size, size)
        hdc_mem = hdc.CreateCompatibleDC()
        hdc_mem.SelectObject(hbmp)
        hdc_mem.FillSolidRect((0, 0, size, size), win32api.RGB(13, 17, 23))  # match the dark theme
        win32gui.DrawIconEx(hdc_mem.GetSafeHdc(), 0, 0, hicon, size, size, 0, None, win32con.DI_NORMAL)
        hbmp.SaveBitmapFile(hdc_mem, str(cache_path))

        win32gui.DestroyIcon(hicon)
        hdc_mem.DeleteDC()
        hdc.DeleteDC()
        return str(cache_path)

    except Exception as e:
        print(f"[icon_utils] Couldn't extract icon for {exe_path}: {e}")
        return None
