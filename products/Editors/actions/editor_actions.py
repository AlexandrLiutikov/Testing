"""Semantic actions для Editors — продуктовый слой (§16, §17 SCRIPT_RULES)."""

import platform
import subprocess
import time

from shared.drivers.base import activate_window, click_rel, send_escape


MENU_POINTS = {
    "home":      (0.07, 0.175),
    "templates": (0.07, 0.245),
    "local":     (0.07, 0.305),
    "collab":    (0.07, 0.385),
    "settings":  (0.07, 0.865),
    "about":     (0.07, 0.925),
}

# Координата кнопки «X» на модальном окне подключения дисков (по центру-вправо)
COLLAB_CLOSE_X = (0.64, 0.26)


def click_menu(pid: int, menu_key: str):
    """Активировать окно и кликнуть по пункту левого меню стартового экрана."""
    if menu_key not in MENU_POINTS:
        raise ValueError(f"Неизвестный пункт меню: {menu_key}")
    activate_window(pid)
    rel_x, rel_y = MENU_POINTS[menu_key]
    click_rel(pid, rel_x, rel_y)
    time.sleep(0.6)  # ожидание перехода (Semantic Actions Layer)


def dismiss_collab_popup(pid: int):
    """Закрыть модальное окно подключения дисков клавишей Esc."""
    send_escape(pid)


# ---------------------------------------------------------------------------
# Управление процессами редактора
# ---------------------------------------------------------------------------

def _is_windows():
    return platform.system() == "Windows"


def kill_editors():
    """Завершить все процессы editors/editors_helper."""
    if _is_windows():
        subprocess.run(["taskkill", "/F", "/IM", "editors.exe"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["taskkill", "/F", "/IM", "editors_helper.exe"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run(["pkill", "-f", "editors"], stderr=subprocess.DEVNULL)
    time.sleep(1)  # ожидание завершения процессов (Platform Driver Layer)


def launch_editor(editor_path: str):
    """Запустить редактор."""
    subprocess.Popen([editor_path])


# ---------------------------------------------------------------------------
# Обработка модальных окон предупреждения (§10.6)
# ---------------------------------------------------------------------------

def detect_warning_window(pid: int, timeout_sec: int = 10) -> bool:
    """Проверить наличие модального предупреждения (диалог с кнопкой OK)."""
    if not _is_windows():
        return False
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
        $okCond=New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty,"OK")
        $ok=$w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$okCond)
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


def dismiss_warning(pid: int) -> bool:
    """Закрыть предупреждение: Invoke кнопки OK, fallback — Enter."""
    if not _is_windows():
        return False
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
        $okCond=New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty,"OK")
        $ok=$w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$okCond)
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
# fallback: отправить Enter
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
