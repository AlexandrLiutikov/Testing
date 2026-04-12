"""Единый раннер тест-кейсов: артефакты, отчёты, решение о релизе.

Этот модуль объединяет всю инфраструктуру, которая раньше дублировалась
в каждом тест-кейсе:
  - создание директории прогона (run_dir)
  - формирование результатов шага через StepResult
  - блок try/except/finally
  - генерация artefacts (json, csv, md, html)
  - вывод итогов в stdout
"""

import json
import os
import shutil
import sys
from datetime import datetime

from shared.infra.environment import collect_environment, platform_tag
from shared.infra.screenshots import take_screenshot
from shared.infra.decision import build_release_decision
from shared.infra.reporting import generate_html, generate_md, write_csv
from shared.infra.step_results import StepResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project_root() -> str:
    """Корень проекта: shared/infra/test_runner.py → ../../.."""
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Artefact creation
# ---------------------------------------------------------------------------

def _copy_css(run_dir: str) -> None:
    """Скопировать report.css в директорию прогона (если существует)."""
    css_src = os.path.join(_project_root(), "docs", "reporting", "report.css")
    if os.path.isfile(css_src):
        shutil.copy2(css_src, os.path.join(run_dir, "report.css"))


def _write_artefacts(
    run_dir: str,
    case_name: str,
    env: dict,
    steps: list,
    decision: dict,
    start: datetime,
    end: datetime,
    duration_sec: int,
) -> dict:
    """Записать json, csv, md, html отчёты."""
    json_path = os.path.join(run_dir, "results.json")
    csv_path = os.path.join(run_dir, "results.csv")
    md_path = os.path.join(run_dir, "report.md")
    html_path = os.path.join(run_dir, "report.html")

    test_failed = sum(
        1
        for s in steps
        if s["status"] == "FAIL" and s.get("failure_type", "TEST_FAIL") == "TEST_FAIL"
    )
    infra_failed = sum(
        1
        for s in steps
        if s["status"] == "FAIL" and s.get("failure_type") == "INFRA_FAIL"
    )
    blocked = sum(1 for s in steps if s["status"] == "BLOCKED")
    warning_steps = sum(1 for s in steps if s.get("warnings"))
    warnings_total = sum(len(s.get("warnings", [])) for s in steps)
    fallback_steps = sum(1 for s in steps if s.get("fallback_source"))
    signal_strength_counts = {
        "STRONG": sum(1 for s in steps if s.get("signal_strength") == "STRONG"),
        "MEDIUM": sum(1 for s in steps if s.get("signal_strength") == "MEDIUM"),
        "WEAK": sum(1 for s in steps if s.get("signal_strength") == "WEAK"),
    }

    results_data = {
        "environment": env,
        "case_meta": {"case_name": case_name},
        "steps": steps,
        "summary": {
            "total": len(steps),
            "passed": sum(1 for s in steps if s["status"] == "PASS"),
            "failed": test_failed,
            "infra_failed": infra_failed,
            "blocked": blocked,
            "warning_steps": warning_steps,
            "warnings_total": warnings_total,
            "fallback_steps": fallback_steps,
            "signal_strength_counts": signal_strength_counts,
        },
        "release_decision": decision,
        "run_confidence": decision.get("run_confidence"),
        "run_confidence_detail": decision.get("run_confidence_detail"),
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)

    write_csv(csv_path, steps)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_md(case_name, env, steps, decision))

    html = generate_html(case_name, start, end, duration_sec, env, steps, decision)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    _copy_css(run_dir)

    return results_data


# ---------------------------------------------------------------------------
# Main runner — заменяет тело main() в каждом тест-кейсе
# ---------------------------------------------------------------------------

class CaseRunner:
    """Контекст выполнения одного тест-кейса.

    Usage:
        runner = CaseRunner(case_meta, editor_path, output_dir)
        with runner:
            ... шаги ...
            runner.add_step(...)
        # после выхода из with — артефакты записаны, решение сформировано
    """

    def __init__(self, case_meta: dict, editor_path: str,
                 output_dir: str = None):
        self.case_meta = case_meta
        self.editor_path = editor_path
        self.output_dir = output_dir or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        self.case_prefix = f"case{case_meta['case_id']}"
        self.steps: list = []
        self.env: dict = {}
        self.run_dir: str = ""
        self.start: datetime = None
        self.end: datetime = None
        self.duration_sec: int = 0
        self.decision: dict = {}
        self._error_caught: Exception = None

    # --- context manager --------------------------------------------------

    def __enter__(self):
        self.start = datetime.now()
        self.env = collect_environment(self.editor_path)

        ts = self.start.strftime("%Y%m%d_%H%M%S")
        ptag = platform_tag()
        out_root = os.path.join(self.output_dir, "artifacts")
        os.makedirs(out_root, exist_ok=True)
        self.run_dir = os.path.join(out_root, f"{self.case_prefix}_{ptag}_{ts}")
        os.makedirs(self.run_dir, exist_ok=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            self._error_caught = exc_val
            self._handle_error(exc_val)

        self.end = datetime.now()
        self.duration_sec = int((self.end - self.start).total_seconds())
        self.decision = build_release_decision(self.steps, self.case_meta)

        case_name = f"{self.case_meta['case_id']}. {self.case_meta['case_name']}"
        self._write_artefacts(case_name)
        self._print_summary()

        # Не подавляем исключения — пусть поднимаются
        return False  # re-raise если было исключение

    # --- public API -------------------------------------------------------

    def add_step(self, **kwargs) -> dict:
        """Добавить результат шага.

        Поддерживает два режима:
          1. Передать готовый StepResult: runner.add_step(step_result=obj)
          2. Передать параметры для создания StepResult:
             runner.add_step(step_num=1, step_name="...", status="PASS", ...)
        """
        # Если передан готовый StepResult — используем его
        if "step_result" in kwargs:
            step_obj = kwargs["step_result"]
            self.steps.append(step_obj.to_dict())
            return step_obj.to_dict()

        # Иначе создаём StepResult из параметров
        kwargs.setdefault("critical_path", self.case_meta.get("critical_path"))
        status = kwargs.get("status", "PASS")

        if status == "PASS":
            step_obj = StepResult.make_pass(
                case_prefix=self.case_prefix,
                step_num=kwargs["step_num"],
                step_name=kwargs["step_name"],
                expected=kwargs["expected"],
                actual=kwargs["actual"],
                screenshot=kwargs.get("screenshot", ""),
                duration_ms=kwargs.get("duration_ms", 0),
                critical_path=kwargs.get("critical_path", False),
                warnings=kwargs.get("warnings"),
                fallback_source=kwargs.get("fallback_source"),
                fallback_reason=kwargs.get("fallback_reason"),
                verification_sources=kwargs.get("verification_sources"),
                signal_strength=kwargs.get("signal_strength"),
                signal_notes=kwargs.get("signal_notes"),
            )
        elif status == "FAIL":
            step_obj = StepResult.make_fail(
                case_prefix=self.case_prefix,
                step_num=kwargs["step_num"],
                step_name=kwargs["step_name"],
                expected=kwargs["expected"],
                actual=kwargs["actual"],
                screenshot=kwargs.get("screenshot", ""),
                duration_ms=kwargs.get("duration_ms", 0),
                failure_severity=kwargs.get("failure_severity", "MEDIUM"),
                failure_area=kwargs.get("failure_area", "CORE_FUNCTION"),
                failure_detail=kwargs.get("failure_detail", ""),
                failure_type=kwargs.get("failure_type", "TEST_FAIL"),
                critical_path=kwargs.get("critical_path", False),
                warnings=kwargs.get("warnings"),
                fallback_source=kwargs.get("fallback_source"),
                fallback_reason=kwargs.get("fallback_reason"),
                verification_sources=kwargs.get("verification_sources"),
                signal_strength=kwargs.get("signal_strength"),
                signal_notes=kwargs.get("signal_notes"),
            )
        elif status == "BLOCKED":
            step_obj = StepResult.make_blocked(
                case_prefix=self.case_prefix,
                step_num=kwargs["step_num"],
                step_name=kwargs["step_name"],
                expected=kwargs["expected"],
                actual=kwargs["actual"],
                screenshot=kwargs.get("screenshot", ""),
                duration_ms=kwargs.get("duration_ms", 0),
                failure_detail=kwargs.get("failure_detail", ""),
                critical_path=kwargs.get("critical_path", False),
                warnings=kwargs.get("warnings"),
                fallback_source=kwargs.get("fallback_source"),
                fallback_reason=kwargs.get("fallback_reason"),
                verification_sources=kwargs.get("verification_sources"),
                signal_strength=kwargs.get("signal_strength"),
                signal_notes=kwargs.get("signal_notes"),
            )
        else:
            raise ValueError(f"Неподдерживаемый статус шага: {status}")

        self.steps.append(step_obj.to_dict())
        return step_obj.to_dict()

    def fail_if_no_steps_passed(self, error: Exception) -> None:
        """Если ни одного шага не добавлено — добавить FAIL step."""
        if not self.steps:
            err_shot = os.path.join(self.run_dir, "99_error.png")
            take_screenshot(err_shot)
            self.add_step(
                step_num=99,
                step_name="Ошибка выполнения",
                status="FAIL",
                expected="Кейс выполнен без ошибок",
                actual=str(error),
                screenshot=err_shot,
                failure_severity="CRITICAL",
                failure_area="CORE_FUNCTION",
                failure_detail=str(error),
            )

    # --- internal ---------------------------------------------------------

    def _handle_error(self, exc: Exception) -> None:
        if not any(s["status"] == "FAIL" for s in self.steps):
            self.fail_if_no_steps_passed(exc)

    def _write_artefacts(self, case_name: str) -> None:
        _write_artefacts(
            self.run_dir, case_name, self.env, self.steps,
            self.decision, self.start, self.end, self.duration_sec,
        )

    def _print_summary(self) -> None:
        overall = "PASS" if all(
            s["status"] == "PASS" for s in self.steps) else "FAIL"
        print(f"RUN_DIR={self.run_dir}")
        print(f"STATUS={overall}")
        print(f"VERDICT={self.decision['verdict']}")
        print(f"REPORT_HTML={os.path.join(self.run_dir, 'report.html')}")
        print(f"ENVIRONMENT={self.env['os_name']} "
              f"{self.env['architecture']} "
              f"{self.env['screen_resolution']}")
