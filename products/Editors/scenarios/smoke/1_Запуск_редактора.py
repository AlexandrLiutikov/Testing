"""
Автотест: Запуск DesktopEditors.exe, обработка предупреждения, снятие скриншотов, формирование отчётов.
Кейс 1 — Запуск редактора.

Предусловие: редактор не запущен.
Постусловие: редактор остаётся открытым для кейса 2.
"""

import argparse
import os
import sys

# --- Корень проекта в sys.path для импортов shared/ ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PRODUCT_DIR = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PRODUCT_DIR)

from shared.infra.test_runner import CaseRunner
from shared.infra.screenshots import take_screenshot
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

        # --- Предусловие: закрытие ранее запущенных процессов ---
        kill_editors()

        # =================================================================
        # Шаг 1: Запуск редактора
        # ОР: Редактор запущен, появляется блокирующее предупреждение
        #     о том, что приложение не зарегистрировано.
        # =================================================================
        from datetime import datetime
        t0 = datetime.now()
        s1_path = os.path.join(runner.run_dir, "01_warning_visible.png")

        launch_editor(args.editor_path)

        pid = wait_main_proc("editors", 20)
        if not pid:
            take_screenshot(s1_path)
            dur1 = int((datetime.now() - t0).total_seconds() * 1000)
            runner.add_step(
                step_num=1, step_name="Запуск редактора", status="FAIL",
                expected="Редактор запущен, появляется предупреждение о регистрации",
                actual="Окно редактора не появилось в течение 20 секунд",
                screenshot=s1_path,
                failure_severity="CRITICAL",
                failure_area="CORE_FUNCTION",
                failure_detail="Окно редактора не найдено после запуска",
                duration_ms=dur1,
            )
            raise RuntimeError("Окно редактора не найдено после запуска")

        activate_window(pid)

        warn_found = detect_warning_window(pid, timeout_sec=10)
        take_screenshot(s1_path)
        dur1 = int((datetime.now() - t0).total_seconds() * 1000)

        if warn_found:
            runner.add_step(
                step_num=1, step_name="Запуск редактора", status="PASS",
                expected="Редактор запущен, появляется предупреждение о регистрации",
                actual="Редактор запущен, отображается предупреждение «Приложение не зарегистрировано»",
                screenshot=s1_path, duration_ms=dur1,
            )
        else:
            runner.add_step(
                step_num=1, step_name="Запуск редактора", status="FAIL",
                expected="Редактор запущен, появляется предупреждение о регистрации",
                actual="Редактор запущен, но предупреждение о регистрации не появилось",
                screenshot=s1_path,
                failure_severity="HIGH",
                failure_area="CORE_FUNCTION",
                failure_detail="Ожидаемое предупреждение о регистрации не появилось",
                duration_ms=dur1,
            )
            raise RuntimeError("Предупреждение о регистрации не появилось")

        # =================================================================
        # Шаг 2: Закрытие предупреждения (Enter или клик OK)
        # ОР: Предупреждение исчезло, отображается главное окно редактора.
        # =================================================================
        t0 = datetime.now()
        s2_path = os.path.join(runner.run_dir, "02_after_dismiss.png")

        dismiss_warning(pid)

        pid_after = wait_main_proc("editors", 10)
        warning_still = pid_after and detect_warning_window(pid_after, timeout_sec=3)

        if pid_after:
            activate_window(pid_after)
        take_screenshot(s2_path)
        dur2 = int((datetime.now() - t0).total_seconds() * 1000)

        if pid_after and not warning_still:
            runner.add_step(
                step_num=2, step_name="Закрытие предупреждения", status="PASS",
                expected="Предупреждение исчезло, отображается главное окно редактора",
                actual="Предупреждение закрыто, главное окно редактора отображается",
                screenshot=s2_path, duration_ms=dur2,
            )
        else:
            runner.add_step(
                step_num=2, step_name="Закрытие предупреждения", status="FAIL",
                expected="Предупреждение исчезло, отображается главное окно редактора",
                actual="Предупреждение не закрылось или главное окно недоступно",
                screenshot=s2_path,
                failure_severity="HIGH",
                failure_area="CORE_FUNCTION",
                failure_detail="Не удалось закрыть предупреждение о регистрации",
                duration_ms=dur2,
            )


if __name__ == "__main__":
    main()
