"""Скриншоты — кроссплатформенная реализация (§5 SCRIPT_RULES)."""

import platform
import subprocess
from typing import Optional, Tuple


def _normalize_bbox(bbox: Optional[Tuple[int, int, int, int]]) -> Optional[Tuple[int, int, int, int]]:
    if not bbox:
        return None
    if len(bbox) != 4:
        return None
    left, top, right, bottom = [int(v) for v in bbox]
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def take_screenshot(path: str, bbox: Optional[Tuple[int, int, int, int]] = None):
    bbox = _normalize_bbox(bbox)
    try:
        from PIL import ImageGrab

        img = ImageGrab.grab(bbox=bbox) if bbox else ImageGrab.grab()
        img.save(path, "PNG")
        return
    except ImportError:
        pass

    system = platform.system()
    if system == "Windows":
        if bbox:
            left, top, right, bottom = bbox
            width = right - left
            height = bottom - top
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
                f"$left={left};$top={top};$width={width};$height={height};"
                "$bmp=New-Object System.Drawing.Bitmap $width,$height;"
                "$g=[System.Drawing.Graphics]::FromImage($bmp);"
                "$src=New-Object System.Drawing.Point $left,$top;"
                "$dst=[System.Drawing.Point]::Empty;"
                "$size=New-Object System.Drawing.Size $width,$height;"
                "$g.CopyFromScreen($src,$dst,$size);"
                f"$bmp.Save('{path}',[System.Drawing.Imaging.ImageFormat]::Png);"
                "$g.Dispose();$bmp.Dispose()"
            )
        else:
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
                "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
                "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
                "$g=[System.Drawing.Graphics]::FromImage($bmp);"
                "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
                f"$bmp.Save('{path}',[System.Drawing.Imaging.ImageFormat]::Png);"
                "$g.Dispose();$bmp.Dispose()"
            )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    elif system == "Linux":
        subprocess.run(["import", "-window", "root", path], check=True)
    elif system == "Darwin":
        subprocess.run(["screencapture", path], check=True)
