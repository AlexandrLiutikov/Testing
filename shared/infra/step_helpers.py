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
from shared.infra.step_results import (
    infer_signal_strength,
    normalize_signal_notes,
    normalize_verification_sources,
)
from shared.infra.verification import bucket_signal_strength


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
    bbox = None
    if activate_driver and pid:
        activate_driver.activate_window(pid)
        try:
            bbox = activate_driver.get_window_rect(pid)
        except Exception:
            bbox = None
    take_screenshot(path, bbox=bbox)
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
        self._verification_sources = []
        self._signal_strength = None
        self._signal_notes = []

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

    def add_verification_source(self, source: str):
        """Добавить источник подтверждения шага (DOM/OCR/GEOMETRY...)."""
        self._verification_sources = normalize_verification_sources(
            [*self._verification_sources, source]
        )

    def add_verification_sources(self, sources):
        """Добавить несколько источников подтверждения шага."""
        self._verification_sources = normalize_verification_sources(
            [*self._verification_sources, *(sources or [])]
        )

    def set_signal_strength(self, signal_strength: str):
        """Явно задать силу сигнала шага."""
        self._signal_strength = signal_strength

    def add_signal_note(self, note: str):
        """Добавить пояснение по качеству сигнала."""
        self._signal_notes = normalize_signal_notes([*self._signal_notes, note])

    def apply_trace(self, trace: Optional[dict]):
        """Применить унифицированный trace из actions/assertions."""
        if not trace:
            return

        fallback_source = trace.get("fallback_source")
        fallback_reason = trace.get("fallback_reason")
        if fallback_source:
            self.set_fallback(str(fallback_source), str(fallback_reason or ""))

        for warning in trace.get("warnings", []) or []:
            self.add_warning(
                code=str(warning.get("code", "TRACE_WARNING")),
                message=str(warning.get("message", "")),
                severity=str(warning.get("severity", "LOW")).upper(),
            )

        sources = trace.get("verification_sources")
        if sources is None and trace.get("verification_source"):
            sources = [trace.get("verification_source")]
        if isinstance(sources, str):
            sources = [sources]
        self.add_verification_sources(sources or [])

        strength = trace.get("signal_strength")
        if strength:
            self.set_signal_strength(str(strength))

        notes = trace.get("signal_notes")
        if isinstance(notes, str):
            notes = [notes]
        for note in notes or []:
            self.add_signal_note(str(note))

    # --- internal ---------------------------------------------------------

    def _record_fail(self, detail: str):
        signal_strength = infer_signal_strength(
            self._verification_sources,
            self._signal_strength,
        )
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
                verification_sources=self._verification_sources,
                signal_strength=signal_strength,
                signal_notes=self._signal_notes,
        )

    def _record_pass(self):
        signal_strength = infer_signal_strength(
            self._verification_sources,
            self._signal_strength,
        )
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
            verification_sources=self._verification_sources,
            signal_strength=signal_strength,
            signal_notes=self._signal_notes,
        )


def apply_action_trace(
    step: StepVerifier,
    trace: Optional[dict],
    action_name: str,
    primary_modes=None,
) -> None:
    """Attach action trace with unified fallback/warning behavior."""
    if not trace:
        return

    step.apply_trace(trace)
    mode = str(trace.get("mode", "")).strip()
    if mode and primary_modes and mode not in set(primary_modes):
        step.add_warning(
            code=f"{action_name.upper()}_MODE",
            severity="LOW",
            message=f"Action выполнился в режиме {mode}, а не в primary-пути.",
        )
    if mode:
        step.add_signal_note(f"action_mode={mode}")


def apply_verification_result(
    step: StepVerifier,
    result,
    context: str = "assertion",
) -> None:
    """Promote VerificationResult to step-level signal metadata."""
    if result is None:
        return

    sources = list(getattr(result, "sources_used", []) or [])
    if sources:
        step.add_verification_sources(sources)

    score = float(getattr(result, "signal_strength", 0.0) or 0.0)
    step.set_signal_strength(bucket_signal_strength(score))
    step.add_signal_note(f"{context}.score={score:.2f}")

    tolerances = list(getattr(result, "tolerance_applied", []) or [])
    for tolerance in tolerances:
        step.add_signal_note(f"{context}.tolerance={tolerance}")

    evidence = dict(getattr(result, "evidence", {}) or {})
    found_tokens = evidence.get("found_tokens", [])
    if isinstance(found_tokens, list) and found_tokens:
        preview = ", ".join(str(token) for token in found_tokens[:4])
        step.add_signal_note(f"{context}.tokens={preview}")
