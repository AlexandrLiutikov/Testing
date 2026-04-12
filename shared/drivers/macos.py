"""macOS-адаптер Platform Driver Layer (AXUI via AppleScript + OCR fallback)."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Iterable, Optional, Tuple

from shared.drivers.base import BaseDriver
from shared.infra.ocr import find_token_bbox, find_token_position, ocr_image
from shared.infra.screenshots import take_screenshot

logger = logging.getLogger(__name__)


class MacOSDriver(BaseDriver):
    """Реализация macOS-драйвера.

    Primary path:
    - AXUI через AppleScript/System Events (семантический поиск по имени).

    Fallback chain:
    - OCR + click at coordinates
    - coordinate map click (cliclick/System Events)
    - CV stub (для будущего расширения)
    """

    _MENU_LABELS = {
        "home": ["Главная", "Home"],
        "templates": ["Шаблоны", "Templates"],
        "local": ["Локальные файлы", "Локальные", "Local Files", "Local"],
        "collab": ["Совместная работа", "Совместная", "Collaboration"],
        "settings": ["Настройки", "Settings"],
        "about": ["О программе", "О приложении", "About"],
    }

    _COORD_FALLBACK = {
        "home": (0.07, 0.175),
        "templates": (0.07, 0.245),
        "local": (0.07, 0.305),
        "collab": (0.07, 0.385),
        "settings": (0.07, 0.865),
        "about": (0.07, 0.925),
    }

    _WARNING_LABELS = [
        "OK",
        "ОК",
        "Предупреждение",
        "Warning",
        "Ошибка",
        "Error",
        "Разрешить",
        "Allow",
    ]

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------

    def activate_window(self, pid: int) -> None:
        script = [
            'tell application "System Events"',
            f"if not (exists (first process whose unix id is {pid})) then return",
            f'tell (first process whose unix id is {pid})',
            "set frontmost to true",
            "if (count of windows) > 0 then",
            'try',
            'perform action "AXRaise" of front window',
            "end try",
            "end if",
            "end tell",
            "end tell",
        ]
        self._run_osascript(script, timeout_sec=3.0)
        time.sleep(0.35)

    # ------------------------------------------------------------------
    # Semantic click path + fallback chain
    # ------------------------------------------------------------------

    def click_menu_item(self, pid: int, menu_name: str) -> bool:
        labels = self._MENU_LABELS.get(menu_name, [menu_name])

        try:
            if self._click_via_accessibility(pid, labels):
                logger.info("MacOSDriver.click_menu_item('%s'): accessibility", menu_name)
                return True
        except Exception as exc:
            logger.warning(
                "MacOSDriver.click_menu_item('%s'): accessibility error: %s",
                menu_name,
                exc,
            )

        try:
            if self._click_via_ocr(pid, labels):
                logger.info("MacOSDriver.click_menu_item('%s'): OCR fallback", menu_name)
                return True
        except Exception as exc:
            logger.warning(
                "MacOSDriver.click_menu_item('%s'): OCR error: %s",
                menu_name,
                exc,
            )

        try:
            if self._click_via_coordinates(pid, menu_name):
                logger.warning(
                    "MacOSDriver.click_menu_item('%s'): coordinate fallback used",
                    menu_name,
                )
                return True
        except Exception as exc:
            logger.warning(
                "MacOSDriver.click_menu_item('%s'): coordinate fallback error: %s",
                menu_name,
                exc,
            )

        if self._click_via_cv(pid, menu_name):
            logger.info("MacOSDriver.click_menu_item('%s'): CV fallback", menu_name)
            return True

        logger.error("MacOSDriver.click_menu_item('%s'): all fallback paths exhausted", menu_name)
        return False

    def _click_via_accessibility(self, pid: int, labels: Iterable[str]) -> bool:
        for label in labels:
            escaped = self._escape_applescript_text(label)
            script = [
                'tell application "System Events"',
                f"if not (exists (first process whose unix id is {pid})) then return \"NOTFOUND\"",
                f'tell (first process whose unix id is {pid})',
                "set frontmost to true",
                "if (count of windows) = 0 then return \"NOTFOUND\"",
                "tell front window",
                f"set directButtons to (every button whose name is \"{escaped}\")",
                "if (count of directButtons) > 0 then",
                "click item 1 of directButtons",
                'return "CLICKED"',
                "end if",
                f"set directGroups to (every UI element whose name is \"{escaped}\")",
                "repeat with targetEl in directGroups",
                "try",
                'perform action "AXPress" of targetEl',
                'return "CLICKED"',
                "end try",
                "try",
                "click targetEl",
                'return "CLICKED"',
                "end try",
                "end repeat",
                "end tell",
                "end tell",
                "end tell",
                'return "NOTFOUND"',
            ]
            out = self._run_osascript(script, timeout_sec=3.0)
            if out == "CLICKED":
                time.sleep(0.4)
                return True
        return False

    def _click_via_ocr(self, pid: int, labels: Iterable[str]) -> bool:
        rect = self.get_window_rect(pid)
        if not rect:
            return False
        left, top, right, bottom = rect
        width = max(1, right - left)
        height = max(1, bottom - top)

        fd_full, full_path = tempfile.mkstemp(prefix="mac_menu_full_", suffix=".png")
        os.close(fd_full)
        fd_ocr, ocr_path = tempfile.mkstemp(prefix="mac_menu_ocr_", suffix=".png")
        os.close(fd_ocr)

        try:
            take_screenshot(full_path)
            base_x, base_y = left, top
            img_w, img_h = width, height

            try:
                from PIL import Image  # pylint: disable=import-outside-toplevel

                with Image.open(full_path) as img:
                    window_crop = img.crop((left, top, right, bottom))
                    sidebar_w = max(1, int(width * 0.15))
                    sidebar_crop = window_crop.crop((0, 0, sidebar_w, height))
                    sidebar_crop.save(ocr_path)
                    img_w, img_h = sidebar_w, height
            except Exception:
                shutil.copyfile(full_path, ocr_path)
                base_x, base_y = 0, 0

            for label in labels:
                bbox = find_token_bbox(ocr_path, label)
                if bbox:
                    return self._click_abs(pid, base_x + int(bbox["center_x"]), base_y + int(bbox["center_y"]))

            text = ocr_image(ocr_path)
            for label in labels:
                pos = find_token_position(text, label, img_w, img_h)
                if pos:
                    return self._click_abs(pid, base_x + int(pos["center_x"]), base_y + int(pos["center_y"]))
            return False
        finally:
            self._safe_unlink(full_path)
            self._safe_unlink(ocr_path)

    def _click_via_coordinates(self, pid: int, menu_name: str) -> bool:
        rel = self._COORD_FALLBACK.get(menu_name)
        if rel is None:
            return False
        self.click_rel(pid, rel[0], rel[1])
        return True

    @staticmethod
    def _click_via_cv(pid: int, menu_name: str) -> bool:
        _ = pid, menu_name
        return False

    # ------------------------------------------------------------------
    # Input simulation
    # ------------------------------------------------------------------

    def click_rel(self, pid: int, rel_x: float, rel_y: float) -> None:
        rect = self.get_window_rect(pid)
        if not rect:
            return
        left, top, right, bottom = rect
        px = int(left + (right - left) * rel_x)
        py = int(top + (bottom - top) * rel_y)
        self._click_abs(pid, px, py)

    def send_escape(self, pid: int) -> None:
        self.activate_window(pid)
        self._send_key_code(53)  # Escape
        time.sleep(0.35)

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def get_window_rect(self, pid: int) -> Optional[Tuple[int, int, int, int]]:
        script = [
            'tell application "System Events"',
            f"if not (exists (first process whose unix id is {pid})) then return \"NOTFOUND\"",
            f'tell (first process whose unix id is {pid})',
            "if (count of windows) = 0 then return \"NOTFOUND\"",
            "set frontmost to true",
            "set p to position of front window",
            "set s to size of front window",
            "set px to item 1 of p",
            "set py to item 2 of p",
            "set w to item 1 of s",
            "set h to item 2 of s",
            'return (px as text) & "," & (py as text) & "," & (w as text) & "," & (h as text)',
            "end tell",
            "end tell",
        ]
        out = self._run_osascript(script, timeout_sec=4.0)
        if not out or out == "NOTFOUND":
            return None
        vals = self._parse_int_csv(out, expected=4)
        if vals is None:
            return None
        x, y, w, h = vals
        return (x, y, x + w, y + h)

    # ------------------------------------------------------------------
    # Warning/dialog handling
    # ------------------------------------------------------------------

    def detect_warning(self, pid: int, timeout_sec: int = 10) -> bool:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if self._detect_warning_via_accessibility(pid):
                return True
            if self._has_extra_window(pid):
                return True
            time.sleep(0.25)
        return False

    def dismiss_warning(self, pid: int) -> bool:
        if self._dismiss_warning_via_accessibility(pid):
            return True
        self.activate_window(pid)
        if self._send_key_code(36):  # Return
            time.sleep(0.5)
            return True
        return False

    # ------------------------------------------------------------------
    # Process management
    # ------------------------------------------------------------------

    @staticmethod
    def kill_editors() -> None:
        subprocess.run(["pkill", "-x", "editors"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-x", "editors_helper"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-f", "DesktopEditors"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.8)

    @staticmethod
    def launch_editor(editor_path: str, enable_debug: bool = True) -> None:
        args = []
        if enable_debug:
            args.append("--ascdesktop-support-debug-info")
        cmd = MacOSDriver._build_launch_cmd(editor_path, args)
        subprocess.Popen(cmd)

    @staticmethod
    def launch_document(editor_path: str, document_path: str, enable_debug: bool = True) -> None:
        args = []
        if enable_debug:
            args.append("--ascdesktop-support-debug-info")
        args.append(document_path)
        cmd = MacOSDriver._build_launch_cmd(editor_path, args)
        subprocess.Popen(cmd)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_launch_cmd(editor_path: str, args: list[str]) -> list[str]:
        if editor_path.endswith(".app"):
            cmd = ["open", "-a", editor_path]
            if args:
                cmd += ["--args"] + args
            return cmd
        return [editor_path] + args

    @staticmethod
    def _safe_unlink(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass

    @staticmethod
    def _escape_applescript_text(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _norm_text(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    @staticmethod
    def _parse_int_csv(raw: str, expected: int) -> Optional[tuple[int, ...]]:
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) != expected:
            return None
        out = []
        for part in parts:
            try:
                out.append(int(float(part)))
            except ValueError:
                return None
        return tuple(out)

    def _run_osascript(self, lines: list[str], *, timeout_sec: float = 4.0) -> str:
        cmd = ["osascript"]
        for line in lines:
            cmd += ["-e", line]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except Exception:
            return ""
        if result.returncode != 0:
            return ""
        return (result.stdout or "").strip()

    def _click_abs(self, pid: int, x: int, y: int) -> bool:
        self.activate_window(pid)
        if shutil.which("cliclick"):
            try:
                result = subprocess.run(
                    ["cliclick", f"m:{x},{y}", f"c:{x},{y}"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=3.0,
                )
                if result.returncode == 0:
                    time.sleep(0.25)
                    return True
            except Exception:
                pass

        script = [
            'tell application "System Events"',
            f"if not (exists (first process whose unix id is {pid})) then return \"FAILED\"",
            f'tell (first process whose unix id is {pid})',
            "set frontmost to true",
            f"click at {{{x}, {y}}}",
            "end tell",
            "end tell",
            'return "OK"',
        ]
        out = self._run_osascript(script, timeout_sec=3.0)
        if out == "OK":
            time.sleep(0.25)
            return True
        return False

    def _send_key_code(self, key_code: int) -> bool:
        script = [
            'tell application "System Events"',
            f"key code {int(key_code)}",
            "end tell",
            'return "OK"',
        ]
        out = self._run_osascript(script, timeout_sec=2.5)
        return out == "OK"

    def _detect_warning_via_accessibility(self, pid: int) -> bool:
        for label in self._WARNING_LABELS:
            escaped = self._escape_applescript_text(label)
            script = [
                'tell application "System Events"',
                f"if not (exists (first process whose unix id is {pid})) then return \"NOTFOUND\"",
                f'tell (first process whose unix id is {pid})',
                "if (count of windows) = 0 then return \"NOTFOUND\"",
                "tell front window",
                f"set directButtons to (every button whose name is \"{escaped}\")",
                "if (count of directButtons) > 0 then return \"FOUND\"",
                f"set directUI to (every UI element whose name is \"{escaped}\")",
                "if (count of directUI) > 0 then return \"FOUND\"",
                "end tell",
                "end tell",
                "end tell",
                'return "NOTFOUND"',
            ]
            if self._run_osascript(script, timeout_sec=2.5) == "FOUND":
                return True
        return False

    def _dismiss_warning_via_accessibility(self, pid: int) -> bool:
        for label in ("OK", "ОК", "Закрыть", "Close", "Allow", "Разрешить"):
            escaped = self._escape_applescript_text(label)
            script = [
                'tell application "System Events"',
                f"if not (exists (first process whose unix id is {pid})) then return \"NOTFOUND\"",
                f'tell (first process whose unix id is {pid})',
                "set frontmost to true",
                "if (count of windows) = 0 then return \"NOTFOUND\"",
                "tell front window",
                f"set directButtons to (every button whose name is \"{escaped}\")",
                "if (count of directButtons) > 0 then",
                "click item 1 of directButtons",
                'return "CLICKED"',
                "end if",
                "end tell",
                "end tell",
                "end tell",
                'return "NOTFOUND"',
            ]
            if self._run_osascript(script, timeout_sec=2.5) == "CLICKED":
                time.sleep(0.4)
                return True
        return False

    def _has_extra_window(self, pid: int) -> bool:
        script = [
            'tell application "System Events"',
            f"if not (exists (first process whose unix id is {pid})) then return \"0\"",
            f'tell (first process whose unix id is {pid})',
            "return (count of windows) as text",
            "end tell",
            "end tell",
        ]
        out = self._run_osascript(script, timeout_sec=2.0)
        try:
            return int(out) > 1
        except ValueError:
            return False
