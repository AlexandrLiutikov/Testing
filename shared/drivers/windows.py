"""Windows-адаптер Platform Driver Layer (UIAutomation + ctypes)."""

import subprocess
import time
from typing import Optional, Tuple

from shared.drivers.base import BaseDriver


class WindowsDriver(BaseDriver):
    """Реализация драйвера для Windows.

    Использует:
    - WScript.Shell.AppActivate / WMI для активации окон
    - ctypes (user32) для геометрии окон и эмуляции ввода
    - UIAutomationClient (PowerShell) для обнаружения модальных диалогов
    """

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
    # Input simulation
    # ---------------------------------------------------------------

    def click_rel(self, pid: int, rel_x: float, rel_y: float) -> None:
        """Клик по относительной позиции в окне (координатный fallback).

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
        import ctypes

        self.activate_window(pid)
        VK_ESCAPE = 0x1B
        KEYEVENTF_KEYUP = 0x0002
        ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, 0, 0)
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(1)

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
    def launch_editor(editor_path: str) -> None:
        subprocess.Popen([editor_path])
