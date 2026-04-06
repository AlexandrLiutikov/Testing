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
from shared.infra import CaseRunner, StepVerifier, capture_step
from shared.lifecycle import app_lifecycle

# === Продуктовый слой ===
from products.Editors.actions.editor_actions import dismiss_warning
from products.Editors.assertions.editor_assertions import (
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
        pid = app_lifecycle(args.editor_path)

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
            step.check(
                condition=pid is not None,
                pass_msg="Окно редактора найдено, процесс активен",
                fail_msg="Окно редактора не найдено после запуска",
            )

        # =================================================================
        # Шаг 2: Проверка - предупреждение о регистрации видно
        # =================================================================
        s2_path = capture_step(runner.run_dir, 2, "warning_visible",
                               activate_driver=driver, pid=pid)

        warn_found = assert_warning_visible(pid, timeout_sec=10)

        with StepVerifier(
            runner, step_num=2,
            step_name="Проверка: предупреждение о регистрации видно",
            expected="Появляется предупреждение «Приложение не зарегистрировано»",
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(s2_path)
            step.check(
                condition=warn_found,
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
        warning_closed = assert_warning_closed(pid_after, timeout_sec=3)

        with StepVerifier(
            runner, step_num=3,
            step_name="Проверка: предупреждение закрыто, главное окно доступно",
            expected="Предупреждение исчезло, отображается главное окно редактора",
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(s3_path)
            step.check(
                condition=(pid_after is not None and warning_closed),
                pass_msg="Предупреждение закрыто, главное окно редактора отображается",
                fail_msg="Не удалось закрыть предупреждение о регистрации",
            )


if __name__ == "__main__":
    main()
