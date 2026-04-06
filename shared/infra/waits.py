"""Централизованные wait / retry (§18 SCRIPT_RULES)."""

import platform
import subprocess
import time
from typing import Callable, Optional


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
