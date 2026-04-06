"""
Автотест: Запуск DesktopEditors.exe, обработка предупреждения, снятие скриншотов, формирование отчётов.
Кейс 1 — Запуск редактора.

Предусловие: редактор не запущен.
Постусловие: редактор остаётся открытым для кейса 2.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime

# --- Корень проекта в sys.path для импортов shared/ ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PRODUCT_DIR = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_PRODUCT_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from shared.infra.environment import collect_environment, platform_tag
from shared.infra.screenshots import take_screenshot
from shared.infra.decision import build_release_decision
from shared.infra.reporting import generate_html, generate_md, write_csv
from shared.infra.waits import wait_main_proc
from shared.drivers.base import activate_window

from products.Editors.actions.editor_actions import (
    kill_editors,
    launch_editor,
    detect_warning_window,
    dismiss_warning,
)


# ---------------------------------------------------------------------------
# Метаданные кейса (§11.1 SCRIPT_RULES)
# ---------------------------------------------------------------------------

CASE_META = {
    "case_id": 1,
    "case_name": "Запуск редактора",
    "area": "Editors/Общее",
    "risk_level": "HIGH",
    "critical_path": True,
}


# ---------------------------------------------------------------------------
# Вспомогательная функция для формирования step_result (§15 SCRIPT_RULES)
# ---------------------------------------------------------------------------

def _step(step_num, step_name, status, expected, actual, screenshot,
          failure_severity=None, failure_area=None, failure_detail=None,
          failure_type=None, duration_ms=0):
    result = {
        "step_id": f"case1_step{step_num}",
        "step": step_num,
        "step_name": step_name,
        "status": status,
        "expected": expected,
        "actual": actual,
        "screenshot": screenshot,
        "timestamp": datetime.now().isoformat(),
        "duration_ms": duration_ms,
        "critical_path": CASE_META["critical_path"],
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


# ===========================================================================
# Основной сценарий
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Автотест: Запуск редактора")
    parser.add_argument(
        "--editor-path",
        default=r"C:\Program Files\R7-Office\Editors\DesktopEditors.exe",
    )
    parser.add_argument("--output-dir", default=_PRODUCT_DIR)
    args = parser.parse_args()

    env = collect_environment(args.editor_path)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ptag = platform_tag()
    out_root = os.path.join(args.output_dir, "artifacts")
    os.makedirs(out_root, exist_ok=True)
    run_dir = os.path.join(out_root, f"case1_{ptag}_{ts}")
    os.makedirs(run_dir, exist_ok=True)

    steps = []
    start = datetime.now()

    try:
        # --- Предусловие: закрытие ранее запущенных процессов ---
        kill_editors()

        # =================================================================
        # Шаг 1: Запуск редактора
        # ОР: Редактор запущен, появляется блокирующее предупреждение
        #     о том, что приложение не зарегистрировано.
        # =================================================================
        t0 = datetime.now()
        s1_path = os.path.join(run_dir, "01_warning_visible.png")

        launch_editor(args.editor_path)

        pid = wait_main_proc("editors", 20)
        if not pid:
            take_screenshot(s1_path)
            dur1 = int((datetime.now() - t0).total_seconds() * 1000)
            steps.append(_step(
                1, "Запуск редактора", "FAIL",
                "Редактор запущен, появляется предупреждение о регистрации",
                "Окно редактора не появилось в течение 20 секунд",
                s1_path,
                failure_severity="CRITICAL",
                failure_area="CORE_FUNCTION",
                failure_detail="Окно редактора не появилось после запуска",
                duration_ms=dur1,
            ))
            raise RuntimeError("Окно редактора не найдено после запуска")

        activate_window(pid)

        # Assertion: ожидаем появление предупреждения (диалог с кнопкой OK)
        warn_found = detect_warning_window(pid, timeout_sec=10)
        take_screenshot(s1_path)
        dur1 = int((datetime.now() - t0).total_seconds() * 1000)

        if warn_found:
            steps.append(_step(
                1, "Запуск редактора", "PASS",
                "Редактор запущен, появляется предупреждение о регистрации",
                "Редактор запущен, отображается предупреждение «Приложение не зарегистрировано»",
                s1_path, duration_ms=dur1,
            ))
        else:
            steps.append(_step(
                1, "Запуск редактора", "FAIL",
                "Редактор запущен, появляется предупреждение о регистрации",
                "Редактор запущен, но предупреждение о регистрации не появилось",
                s1_path,
                failure_severity="HIGH",
                failure_area="CORE_FUNCTION",
                failure_detail="Ожидаемое предупреждение о регистрации не появилось",
                duration_ms=dur1,
            ))
            raise RuntimeError("Предупреждение о регистрации не появилось")

        # =================================================================
        # Шаг 2: Закрытие предупреждения (Enter или клик OK)
        # ОР: Предупреждение исчезло, отображается главное окно редактора.
        # =================================================================
        t0 = datetime.now()
        s2_path = os.path.join(run_dir, "02_after_dismiss.png")

        dismiss_warning(pid)

        pid_after = wait_main_proc("editors", 10)
        # Assertion: предупреждение исчезло и главное окно доступно
        warning_still = pid_after and detect_warning_window(pid_after, timeout_sec=3)

        if pid_after:
            activate_window(pid_after)
        take_screenshot(s2_path)
        dur2 = int((datetime.now() - t0).total_seconds() * 1000)

        if pid_after and not warning_still:
            steps.append(_step(
                2, "Закрытие предупреждения", "PASS",
                "Предупреждение исчезло, отображается главное окно редактора",
                "Предупреждение закрыто, главное окно редактора отображается",
                s2_path, duration_ms=dur2,
            ))
        else:
            steps.append(_step(
                2, "Закрытие предупреждения", "FAIL",
                "Предупреждение исчезло, отображается главное окно редактора",
                "Предупреждение не закрылось или главное окно недоступно",
                s2_path,
                failure_severity="HIGH",
                failure_area="CORE_FUNCTION",
                failure_detail="Не удалось закрыть предупреждение о регистрации",
                duration_ms=dur2,
            ))

    except Exception as e:
        if not any(s["status"] == "FAIL" for s in steps):
            err_shot = os.path.join(run_dir, "99_error.png")
            take_screenshot(err_shot)
            steps.append(_step(
                99, "Ошибка выполнения", "FAIL",
                "Кейс выполнен без ошибок", str(e), err_shot,
                failure_severity="CRITICAL",
                failure_area="CORE_FUNCTION",
                failure_detail=str(e),
            ))

    finally:
        # Постусловие: редактор остаётся открытым для кейса 2 (§10.1)
        pass

    end = datetime.now()
    dur = int((end - start).total_seconds())

    decision = build_release_decision(steps, CASE_META)

    # --- Формирование артефактов ---
    json_path = os.path.join(run_dir, "results.json")
    csv_path = os.path.join(run_dir, "results.csv")
    md_path = os.path.join(run_dir, "report.md")
    html_path = os.path.join(run_dir, "report.html")

    case_name = f"{CASE_META['case_id']}. {CASE_META['case_name']}"

    results_data = {
        "environment": env,
        "case_meta": CASE_META,
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

    html = generate_html(case_name, start, end, dur, env, steps, decision)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    css_src = os.path.join(_PROJECT_ROOT, "docs", "reporting", "report.css")
    if os.path.isfile(css_src):
        shutil.copy2(css_src, os.path.join(run_dir, "report.css"))

    overall_status = "PASS" if all(s["status"] == "PASS" for s in steps) else "FAIL"
    print(f"RUN_DIR={run_dir}")
    print(f"STATUS={overall_status}")
    print(f"VERDICT={decision['verdict']}")
    print(f"ENVIRONMENT={env['os_name']} {env['architecture']} {env['screen_resolution']}")
    print(f"REPORT_HTML={html_path}")


if __name__ == "__main__":
    main()
