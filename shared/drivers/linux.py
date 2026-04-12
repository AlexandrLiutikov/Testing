"""Linux-адаптер Platform Driver Layer (AT-SPI + OCR + xdotool fallback)."""

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


class LinuxDriver(BaseDriver):
    """Реализация Linux-драйвера.

    Primary path:
    - AT-SPI (`pyatspi`) для семантических кликов/поиска предупреждений.

    Fallback chain:
    - OCR (bbox/token) + клик по абсолютным координатам
    - координатный клик через xdotool
    - CV stub (зарезервировано для будущего этапа)
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
    ]

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------

    def activate_window(self, pid: int) -> None:
        wid = self._resolve_window_id(pid)
        if not wid:
            return
        if self._run_quiet(["xdotool", "windowactivate", "--sync", str(wid)]):
            time.sleep(0.35)
            return
        if self._run_quiet(["wmctrl", "-ia", str(wid)]):
            time.sleep(0.35)

    # ------------------------------------------------------------------
    # Semantic click path + fallback chain
    # ------------------------------------------------------------------

    def click_menu_item(self, pid: int, menu_name: str) -> bool:
        labels = self._MENU_LABELS.get(menu_name, [menu_name])

        try:
            if self._click_via_accessibility(pid, labels):
                logger.info("LinuxDriver.click_menu_item('%s'): accessibility", menu_name)
                return True
        except Exception as exc:
            logger.warning(
                "LinuxDriver.click_menu_item('%s'): accessibility error: %s",
                menu_name,
                exc,
            )

        try:
            if self._click_via_ocr(pid, labels):
                logger.info("LinuxDriver.click_menu_item('%s'): OCR fallback", menu_name)
                return True
        except Exception as exc:
            logger.warning(
                "LinuxDriver.click_menu_item('%s'): OCR error: %s",
                menu_name,
                exc,
            )

        try:
            if self._click_via_coordinates(pid, menu_name):
                logger.warning(
                    "LinuxDriver.click_menu_item('%s'): coordinate fallback used",
                    menu_name,
                )
                return True
        except Exception as exc:
            logger.warning(
                "LinuxDriver.click_menu_item('%s'): coordinate fallback error: %s",
                menu_name,
                exc,
            )

        if self._click_via_cv(pid, menu_name):
            logger.info("LinuxDriver.click_menu_item('%s'): CV fallback", menu_name)
            return True

        logger.error("LinuxDriver.click_menu_item('%s'): all fallback paths exhausted", menu_name)
        return False

    def _click_via_accessibility(self, pid: int, labels: Iterable[str]) -> bool:
        app = self._find_atspi_app(pid)
        if app is None:
            return False

        wanted = {self._norm_text(label) for label in labels if label}
        if not wanted:
            return False

        deadline = time.time() + 5.0
        while time.time() < deadline:
            for node in self._iter_accessibility_nodes(app):
                name = self._norm_text(getattr(node, "name", "") or "")
                if not name or name not in wanted:
                    continue
                if self._press_accessibility_node(node):
                    time.sleep(0.4)
                    return True
            time.sleep(0.2)
        return False

    def _click_via_ocr(self, pid: int, labels: Iterable[str]) -> bool:
        rect = self.get_window_rect(pid)
        if not rect:
            return False
        left, top, right, bottom = rect
        width = max(1, right - left)
        height = max(1, bottom - top)

        fd_full, full_path = tempfile.mkstemp(prefix="linux_menu_full_", suffix=".png")
        os.close(fd_full)
        fd_ocr, ocr_path = tempfile.mkstemp(prefix="linux_menu_ocr_", suffix=".png")
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
                # Если PIL/crop недоступны — пробуем OCR на полном скриншоте.
                shutil.copyfile(full_path, ocr_path)
                base_x, base_y = 0, 0

            for label in labels:
                bbox = find_token_bbox(ocr_path, label)
                if bbox:
                    return self._click_abs(
                        base_x + int(bbox["center_x"]),
                        base_y + int(bbox["center_y"]),
                    )

            text = ocr_image(ocr_path)
            for label in labels:
                pos = find_token_position(text, label, img_w, img_h)
                if pos:
                    return self._click_abs(
                        base_x + int(pos["center_x"]),
                        base_y + int(pos["center_y"]),
                    )
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
        self._click_abs(px, py)

    def send_escape(self, pid: int) -> None:
        self.activate_window(pid)
        self._send_key("Escape")
        time.sleep(0.4)

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def get_window_rect(self, pid: int) -> Optional[Tuple[int, int, int, int]]:
        wid = self._resolve_window_id(pid)
        if not wid:
            return None

        # 1) xdotool getwindowgeometry --shell
        geom = self._read_geometry_via_xdotool(wid)
        if geom:
            return geom

        # 2) xwininfo -id
        return self._read_geometry_via_xwininfo(wid)

    # ------------------------------------------------------------------
    # Warning/dialog handling
    # ------------------------------------------------------------------

    def detect_warning(self, pid: int, timeout_sec: int = 10) -> bool:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if self._detect_warning_via_accessibility(pid):
                return True
            # Тонкий fallback: наличие отдельного модального окна по PID.
            if self._count_windows_for_pid(pid) > 1:
                return True
            time.sleep(0.25)
        return False

    def dismiss_warning(self, pid: int) -> bool:
        if self._dismiss_warning_via_accessibility(pid):
            return True
        self.activate_window(pid)
        if self._send_key("Return"):
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
        subprocess.run(["pkill", "-f", "desktopeditors"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.8)

    @staticmethod
    def launch_editor(editor_path: str, enable_debug: bool = True) -> None:
        cmd = [editor_path]
        if enable_debug:
            cmd.append("--ascdesktop-support-debug-info")
        subprocess.Popen(cmd)

    @staticmethod
    def launch_document(editor_path: str, document_path: str, enable_debug: bool = True) -> None:
        cmd = [editor_path]
        if enable_debug:
            cmd.append("--ascdesktop-support-debug-info")
        cmd.append(document_path)
        subprocess.Popen(cmd)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_unlink(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass

    @staticmethod
    def _norm_text(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    @staticmethod
    def _tool_available(name: str) -> bool:
        return shutil.which(name) is not None

    def _run_quiet(self, command: list[str], *, timeout_sec: float = 5.0) -> bool:
        if not command:
            return False
        if not self._tool_available(command[0]):
            return False
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout_sec,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _run_capture(self, command: list[str], *, timeout_sec: float = 5.0) -> str:
        if not command:
            return ""
        if not self._tool_available(command[0]):
            return ""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
            if result.returncode != 0:
                return ""
            return result.stdout.strip()
        except Exception:
            return ""

    def _resolve_window_id(self, pid: int) -> Optional[str]:
        # Предпочитаем xdotool (обычно даёт "активные" window id).
        out = self._run_capture(["xdotool", "search", "--onlyvisible", "--pid", str(pid)])
        if out:
            first = out.splitlines()[0].strip()
            if first:
                return first

        # fallback через wmctrl.
        out = self._run_capture(["wmctrl", "-lp"])
        if not out:
            return None
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            if parts[2] == str(pid):
                return parts[0]
        return None

    def _count_windows_for_pid(self, pid: int) -> int:
        out = self._run_capture(["wmctrl", "-lp"])
        if not out:
            return 0
        total = 0
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[2] == str(pid):
                total += 1
        return total

    def _read_geometry_via_xdotool(self, wid: str) -> Optional[Tuple[int, int, int, int]]:
        out = self._run_capture(["xdotool", "getwindowgeometry", "--shell", str(wid)])
        if not out:
            return None
        values: dict[str, int] = {}
        for line in out.splitlines():
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip().upper()
            val = val.strip()
            if key in {"X", "Y", "WIDTH", "HEIGHT"}:
                try:
                    values[key] = int(val)
                except ValueError:
                    return None
        if {"X", "Y", "WIDTH", "HEIGHT"} - set(values):
            return None
        return (
            values["X"],
            values["Y"],
            values["X"] + values["WIDTH"],
            values["Y"] + values["HEIGHT"],
        )

    def _read_geometry_via_xwininfo(self, wid: str) -> Optional[Tuple[int, int, int, int]]:
        out = self._run_capture(["xwininfo", "-id", str(wid)])
        if not out:
            return None
        patterns = {
            "x": r"Absolute upper-left X:\s*(-?\d+)",
            "y": r"Absolute upper-left Y:\s*(-?\d+)",
            "w": r"Width:\s*(\d+)",
            "h": r"Height:\s*(\d+)",
        }
        data: dict[str, int] = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, out)
            if not match:
                return None
            data[key] = int(match.group(1))
        return (data["x"], data["y"], data["x"] + data["w"], data["y"] + data["h"])

    def _click_abs(self, x: int, y: int) -> bool:
        if not self._tool_available("xdotool"):
            return False
        ok_move = self._run_quiet(["xdotool", "mousemove", "--sync", str(x), str(y)])
        if not ok_move:
            return False
        ok_click = self._run_quiet(["xdotool", "click", "1"])
        if ok_click:
            time.sleep(0.25)
        return ok_click

    def _send_key(self, key_name: str) -> bool:
        if not self._tool_available("xdotool"):
            return False
        return self._run_quiet(["xdotool", "key", "--clearmodifiers", key_name])

    @staticmethod
    def _iter_accessibility_nodes(root):
        stack = [root]
        while stack:
            node = stack.pop()
            yield node
            try:
                count = int(getattr(node, "childCount", 0))
            except Exception:
                count = 0
            for idx in range(count - 1, -1, -1):
                try:
                    child = node.getChildAtIndex(idx)
                except Exception:
                    child = None
                if child is not None:
                    stack.append(child)

    @staticmethod
    def _get_node_pid(node) -> Optional[int]:
        try:
            val = node.get_process_id()
            if isinstance(val, int):
                return val
        except Exception:
            pass
        try:
            val = getattr(node, "pid", None)
            if isinstance(val, int):
                return val
        except Exception:
            pass
        return None

    def _find_atspi_app(self, pid: int):
        try:
            import pyatspi  # pylint: disable=import-outside-toplevel
        except Exception:
            return None
        try:
            desktop = pyatspi.Registry.getDesktop(0)
        except Exception:
            return None
        try:
            child_count = int(getattr(desktop, "childCount", 0))
        except Exception:
            child_count = 0
        for idx in range(child_count):
            try:
                app = desktop.getChildAtIndex(idx)
            except Exception:
                continue
            if self._get_node_pid(app) == pid:
                return app
        return None

    @staticmethod
    def _press_accessibility_node(node) -> bool:
        try:
            action = node.queryAction()
        except Exception:
            return False
        try:
            action_count = int(getattr(action, "nActions", 0))
        except Exception:
            action_count = 0
        for idx in range(action_count):
            try:
                name = str(action.getName(idx) or "").lower()
            except Exception:
                name = ""
            if any(token in name for token in ("click", "press", "activate")):
                try:
                    if action.doAction(idx):
                        return True
                except Exception:
                    continue
        return False

    def _detect_warning_via_accessibility(self, pid: int) -> bool:
        app = self._find_atspi_app(pid)
        if app is None:
            return False
        labels = {self._norm_text(label) for label in self._WARNING_LABELS}
        for node in self._iter_accessibility_nodes(app):
            name = self._norm_text(getattr(node, "name", "") or "")
            if name in labels:
                return True
        return False

    def _dismiss_warning_via_accessibility(self, pid: int) -> bool:
        app = self._find_atspi_app(pid)
        if app is None:
            return False
        labels = {self._norm_text(label) for label in ("OK", "ОК", "Закрыть", "Close")}
        for node in self._iter_accessibility_nodes(app):
            name = self._norm_text(getattr(node, "name", "") or "")
            if name not in labels:
                continue
            if self._press_accessibility_node(node):
                time.sleep(0.4)
                return True
        return False
