"""Единый раннер тест-кейсов: артефакты, отчёты, решение о релизе.

Этот модуль объединяет всю инфраструктуру, которая раньше дублировалась
в каждом тест-кейсе:
  - создание директории прогона (run_dir)
  - функция _step() для формирования результатов шага
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project_root() -> str:
    """Корень проекта: shared/infra/test_runner.py → ../../.."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))


# ---------------------------------------------------------------------------
# Step factory
# ---------------------------------------------------------------------------

def make_step(
    case_prefix: str,
    step_num,
    step_name: str,
    status: str,
    expected: str,
    actual: str,
    screenshot: str,
    failure_severity: str = None,
    failure_area: str = None,
    failure_detail: str = None,
    failure_type: str = None,
    duration_ms: int = 0,
    critical_path: bool = None,
) -> dict:
    """Сформировать dict результата шага (единый формат для всех кейсов)."""
    result = {
        "step_id": f"{case_prefix}_step{step_num}",
        "step": step_num,
        "step_name": step_name,
        "status": status,
        "expected": expected,
        "actual": actual,
        "screenshot": screenshot,
        "timestamp": datetime.now().isoformat(),
        "duration_ms": duration_ms,
        "critical_path": critical_path,
    }
    if status == "FAIL":
        result["failure_type"] = failure_type or "TEST_FAIL"
        result["failure_severity"] = failure_severity or "MEDIUM"
        result["failure_area"] = failure_area or "CORE_FUNCTION"
        result["failure_detail"] = failure_detail or actual
    elif status == "BLOCKED":
        result["failure_type"] = "BLOCKED"
        result["failure_severity"] = None
        result["failure_area"] = None
        result["failure_detail"] = failure_detail or actual
    return result


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

    results_data = {
        "environment": env,
        "case_meta": {"case_name": case_name},
        "steps": steps,
        "summary": {
            "total": len(steps),
            "passed": sum(1 for s in steps if s["status"] == "PASS"),
            "failed": sum(1 for s in steps if s["status"] == "FAIL"),
        },
        "release_decision": decision,
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
        """Добавить результат шага."""
        kwargs.setdefault("critical_path",
                          self.case_meta.get("critical_path"))
        step = make_step(self.case_prefix, **kwargs)
        self.steps.append(step)
        return step

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
        print(f"ENVIRONMENT={self.env['os_name']} "
              f"{self.env['architecture']} "
              f"{self.env['screen_resolution']}")
