"""Скриншоты — кроссплатформенная реализация (§5 SCRIPT_RULES)."""

import platform
import subprocess


def take_screenshot(path: str):
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.save(path, "PNG")
        return
    except ImportError:
        pass

    system = platform.system()
    if system == "Windows":
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
