# -*- coding: utf-8 -*-
"""
Кейс 1 — Запуск редактора.

Предусловие: редактор не запущен.
Постусловие: редактор остаётся открытым для кейса 2.

Каждый шаг разрезан на пары: действие -> подтверждающая проверка.
"""

import argparse
import os
import sys

# --- Корень проекта в sys.path для импортов shared/ ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# _SCRIPT_DIR -> scenarios/smoke
# _SCENARIOS_DIR -> scenarios
# _PRODUCT_DIR -> products/Editors  
# _PROJECT_ROOT -> Testing (корень)
_SCENARIOS_DIR = os.path.dirname(_SCRIPT_DIR)
_PRODUCT_DIR = os.path.dirname(_SCENARIOS_DIR)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_PRODUCT_DIR))
sys.path.insert(0, _PROJECT_ROOT)

# === Reusable инфраструктура ===
from shared.infra import (
    CaseRunner,
    StepVerifier,
    apply_verification_result,
    capture_step,
)
from shared.lifecycle import app_lifecycle

# === Продуктовый слой ===
from products.Editors.actions.editor_actions import dismiss_warning
from products.Editors.assertions.editor_assertions import (
    assert_window_exists,
    assert_warning_visible,
    assert_warning_closed,
)
from shared.drivers import get_driver
from shared.infra.waits import wait_main_proc


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

    with CaseRunner(CASE_META, args.editor_path, args.output_dir) as runner:
        driver = get_driver()

        # ---------------------------------------------------------------
        # Lifecycle: kill -> launch -> detect main window
        # ---------------------------------------------------------------
        try:
            pid, launch_info = app_lifecycle(args.editor_path, return_info=True)
        except Exception as exc:
            err_shot = capture_step(runner.run_dir, 0, "launch_failed")
            runner.add_step(
                step_num=0,
                step_name="Запуск редактора",
                status="FAIL",
                expected="Редактор запускается и отображает главное окно",
                actual="Не удалось запустить редактор ни в debug-, ни в standard-режиме",
                screenshot=err_shot,
                failure_type="INFRA_FAIL",
                failure_severity="MEDIUM",
                failure_area="INFRASTRUCTURE",
                failure_detail=str(exc),
                fallback_source="LAUNCH_NO_DEBUG",
                fallback_reason="Исчерпаны попытки debug->standard запуска редактора.",
                warnings=[{
                    "code": "LAUNCH_DEBUG_FALLBACK_EXHAUSTED",
                    "severity": "MEDIUM",
                    "message": "Запуск редактора не удался после цепочки debug->standard.",
                }],
            )
            return

        # =================================================================
        # Шаг 1: Проверка - окно редактора появилось
        # =================================================================
        s1_path = capture_step(runner.run_dir, 1, "editor_window",
                               activate_driver=driver, pid=pid)

        with StepVerifier(
            runner, step_num=1,
            step_name="Проверка: окно редактора появилось",
            expected="Окно редактора появилось в течение 20 секунд",
            severity="CRITICAL",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(s1_path)
            if launch_info.get("fallback_used"):
                step.set_fallback(
                    launch_info.get("fallback_source", "LAUNCH_NO_DEBUG"),
                    launch_info.get("fallback_reason", ""),
                )
                step.add_warning(
                    code="LAUNCH_DEBUG_FALLBACK",
                    severity="LOW",
                    message=(
                        "Редактор запущен после fallback-цепочки "
                        "debug -> standard (без debug-флага)."
                    ),
                )
            window_result = assert_window_exists(process_name="editors", timeout_sec=3)
            apply_verification_result(step, window_result, context="window_visible")
            step.check(
                condition=bool(window_result),
                pass_msg="Окно редактора найдено, процесс активен",
                fail_msg="Окно редактора не найдено после запуска",
            )

        # =================================================================
        # Шаг 2: Проверка - предупреждение о регистрации видно
        # =================================================================
        s2_path = capture_step(runner.run_dir, 2, "warning_visible",
                               activate_driver=driver, pid=pid)

        warn_result = assert_warning_visible(pid, timeout_sec=10)

        with StepVerifier(
            runner, step_num=2,
            step_name="Проверка: предупреждение о регистрации видно",
            expected="Появляется предупреждение «Приложение не зарегистрировано»",
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(s2_path)
            apply_verification_result(step, warn_result, context="warning_visible")
            step.check(
                condition=bool(warn_result),
                pass_msg="Предупреждение о регистрации отображается",
                fail_msg="Предупреждение о регистрации не появилось",
            )

        # =================================================================
        # Шаг 3: Закрытие предупреждения -> проверка что закрыто
        # =================================================================
        dismiss_warning(pid)

        s3_path = capture_step(runner.run_dir, 3, "after_dismiss",
                               activate_driver=driver, pid=pid)

        pid_after = wait_main_proc("editors", 10)
        warning_closed_result = assert_warning_closed(pid_after, timeout_sec=3)

        with StepVerifier(
            runner, step_num=3,
            step_name="Проверка: предупреждение закрыто, главное окно доступно",
            expected="Предупреждение исчезло, отображается главное окно редактора",
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(s3_path)
            apply_verification_result(step, warning_closed_result, context="warning_closed")
            step.check(
                condition=(pid_after is not None and bool(warning_closed_result)),
                pass_msg="Предупреждение закрыто, главное окно редактора отображается",
                fail_msg="Не удалось закрыть предупреждение о регистрации",
            )


if __name__ == "__main__":
    main()
