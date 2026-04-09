"""Хелперы для оформления шагов тест-кейса.

Убирают дублирующийся boilerplate из каждого шага:
  - timing (datetime.now → duration_ms)
  - screenshot path construction
  - PASS/FAIL ветвление
  - add_step вызов
"""

import os
import time
from typing import Optional

from shared.infra.screenshots import take_screenshot


class DurationTimer:
    """Простой таймер для замера длительности шага.

    Usage:
        timer = DurationTimer()
        ... действие ...
        ms = timer.elapsed_ms()
    """

    def __init__(self):
        self._start = time.monotonic()

    def elapsed_ms(self) -> int:
        """Вернуть elapsed time в миллисекундах."""
        return int((time.monotonic() - self._start) * 1000)


def screenshot_path(run_dir: str, step_num: int, name: str) -> str:
    """Сформировать путь к скриншоту для шага.

    Формат: ``{run_dir}/{step_num:02d}_{name}.png``

    Args:
        run_dir: Директория прогона (runner.run_dir).
        step_num: Номер шага.
        name: Краткое имя (латиница, snake_case).

    Returns:
        Полный путь к файлу скриншота.
    """
    return os.path.join(run_dir, f"{step_num:02d}_{name}.png")


def capture_step(run_dir: str, step_num: int, name: str,
                 activate_driver=None, pid: Optional[int] = None) -> str:
    """Сделать скриншот шага с активацией окна.

    Комбинирует: activate_window (если pid передан) + take_screenshot.

    Args:
        run_dir: Директория прогона.
        step_num: Номер шага.
        name: Краткое имя скриншота.
        activate_driver: Экземпляр драйвера для activate_window.
        pid: PID окна для активации перед скриншотом.

    Returns:
        Путь к сохранённому скриншоту.
    """
    path = screenshot_path(run_dir, step_num, name)
    if activate_driver and pid:
        activate_driver.activate_window(pid)
    take_screenshot(path)
    return path


class StepVerifier:
    """Контекст выполнения одного шага с авто-оформлением результата.

    Значительно сокращает boilerplate в тестах: вместо if/else на 20+ строк
    — одна цепочка вызовов.

    Usage:
        with StepVerifier(runner, step_num=1, name="окно редактора появилось") as step:
            step.check(pid is not None, "Окно редактора найдено")
            step.screenshot(path)

        # Если check() не пройдён — шаг автоматически оформлен как FAIL
        # Если check() пройдён — шаг оформлен как PASS
    """

    def __init__(self, runner, step_num: int, step_name: str,
                 expected: str = "",
                 severity: str = "CRITICAL",
                 failure_area: str = "CORE_FUNCTION"):
        self._runner = runner
        self._step_num = step_num
        self._step_name = step_name
        self._expected = expected
        self._severity = severity
        self._failure_area = failure_area
        self._passed = False
        self._actual_pass = ""
        self._actual_fail = ""
        self._screenshot = ""
        self._timer = DurationTimer()
        self._warnings = []
        self._fallback_source = None
        self._fallback_reason = None

    # --- context manager --------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            # Исключение внутри шага — авто-Fail
            self._record_fail(str(exc_val))
            return False  # re-raise

        if self._passed:
            self._record_pass()
        else:
            # check() не вызывался или вернул False
            self._record_fail(self._actual_fail or "Проверка не пройдена")

        return False  # не подавляем исключения

    # --- public API -------------------------------------------------------

    def check(self, condition: bool, pass_msg: str = "", fail_msg: str = ""):
        """Зафиксировать результат проверки.

        Args:
            condition: Результат проверки.
            pass_msg: Описание при успехе (факт).
            fail_msg: Описание при провале (факт).
        """
        self._passed = condition
        if condition:
            self._actual_pass = pass_msg
        else:
            self._actual_fail = fail_msg or pass_msg

    def screenshot(self, path: str):
        """Прикрепить скриншот к шагу."""
        self._screenshot = path

    def add_warning(self, code: str, message: str, severity: str = "LOW"):
        """Добавить предупреждение шага без перевода шага в FAIL."""
        self._warnings.append({
            "code": code,
            "severity": severity,
            "message": message,
        })

    def set_fallback(self, source: str, reason: str):
        """Зафиксировать факт использования fallback-пути."""
        self._fallback_source = source
        self._fallback_reason = reason

    # --- internal ---------------------------------------------------------

    def _record_fail(self, detail: str):
        self._runner.add_step(
            step_num=self._step_num,
            step_name=self._step_name,
            status="FAIL",
            expected=self._expected,
            actual=detail,
            screenshot=self._screenshot,
            duration_ms=self._timer.elapsed_ms(),
                failure_severity=self._severity,
                failure_area=self._failure_area,
                failure_detail=detail,
                warnings=self._warnings,
                fallback_source=self._fallback_source,
                fallback_reason=self._fallback_reason,
        )

    def _record_pass(self):
        self._runner.add_step(
            step_num=self._step_num,
            step_name=self._step_name,
            status="PASS",
            expected=self._expected,
            actual=self._actual_pass,
            screenshot=self._screenshot,
            duration_ms=self._timer.elapsed_ms(),
            warnings=self._warnings,
            fallback_source=self._fallback_source,
            fallback_reason=self._fallback_reason,
        )
