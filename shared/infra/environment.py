"""Сбор информации о среде выполнения (§12.1–12.5 SCRIPT_RULES)."""

import os
import platform
import socket
import subprocess
from datetime import datetime


def _is_windows():
    return platform.system() == "Windows"


def _is_linux():
    return platform.system() == "Linux"


def _is_macos():
    return platform.system() == "Darwin"


def detect_os_info() -> dict:
    system = platform.system()
    if system == "Windows":
        return {
            "os_family": "Windows",
            "os_name": f"Windows {platform.release()}",
            "os_version": platform.version(),
        }
    elif system == "Linux":
        info = {}
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    k, _, v = line.strip().partition("=")
                    info[k] = v.strip('"')
        except FileNotFoundError:
            pass
        return {
            "os_family": "Linux",
            "os_name": info.get("PRETTY_NAME", "Linux"),
            "os_version": info.get("VERSION_ID", ""),
        }
    elif system == "Darwin":
        ver = platform.mac_ver()[0]
        return {
            "os_family": "macOS",
            "os_name": f"macOS {ver}",
            "os_version": ver,
        }
    return {"os_family": system, "os_name": system, "os_version": ""}


def detect_screen_resolution() -> str:
    system = platform.system()
    try:
        if system == "Windows":
            import ctypes
            u32 = ctypes.windll.user32
            return f"{u32.GetSystemMetrics(0)}x{u32.GetSystemMetrics(1)}"
        elif system == "Linux":
            r = subprocess.run(
                ["xrandr", "--current"], capture_output=True, text=True,
            )
            for line in r.stdout.splitlines():
                if "*" in line:
                    return line.split()[0]
        elif system == "Darwin":
            r = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True,
            )
            for line in r.stdout.splitlines():
                if "Resolution" in line:
                    return line.split(":")[1].strip()
    except Exception:
        pass
    return "н/д"


def detect_display_scale() -> str:
    try:
        if _is_windows():
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            dc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)
            ctypes.windll.user32.ReleaseDC(0, dc)
            return f"{round(dpi / 96 * 100)}%"
    except Exception:
        pass
    return "100%"


def detect_editor_version(editor_path: str) -> str:
    try:
        if _is_windows():
            ps = f"(Get-Item '{editor_path}').VersionInfo.ProductVersion"
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True,
            )
            ver = r.stdout.strip()
            if ver:
                return ver
        elif _is_linux() or _is_macos():
            r = subprocess.run(
                [editor_path, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if r.stdout.strip():
                return r.stdout.strip()
    except Exception:
        pass
    return "н/д"


def detect_package() -> str:
    system = platform.system()
    try:
        if system == "Linux":
            r = subprocess.run(
                ["dpkg-query", "-W", "-f",
                 "${Package} ${Version} ${Architecture}",
                 "r7-office-editors"],
                capture_output=True, text=True,
            )
            if r.returncode == 0:
                return r.stdout.strip()
            r = subprocess.run(
                ["rpm", "-q", "--qf",
                 "%{NAME} %{VERSION} %{ARCH}",
                 "r7-office-editors"],
                capture_output=True, text=True,
            )
            if r.returncode == 0:
                return r.stdout.strip()
        elif system == "Windows":
            return "exe/msi"
        elif system == "Darwin":
            return "dmg"
    except Exception:
        pass
    return "н/д"


def collect_environment(editor_path: str) -> dict:
    os_info = detect_os_info()
    return {
        "os_family": os_info["os_family"],
        "os_name": os_info["os_name"],
        "os_version": os_info["os_version"],
        "architecture": platform.machine(),
        "package": detect_package(),
        "screen_resolution": detect_screen_resolution(),
        "display_scale": detect_display_scale(),
        "editor_version": detect_editor_version(editor_path),
        "editor_path": editor_path,
        "hostname": socket.gethostname(),
        "run_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def platform_tag() -> str:
    os_info = detect_os_info()
    name = os_info["os_name"].lower().replace(" ", "-")
    arch = platform.machine()
    return f"{name}-{arch}"
