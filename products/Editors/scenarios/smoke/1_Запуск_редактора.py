"""
Автотест: Запуск DesktopEditors.exe, обработка предупреждения, снятие скриншотов, формирование отчётов.
Кейс 1 — Запуск редактора.

Предусловие: редактор не запущен.
Постусловие: редактор остаётся открытым для кейса 2.

Каждый шаг разрезан на пары: действие → подтверждающая проверка.
"""

import argparse
import os
import sys
from datetime import datetime

# --- Корень проекта в sys.path для импортов shared/ ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PRODUCT_DIR = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

from shared.infra.test_runner import CaseRunner
from shared.infra.screenshots import take_screenshot
from shared.infra.waits import wait_main_proc
from shared.drivers import get_driver

from products.Editors.actions.editor_actions import (
    kill_editors,
    launch_editor,
    dismiss_warning,
)
from products.Editors.assertions.editor_assertions import (
    assert_window_exists,
    assert_warning_visible,
    assert_warning_closed,
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

        # --- Предусловие: закрытие ранее запущенных процессов ---
        kill_editors()

        # =================================================================
        # Шаг 1: Запуск редактора (действие)
        # =================================================================
        t0 = datetime.now()
        launch_editor(args.editor_path)
        dur_launch = int((datetime.now() - t0).total_seconds() * 1000)

        # =================================================================
        # Шаг 1: Проверка — окно редактора появилось (assertion)
        # =================================================================
        t0_assert = datetime.now()
        s1_path = os.path.join(runner.run_dir, "01_editor_window.png")
        pid = wait_main_proc("editors", 20)
        editor_visible = pid is not None
        if editor_visible:
            driver.activate_window(pid)
        take_screenshot(s1_path)
        dur_assert = int((datetime.now() - t0_assert).total_seconds() * 1000)

        if editor_visible:
            runner.add_step(
                step_num=1, step_name="Проверка: окно редактора появилось",
                status="PASS",
                expected="Окно редактора появилось в течение 20 секунд",
                actual="Окно редактора найдено, процесс активен",
                screenshot=s1_path, duration_ms=dur_assert,
            )
        else:
            runner.add_step(
                step_num=1, step_name="Проверка: окно редактора появилось",
                status="FAIL",
                expected="Окно редактора появилось в течение 20 секунд",
                actual="Окно редактора не появилось в течение 20 секунд",
                screenshot=s1_path,
                failure_severity="CRITICAL",
                failure_area="CORE_FUNCTION",
                failure_detail="Окно редактора не найдено после запуска",
                duration_ms=dur_assert,
            )
            raise RuntimeError("Окно редактора не найдено после запуска")

        # =================================================================
        # Шаг 2: Проверка — предупреждение о регистрации видно (assertion)
        # =================================================================
        t0_assert = datetime.now()
        s2_path = os.path.join(runner.run_dir, "02_warning_visible.png")
        warn_found = assert_warning_visible(pid, timeout_sec=10)
        take_screenshot(s2_path)
        dur_warn_assert = int((datetime.now() - t0_assert).total_seconds() * 1000)

        if warn_found:
            runner.add_step(
                step_num=2, step_name="Проверка: предупреждение о регистрации видно",
                status="PASS",
                expected="Появляется предупреждение «Приложение не зарегистрировано»",
                actual="Предупреждение о регистрации отображается",
                screenshot=s2_path, duration_ms=dur_warn_assert,
            )
        else:
            runner.add_step(
                step_num=2, step_name="Проверка: предупреждение о регистрации видно",
                status="FAIL",
                expected="Появляется предупреждение «Приложение не зарегистрировано»",
                actual="Предупреждение о регистрации не появилось",
                screenshot=s2_path,
                failure_severity="HIGH",
                failure_area="CORE_FUNCTION",
                failure_detail="Ожидаемое предупреждение о регистрации не появилось",
                duration_ms=dur_warn_assert,
            )
            raise RuntimeError("Предупреждение о регистрации не появилось")

        # =================================================================
        # Шаг 3: Закрытие предупреждения (действие)
        # =================================================================
        t0 = datetime.now()
        dismiss_warning(pid)
        dur_dismiss = int((datetime.now() - t0).total_seconds() * 1000)

        # =================================================================
        # Шаг 3: Проверка — предупреждение закрыто, главное окно доступно (assertion)
        # =================================================================
        t0_assert = datetime.now()
        s3_path = os.path.join(runner.run_dir, "03_after_dismiss.png")
        pid_after = wait_main_proc("editors", 10)
        warning_still_closed = assert_warning_closed(pid_after, timeout_sec=3)
        if pid_after:
            driver.activate_window(pid_after)
        take_screenshot(s3_path)
        dur_closed_assert = int((datetime.now() - t0_assert).total_seconds() * 1000)

        if pid_after and warning_still_closed:
            runner.add_step(
                step_num=3, step_name="Проверка: предупреждение закрыто, главное окно доступно",
                status="PASS",
                expected="Предупреждение исчезло, отображается главное окно редактора",
                actual="Предупреждение закрыто, главное окно редактора отображается",
                screenshot=s3_path, duration_ms=dur_closed_assert,
            )
        else:
            runner.add_step(
                step_num=3, step_name="Проверка: предупреждение закрыто, главное окно доступно",
                status="FAIL",
                expected="Предупреждение исчезло, отображается главное окно редактора",
                actual="Предупреждение не закрылось или главное окно недоступно",
                screenshot=s3_path,
                failure_severity="HIGH",
                failure_area="CORE_FUNCTION",
                failure_detail="Не удалось закрыть предупреждение о регистрации",
                duration_ms=dur_closed_assert,
            )


if __name__ == "__main__":
    main()
