"""Infrastructure package — reexports для удобства."""

from shared.infra.waits import wait_until, wait_main_proc, wait_window_stable
from shared.infra.screenshots import take_screenshot
from shared.infra.step_helpers import (
    DurationTimer,
    screenshot_path,
    capture_step,
    StepVerifier,
)
from shared.infra.test_runner import CaseRunner

__all__ = [
    "wait_until",
    "wait_main_proc",
    "wait_window_stable",
    "take_screenshot",
    "DurationTimer",
    "screenshot_path",
    "capture_step",
    "StepVerifier",
    "CaseRunner",
]
