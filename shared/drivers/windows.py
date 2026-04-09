"""Windows-адаптер Platform Driver Layer (UIAutomation + ctypes)."""

import logging
import subprocess
import time
from typing import Optional, Tuple

from shared.drivers.base import BaseDriver

logger = logging.getLogger(__name__)


class WindowsDriver(BaseDriver):
    """Реализация драйвера для Windows.

    Использует:
    - WScript.Shell.AppActivate / WMI для активации окон
    - ctypes (user32) для геометрии окон и эмуляции ввода
    - UIAutomationClient (PowerShell) для обнаружения модальных диалогов
    """

    # Видимые подписи пунктов левого меню стартового экрана.
    # Ключ — внутренний идентификатор, значение — список возможных
    # пользовательских названий (локализация/варианты сборок), по которым
    # ищут Accessibility API и OCR. Coordinate fallback использует ключ.
    _MENU_LABELS = {
        "home":      ["Главная", "Home"],
        "templates": ["Шаблоны", "Templates"],
        "local":     ["Локальные файлы", "Локальные", "Local Files", "Local"],
        "collab":    ["Совместная", "Совместная работа", "Collaboration"],
        "settings":  ["Настройки", "Settings"],
        "about":     ["О программе", "О приложении", "About"],
    }

    # ---------------------------------------------------------------
    # Window management
    # ---------------------------------------------------------------

    def activate_window(self, pid: int) -> None:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(New-Object -ComObject WScript.Shell).AppActivate({pid})"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)

    # ---------------------------------------------------------------
    # Window geometry
    # ---------------------------------------------------------------

    def get_window_rect(self, pid: int) -> Optional[Tuple[int, int, int, int]]:
        hwnd = self._get_hwnd_from_pid(pid)
        if not hwnd:
            return None
        return self._get_window_rect(hwnd)

    def _get_hwnd_from_pid(self, pid: int) -> Optional[int]:
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

    @staticmethod
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

    # ---------------------------------------------------------------
    # Semantic UI interaction (primary path with fallback chain)
    # ---------------------------------------------------------------

    def click_menu_item(self, pid: int, menu_name: str) -> bool:
        """Кликнуть по пункту левого меню стартового экрана с fallback цепочкой.

        ВАЖНО: левое меню R7 Editors — часть CEF-поверхности, и
        Accessibility API выдаёт неоднозначные совпадения по имени
        (та же подпись встречается на карточках в центральной области,
        напр. «Шаблоны»). Поэтому для пунктов левого меню путь
        Accessibility отключён: первичный путь — OCR, ограниченный
        областью сайдбара.

        Порядок fallback:
        1. (пропущен для CEF-сайдбара) Accessibility API
        2. OCR скриншота (сайдбар) + клик по координатам текста
        3. Координатный клик (крайний резерв, логируется)
        4. Computer Vision (заглушка для будущего расширения)
        """
        # Fallback 1: Accessibility API — отключено для сайдбара CEF (см. docstring).
        # Путь оставлен в классе и доступен для других меню, но не вызывается здесь.

        # Fallback 2: OCR
        try:
            if self._click_via_ocr(pid, menu_name):
                logger.info(f"click_menu_item: '{menu_name}' — клик через OCR")
                return True
        except Exception as e:
            logger.warning(f"click_menu_item: OCR недоступен для '{menu_name}': {e}")

        # Fallback 3: Координаты (крайний резерв)
        try:
            if self._click_via_coordinates(pid, menu_name):
                logger.warning(
                    f"click_menu_item: '{menu_name}' — использован координатный клик (FALLBACK). "
                    f"Причина: Accessibility API и OCR недоступны."
                )
                return True
        except Exception as e:
            logger.warning(f"click_menu_item: координатный клик недоступен для '{menu_name}': {e}")

        # Fallback 4: Computer Vision (заглушка)
        try:
            if self._click_via_cv(pid, menu_name):
                logger.info(f"click_menu_item: '{menu_name}' — клик через CV")
                return True
        except Exception as e:
            logger.warning(f"click_menu_item: CV недоступен для '{menu_name}': {e}")

        logger.error(f"click_menu_item: ВСЕ FALLBACK исчерпаны для '{menu_name}'")
        return False

    def _click_via_accessibility(self, pid: int, menu_name: str) -> bool:
        """Попытка клика через UIAutomation API (PowerShell).

        Ищет элемент UIA по всем известным подписям (`_MENU_LABELS`) —
        т.к. `menu_name` это внутренний ключ, а не то, что видит пользователь.
        """
        labels = self._MENU_LABELS.get(menu_name, [menu_name])
        # Безопасная сериализация в литерал PS-массива.
        ps_labels = ", ".join(
            "'{}'".format(lbl.replace("'", "''")) for lbl in labels
        )
        ps = f"""
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$root = [System.Windows.Automation.AutomationElement]::RootElement
$pidCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty, {pid})
$labels = @({ps_labels})

$dl = (Get-Date).AddSeconds(5)
while ((Get-Date) -lt $dl) {{
    $wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $pidCond)
    foreach ($w in $wins) {{
        foreach ($lbl in $labels) {{
            $nameCond = New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::NameProperty, $lbl)
            $elem = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $nameCond)
            if ($elem) {{
                try {{
                    $ip = $elem.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                    $ip.Invoke()
                    Write-Output "CLICKED"
                    exit
                }} catch {{}}
            }}
        }}
    }}
    Start-Sleep -Milliseconds 300
}}
Write-Output "NOTFOUND"
"""
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True,
        )
        result = r.stdout.strip()
        if result == "CLICKED":
            time.sleep(0.6)
            return True
        return False

    def _click_via_ocr(self, pid: int, menu_name: str) -> bool:
        """Попытка клика через OCR скриншота."""
        from shared.infra.screenshots import take_screenshot
        from shared.infra.ocr import ocr_image, find_token_position, find_token_bbox

        hwnd = self._get_hwnd_from_pid(pid)
        if not hwnd:
            return False

        # Сделать скриншот окна
        import tempfile
        import os
        tmp_dir = tempfile.gettempdir()
        screenshot_path = os.path.join(tmp_dir, f"ocr_menu_{pid}_{int(time.time())}.png")
        
        # Скриншот только области окна
        rect = self._get_window_rect(hwnd)
        if not rect:
            return False
        
        left, top, right, bottom = rect
        width = right - left
        height = bottom - top

        # Сайдбар стартового экрана занимает ~первые 15% ширины окна.
        # Ограничиваем OCR этой полосой — у левого меню так исчезает
        # неоднозначность с одноимёнными элементами в центральной области
        # (напр. карточка «Шаблоны»), которая ломала семантический клик.
        sidebar_frac = 0.15
        sidebar_w = max(1, int(width * sidebar_frac))

        try:
            from PIL import ImageGrab
            full_shot = ImageGrab.grab()
            sidebar_shot = full_shot.crop((left, top, left + sidebar_w, bottom))
            sidebar_shot.save(screenshot_path)
            ocr_width = sidebar_w
            ocr_height = height
        except ImportError:
            # Fallback: полный скриншот окна, OCR без кропа.
            take_screenshot(screenshot_path)
            ocr_width = width
            ocr_height = height

        # Сначала пробуем точные bbox'ы через Tesseract TSV,
        # потом — старый грубый поиск по распределению строк.
        labels = self._MENU_LABELS.get(menu_name, [menu_name])
        pos = None
        try:
            for lbl in labels:
                pos = find_token_bbox(screenshot_path, lbl)
                if pos:
                    break
            if pos is None:
                ocr_text = ocr_image(screenshot_path)
                for lbl in labels:
                    pos = find_token_position(ocr_text, lbl, ocr_width, ocr_height)
                    if pos:
                        break
            if pos:
                # Клик по найденным координатам
                abs_x = left + pos['center_x']
                abs_y = top + pos['center_y']
                
                import ctypes
                ctypes.windll.user32.SetCursorPos(abs_x, abs_y)
                time.sleep(0.08)
                MOUSEEVENTF_LEFTDOWN = 0x0002
                MOUSEEVENTF_LEFTUP = 0x0004
                ctypes.windll.user32.mouse_event(
                    ctypes.c_ulong(MOUSEEVENTF_LEFTDOWN), ctypes.c_ulong(0),
                    ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_size_t(0),
                )
                ctypes.windll.user32.mouse_event(
                    ctypes.c_ulong(MOUSEEVENTF_LEFTUP), ctypes.c_ulong(0),
                    ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_size_t(0),
                )
                time.sleep(0.5)
                
                # Убрать временный файл
                try:
                    os.remove(screenshot_path)
                except OSError:
                    pass
                
                return True
        except Exception:
            pass
        
        return False

    def _click_via_coordinates(self, pid: int, menu_name: str) -> bool:
        """Координатный клик как крайний резерв (логируется)."""
        # Маппинг имен меню на относительные координаты
        COORD_FALLBACK = {
            "home":      (0.07, 0.175),
            "templates": (0.07, 0.245),
            "local":     (0.07, 0.305),
            "collab":    (0.07, 0.385),
            "settings":  (0.07, 0.865),
            "about":     (0.07, 0.925),
        }
        
        if menu_name not in COORD_FALLBACK:
            return False
        
        rel_x, rel_y = COORD_FALLBACK[menu_name]
        self.click_rel(pid, rel_x, rel_y)
        return True

    def _click_via_cv(self, pid: int, menu_name: str) -> bool:
        """Computer Vision fallback (заглушка для будущего расширения)."""
        # TODO: Интеграция с OpenCV для поиска элемента по шаблону
        logger.debug(f"CV fallback не реализован для '{menu_name}'")
        return False

    # ---------------------------------------------------------------
    # Input simulation (coordinate fallback)
    # ---------------------------------------------------------------

    def click_rel(self, pid: int, rel_x: float, rel_y: float) -> None:
        """Клик по относительной позиции в окне (координатный fallback).

        ВНИМАНИЕ: Этот метод — fallback для крайнего резерва.
        Основной путь — click_menu_item() с семантическим поиском.

        R7 Office использует пользовательскую отрисовку UI (CEF),
        стандартные элементы Accessibility API недоступны для пунктов
        левого меню стартового экрана.
        """
        import ctypes

        hwnd = self._get_hwnd_from_pid(pid)
        if not hwnd:
            return
        rect = self._get_window_rect(hwnd)
        if not rect:
            return
        left, top, right, bottom = rect

        px = int(left + (right - left) * rel_x)
        py = int(top + (bottom - top) * rel_y)

        ctypes.windll.user32.SetCursorPos(px, py)
        time.sleep(0.08)
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        ctypes.windll.user32.mouse_event(
            ctypes.c_ulong(MOUSEEVENTF_LEFTDOWN), ctypes.c_ulong(0),
            ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_size_t(0),
        )
        ctypes.windll.user32.mouse_event(
            ctypes.c_ulong(MOUSEEVENTF_LEFTUP), ctypes.c_ulong(0),
            ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_size_t(0),
        )
        time.sleep(0.5)

    def send_escape(self, pid: int) -> None:
        self.activate_window(pid)
        self._tap_key(0x1B)
        time.sleep(1)

    def paste_text(self, pid: int, text: str) -> None:
        """Вставить текст в активное окно через системный буфер обмена."""
        self.activate_window(pid)
        self._set_clipboard_text(text)
        self._send_ctrl_combo(0x56)  # V
        time.sleep(0.3)

    def align_paragraph_left(self, pid: int) -> None:
        """Выровнять текущий абзац по левому краю (Ctrl+L)."""
        self.activate_window(pid)
        self._send_ctrl_combo(0x4C)  # L
        time.sleep(0.3)

    def undo_action(self, pid: int) -> None:
        """Отменить последнее действие (Ctrl+Z)."""
        self.activate_window(pid)
        self._send_ctrl_combo(0x5A)  # Z
        time.sleep(0.3)

    def redo_action(self, pid: int) -> None:
        """Повторить отменённое действие (Ctrl+Y)."""
        self.activate_window(pid)
        self._send_ctrl_combo(0x59)  # Y
        time.sleep(0.3)

    def save_document(self, pid: int) -> None:
        """Открыть диалог сохранения документа (Ctrl+S)."""
        self.activate_window(pid)
        self._send_ctrl_combo(0x53)  # S
        time.sleep(0.4)

    def confirm_dialog(self, pid: int) -> None:
        """Подтвердить активный диалог клавишей Enter."""
        self.activate_window(pid)
        self._tap_key(0x0D)  # Enter
        time.sleep(0.5)

    def close_current_tab(self, pid: int) -> None:
        """Закрыть текущую вкладку документа (Ctrl+F4)."""
        self.activate_window(pid)
        self._send_ctrl_combo(0x73)  # F4
        time.sleep(0.4)

    def page_down(self, pid: int) -> None:
        """Прокрутить документ на следующую страницу (PageDown)."""
        self.activate_window(pid)
        self._tap_key(0x22)  # VK_NEXT / PageDown
        time.sleep(0.3)

    def click_current_tab_close_button(self, pid: int) -> bool:
        """Кликнуть по `X` активной вкладки через UIAutomation TabBar."""
        ps = f"""
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$root=[System.Windows.Automation.AutomationElement]::RootElement
$pidCond=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::ProcessIdProperty, {pid}
)
$wins=$root.FindAll([System.Windows.Automation.TreeScope]::Children, $pidCond)
if ($wins.Count -eq 0) {{ Write-Output 'NOTFOUND'; exit }}
$w=$wins.Item(0)

$tabCond=New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty,
  'MainWindow.mainPanel.tabWrapper.asc_editors_tabbar'
)
$tab=$w.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $tabCond)
if (-not $tab) {{ Write-Output 'NOTFOUND'; exit }}

$tabs=$tab.FindAll([System.Windows.Automation.TreeScope]::Descendants,
  (New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::TabItem
  )))
if ($tabs.Count -eq 0) {{ Write-Output 'NOTFOUND'; exit }}

$active = $null
for ($i=0; $i -lt $tabs.Count; $i++) {{
  $t = $tabs.Item($i)
  try {{
    $p = $t.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
    if ($p.Current.IsSelected) {{ $active = $t; break }}
  }} catch {{}}
}}
if (-not $active) {{ $active = $tabs.Item(0) }}
if (-not $active) {{ Write-Output 'NOTFOUND'; exit }}

$r = $active.Current.BoundingRectangle
if ($r.Width -le 0 -or $r.Height -le 0) {{ Write-Output 'NOTFOUND'; exit }}

$offset = [Math]::Max(12, [Math]::Min(24, [int]($r.Width * 0.12)))
$x = [int]($r.Right - $offset)
$y = [int]($r.Top + ($r.Height / 2))
Write-Output ($x.ToString() + ',' + $y.ToString())
"""
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
        )
        out = (r.stdout or "").strip()
        if not out or out == "NOTFOUND":
            return False
        try:
            x_str, y_str = out.split(",", 1)
            x, y = int(x_str), int(y_str)
        except Exception:
            return False
        self.activate_window(pid)
        self._click_abs(x, y)
        return True

    # ---------------------------------------------------------------
    # Modal / warning detection (UIAutomation через PowerShell)
    # ---------------------------------------------------------------

    def detect_warning(self, pid: int, timeout_sec: int = 10) -> bool:
        ps = f"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::RootElement
$dl=(Get-Date).AddSeconds({timeout_sec})
while((Get-Date)-lt $dl){{
    $pidCond=New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty,{pid})
    $wins=$root.FindAll([System.Windows.Automation.TreeScope]::Children,$pidCond)
    foreach($w in $wins){{
        $ok_cond=New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty,"OK")
        $ok=$w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$ok_cond)
        if($ok){{ Write-Output "FOUND"; exit }}
    }}
    Start-Sleep -Milliseconds 300
}}
Write-Output "NOTFOUND"
"""
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True,
        )
        return r.stdout.strip() == "FOUND"

    def dismiss_warning(self, pid: int) -> bool:
        ps = f"""
$ErrorActionPreference='SilentlyContinue'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

$root=[System.Windows.Automation.AutomationElement]::RootElement
$pidCond=New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty,{pid})
$dl=(Get-Date).AddSeconds(10)
while((Get-Date)-lt $dl){{
    $wins=$root.FindAll([System.Windows.Automation.TreeScope]::Children,$pidCond)
    foreach($w in $wins){{
        $ok_cond=New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty,"OK")
        $ok=$w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$ok_cond)
        if($ok){{
            try {{
                $ip=$ok.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                $ip.Invoke()
            }} catch {{
                try {{ $ok.SetFocus() }} catch {{}}
                (New-Object -ComObject WScript.Shell).AppActivate({pid})
                [System.Windows.Forms.SendKeys]::SendWait('{{ENTER}}')
            }}
            Start-Sleep -Milliseconds 700
            Write-Output "TRUE"
            exit
        }}
    }}
    Start-Sleep -Milliseconds 250
}}
(New-Object -ComObject WScript.Shell).AppActivate({pid})
[System.Windows.Forms.SendKeys]::SendWait('{{ENTER}}')
Start-Sleep -Milliseconds 700
Write-Output "FALLBACK"
"""
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True,
        )
        return r.stdout.strip() in ("TRUE", "FALLBACK")

    # ---------------------------------------------------------------
    # Process management
    # ---------------------------------------------------------------

    @staticmethod
    def kill_editors() -> None:
        subprocess.run(
            ["taskkill", "/F", "/IM", "editors.exe"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["taskkill", "/F", "/IM", "editors_helper.exe"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1)

    @staticmethod
    def launch_editor(editor_path: str, enable_debug: bool = True) -> None:
        """Запустить редактор с опциональным debug-флагом."""
        if enable_debug:
            # Для устойчивой автоматизации CEF-UI включаем debug-интерфейс.
            # Это открывает локальный CDP-порт, который используют semantic actions.
            subprocess.Popen([editor_path, "--ascdesktop-support-debug-info"])
            return
        subprocess.Popen([editor_path])

    @staticmethod
    def launch_document(
        editor_path: str,
        document_path: str,
        enable_debug: bool = True,
    ) -> None:
        """Открыть документ, передав путь к файлу в аргументах запуска."""
        if enable_debug:
            subprocess.Popen(
                [editor_path, "--ascdesktop-support-debug-info", document_path]
            )
            return
        subprocess.Popen([editor_path, document_path])

    # ---------------------------------------------------------------
    # Keyboard / clipboard helpers
    # ---------------------------------------------------------------

    @staticmethod
    def _tap_key(vk_code: int, pause_sec: float = 0.05) -> None:
        import ctypes

        KEYEVENTF_KEYUP = 0x0002
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        time.sleep(pause_sec)
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)

    @staticmethod
    def _click_abs(px: int, py: int) -> None:
        import ctypes

        ctypes.windll.user32.SetCursorPos(px, py)
        time.sleep(0.08)
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        ctypes.windll.user32.mouse_event(
            ctypes.c_ulong(MOUSEEVENTF_LEFTDOWN), ctypes.c_ulong(0),
            ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_size_t(0),
        )
        ctypes.windll.user32.mouse_event(
            ctypes.c_ulong(MOUSEEVENTF_LEFTUP), ctypes.c_ulong(0),
            ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_size_t(0),
        )
        time.sleep(0.25)

    @staticmethod
    def _send_ctrl_combo(key_vk: int, pause_sec: float = 0.05) -> None:
        import ctypes

        VK_CONTROL = 0x11
        KEYEVENTF_KEYUP = 0x0002

        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        time.sleep(pause_sec)
        ctypes.windll.user32.keybd_event(key_vk, 0, 0, 0)
        time.sleep(pause_sec)
        ctypes.windll.user32.keybd_event(key_vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(pause_sec)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

    @staticmethod
    def _set_clipboard_text(text: str) -> None:
        safe_text = text.replace("'@", "' '@")
        ps = (
            "$clip = @'\n"
            f"{safe_text}\n"
            "'@; Set-Clipboard -Value $clip"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
