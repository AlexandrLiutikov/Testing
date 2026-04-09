"""Единый контракт результата шага — StepResult.

Все шаги в проекте собираются одинаково:
  step_id, step_name, status, expected, actual, screenshot, timestamp, duration_ms, critical_path
Для non-PASS добавляются:
  failure_type, failure_severity, failure_area, failure_detail
Дополнительно для прозрачности прогона:
  warnings, fallback_source, fallback_reason

Этот модуль централизует структуру, чтобы она не расползалась по кейсам.
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import List, Optional


@dataclass
class StepResult:
    """Результат выполнения одного шага тест-кейса.

    Атрибуты (обязательные для всех шагов):
        step_id:      Уникальный идентификатор (например "case1_step1")
        step:         Номер шага (int)
        step_name:    Человекочитаемое название шага
        status:       "PASS", "FAIL" или "BLOCKED"
        expected:     Что ожидалось
        actual:       Что произошло фактически
        screenshot:   Путь к скриншоту (может быть пустым)
        timestamp:    ISO-формат времени выполнения
        duration_ms:  Длительность в миллисекундах
        critical_path: Является ли шаг частью критического пути

    Атрибуты (заполняются только для non-PASS):
        failure_type:        Тип сбоя (TEST_FAIL, BLOCKED, TIMEOUT, и т.д.)
        failure_severity:    CRITICAL / HIGH / MEDIUM / LOW
        failure_area:        Область сбоя (CORE_FUNCTION, UI_LAYOUT, и т.д.)
        failure_detail:      Развёрнутое описание проблемы
        warnings:            Непрерывающие предупреждения шага
        fallback_source:     Источник fallback (например HOTKEY, OCR, COORDINATES)
        fallback_reason:     Причина перехода на fallback
    """

    step_id: str
    step: int
    step_name: str
    status: str
    expected: str
    actual: str
    screenshot: str
    timestamp: str
    duration_ms: int
    critical_path: bool

    # Failure-поля (заполняются только для non-PASS)
    failure_type: Optional[str] = None
    failure_severity: Optional[str] = None
    failure_area: Optional[str] = None
    failure_detail: Optional[str] = None
    warnings: List[dict] = field(default_factory=list)
    fallback_source: Optional[str] = None
    fallback_reason: Optional[str] = None

    def to_dict(self) -> dict:
        """Сериализовать в dict для JSON/CSV/отчётов."""
        return asdict(self)

    @classmethod
    def make_pass(
        cls,
        case_prefix: str,
        step_num: int,
        step_name: str,
        expected: str,
        actual: str,
        screenshot: str,
        duration_ms: int,
        critical_path: bool = False,
        warnings: Optional[List[dict]] = None,
        fallback_source: Optional[str] = None,
        fallback_reason: Optional[str] = None,
    ) -> "StepResult":
        """Создать результат успешного шага."""
        return cls(
            step_id=f"{case_prefix}_step{step_num}",
            step=step_num,
            step_name=step_name,
            status="PASS",
            expected=expected,
            actual=actual,
            screenshot=screenshot,
            timestamp=datetime.now().isoformat(),
            duration_ms=duration_ms,
            critical_path=critical_path,
            warnings=list(warnings or []),
            fallback_source=fallback_source,
            fallback_reason=fallback_reason,
        )

    @classmethod
    def make_fail(
        cls,
        case_prefix: str,
        step_num: int,
        step_name: str,
        expected: str,
        actual: str,
        screenshot: str,
        duration_ms: int,
        failure_severity: str = "MEDIUM",
        failure_area: str = "CORE_FUNCTION",
        failure_detail: str = "",
        failure_type: str = "TEST_FAIL",
        critical_path: bool = False,
        warnings: Optional[List[dict]] = None,
        fallback_source: Optional[str] = None,
        fallback_reason: Optional[str] = None,
    ) -> "StepResult":
        """Создать результат неудачного шага."""
        return cls(
            step_id=f"{case_prefix}_step{step_num}",
            step=step_num,
            step_name=step_name,
            status="FAIL",
            expected=expected,
            actual=actual,
            screenshot=screenshot,
            timestamp=datetime.now().isoformat(),
            duration_ms=duration_ms,
            critical_path=critical_path,
            failure_type=failure_type,
            failure_severity=failure_severity,
            failure_area=failure_area,
            failure_detail=failure_detail or actual,
            warnings=list(warnings or []),
            fallback_source=fallback_source,
            fallback_reason=fallback_reason,
        )

    @classmethod
    def make_blocked(
        cls,
        case_prefix: str,
        step_num: int,
        step_name: str,
        expected: str,
        actual: str,
        screenshot: str,
        duration_ms: int,
        failure_detail: str = "",
        critical_path: bool = False,
        warnings: Optional[List[dict]] = None,
        fallback_source: Optional[str] = None,
        fallback_reason: Optional[str] = None,
    ) -> "StepResult":
        """Создать результат заблокированного шага (не выполнился из-за предыдущего сбоя)."""
        return cls(
            step_id=f"{case_prefix}_step{step_num}",
            step=step_num,
            step_name=step_name,
            status="BLOCKED",
            expected=expected,
            actual=actual,
            screenshot=screenshot,
            timestamp=datetime.now().isoformat(),
            duration_ms=duration_ms,
            critical_path=critical_path,
            failure_type="BLOCKED",
            failure_detail=failure_detail or actual,
            warnings=list(warnings or []),
            fallback_source=fallback_source,
            fallback_reason=fallback_reason,
        )
