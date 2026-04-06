"""Базовый (абстрактный) интерфейс Platform Driver Layer."""

import platform
import subprocess
import time
from typing import Optional, Tuple


def _is_windows():
    return platform.system() == "Windows"


def _is_linux():
    return platform.system() == "Linux"


def _is_macos():
    return platform.system() == "Darwin"


def activate_window(pid: int):
    if _is_windows():
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(New-Object -ComObject WScript.Shell).AppActivate({pid})"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    elif _is_linux():
        subprocess.run(
            ["xdotool", "search", "--pid", str(pid), "--onlyvisible",
             "--limit", "1", "windowactivate"],
            stderr=subprocess.DEVNULL,
        )
    time.sleep(0.5)  # ожидание активации окна (Platform Driver Layer)


def _get_hwnd_from_pid(pid: int) -> Optional[int]:
    if not _is_windows():
        return None
    ps = (
        f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).MainWindowHandle"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True,
    )
    val = r.stdout.strip()
    try:
        hwnd = int(val)
        if hwnd != 0:
            return hwnd
    except (ValueError, TypeError):
        pass
    return None


def _get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    import ctypes

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long), ("top", ctypes.c_long),
            ("right", ctypes.c_long), ("bottom", ctypes.c_long),
        ]

    rect = RECT()
    ok = ctypes.windll.user32.GetWindowRect(
        ctypes.c_void_p(hwnd), ctypes.byref(rect)
    )
    if ok:
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None


def click_rel(pid: int, rel_x: float, rel_y: float):
    """Клик по относительной позиции в окне (координатный fallback).

    R7 Office использует пользовательскую отрисовку UI (CEF),
    стандартные элементы Accessibility API недоступны для пунктов
    левого меню стартового экрана.
    """
    if _is_windows():
        import ctypes

        hwnd = _get_hwnd_from_pid(pid)
        if not hwnd:
            return
        rect = _get_window_rect(hwnd)
        if not rect:
            return
        left, top, right, bottom = rect

        px = int(left + (right - left) * rel_x)
        py = int(top + (bottom - top) * rel_y)

        ctypes.windll.user32.SetCursorPos(px, py)
        time.sleep(0.08)
        ctypes.windll.user32.mouse_event(
            ctypes.c_ulong(0x0002), ctypes.c_ulong(0),
            ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_size_t(0),
        )
        ctypes.windll.user32.mouse_event(
            ctypes.c_ulong(0x0004), ctypes.c_ulong(0),
            ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_size_t(0),
        )
        time.sleep(0.5)

    elif _is_linux():
        try:
            r = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowgeometry", "--shell"],
                capture_output=True, text=True,
            )
            geom = {}
            for line in r.stdout.splitlines():
                k, _, v = line.partition("=")
                if v.isdigit():
                    geom[k] = int(v)
            x_pos = geom.get("X", 0) + int(geom.get("WIDTH", 0) * rel_x)
            y_pos = geom.get("Y", 0) + int(geom.get("HEIGHT", 0) * rel_y)
            subprocess.run(
                ["xdotool", "mousemove", str(x_pos), str(y_pos)],
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.08)
            subprocess.run(["xdotool", "click", "1"], stderr=subprocess.DEVNULL)
            time.sleep(0.5)
        except Exception:
            pass

    elif _is_macos():
        try:
            script = (
                'tell application "System Events"\n'
                '  set frontApp to first application process whose frontmost is true\n'
                '  set win to first window of frontApp\n'
                '  set {x, y} to position of win\n'
                '  set {w, h} to size of win\n'
                '  return (x as text) & " " & (y as text) & " " & (w as text) & " " & (h as text)\n'
                'end tell'
            )
            r = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True,
            )
            parts = r.stdout.strip().split()
            if len(parts) == 4:
                wx, wy, ww, wh = (int(p) for p in parts)
                px = wx + int(ww * rel_x)
                py = wy + int(wh * rel_y)
                subprocess.run(
                    ["cliclick", f"c:{px},{py}"], stderr=subprocess.DEVNULL,
                )
                time.sleep(0.5)
        except Exception:
            pass


def send_escape(pid: int):
    activate_window(pid)
    if _is_windows():
        import ctypes
        VK_ESCAPE = 0x1B
        KEYEVENTF_KEYUP = 0x0002
        ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, 0, 0)
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
    elif _is_linux():
        subprocess.run(["xdotool", "key", "Escape"], stderr=subprocess.DEVNULL)
    elif _is_macos():
        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to key code 53'],
            stderr=subprocess.DEVNULL,
        )
    time.sleep(1)  # ожидание обработки нажатия (Platform Driver Layer)
