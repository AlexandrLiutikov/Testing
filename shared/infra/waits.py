"""Централизованные wait / retry (§18 SCRIPT_RULES)."""

import platform
import subprocess
import time
from typing import Callable, Optional

from shared.drivers import get_driver


def wait_until(condition: Callable[[], bool], timeout_sec: float = 10,
               poll_interval: float = 0.3) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(poll_interval)  # polling внутри инфраструктурного метода
    return False


def wait_main_proc(process_name: str = "editors",
                   timeout_sec: float = 20) -> Optional[int]:
    system = platform.system()
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if system == "Windows":
            ps = (
                f"Get-Process {process_name} -ErrorAction SilentlyContinue "
                f"| Where-Object {{ $_.MainWindowHandle -ne 0 }} "
                f"| Sort-Object StartTime -Descending "
                f"| Select-Object -First 1 -ExpandProperty Id"
            )
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True,
            )
            pid_str = r.stdout.strip()
            if pid_str.isdigit():
                return int(pid_str)
        else:
            r = subprocess.run(
                ["pgrep", "-x", process_name],
                capture_output=True, text=True,
            )
            if r.stdout.strip():
                return int(r.stdout.strip().splitlines()[0])
        time.sleep(0.3)  # polling внутри инфраструктурного метода
    return None


def wait_window_stable(pid: int, timeout_sec: float = 3.0) -> bool:
    """Ожидание стабилизации окна после действия.

    Проверяет, что окно всё ещё существует и его геометрия не меняется
    в течение короткого интервала (признак завершения анимации/рендеринга).

    Args:
        pid: PID процесса, окно которого ожидаем.
        timeout_sec: Максимальное время ожидания стабилизации.

    Returns:
        True если окно стабилизировалось, False если исчезло.
    """
    driver = get_driver()
    deadline = time.time() + timeout_sec
    prev_rect = None

    while time.time() < deadline:
        rect = driver.get_window_rect(pid)
        if rect is None:
            return False  # Окно исчезло
        if prev_rect is not None and rect == prev_rect:
            return True  # Геометрия не меняется — стабильно
        prev_rect = rect
        time.sleep(0.2)

    return prev_rect is not None  # Не успело стабилизироваться, но живо
