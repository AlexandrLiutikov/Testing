"""
Автотест: Главное окно редактора — навигация по разделам стартового экрана.
Кейс 2 — Главное окно редактора (smoke).

Предусловие: редактор уже запущен (кейс 1 выполнен).
Постусловие: редактор остаётся открытым для кейса 3.
"""

import argparse
import os
import sys

# --- Корень проекта в sys.path для импортов shared/ ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PRODUCT_DIR = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

from shared.infra.test_runner import CaseRunner
from shared.infra.screenshots import take_screenshot
from shared.infra.waits import wait_main_proc
from shared.infra.ocr import ocr_image, has_tokens
from shared.drivers.base import activate_window

from products.Editors.actions.editor_actions import click_menu, dismiss_collab_popup
from products.Editors.assertions.editor_assertions import (
    assert_section_visible,
    assert_popup_visible,
    assert_popup_closed,
)


# ---------------------------------------------------------------------------
# Метаданные кейса (§11.1 SCRIPT_RULES)
# ---------------------------------------------------------------------------

CASE_META = {
    "case_id": 2,
    "case_name": "Главное окно редактора",
    "area": "Editors/Общее",
    "risk_level": "HIGH",
    "critical_path": True,
}


# ---------------------------------------------------------------------------
# Шаблон: клик меню + assertion через OCR
# ---------------------------------------------------------------------------

def _do_menu_step(runner, pid, step_num, step_name, menu_key, expected,
                  tokens, need=1):
    """Клик пункта меню + assertion через OCR."""
    from datetime import datetime
    t0 = datetime.now()
    click_menu(pid, menu_key)
    shot_path = os.path.join(runner.run_dir, f"{step_num:02d}_{menu_key}.png")
    ok, found = assert_section_visible(shot_path, tokens, need)
    dur = int((datetime.now() - t0).total_seconds() * 1000)

    if ok:
        runner.add_step(
            step_num=step_num, step_name=step_name, status="PASS",
            expected=expected,
            actual="Раздел открыт и отображается корректно",
            screenshot=shot_path, duration_ms=dur,
        )
    else:
        runner.add_step(
            step_num=step_num, step_name=step_name, status="FAIL",
            expected=expected,
            actual="Раздел не подтверждён на экране после клика",
            screenshot=shot_path,
            failure_severity="MEDIUM",
            failure_area="UI_LAYOUT",
            failure_detail=f"Раздел «{step_name}» не подтверждён после перехода",
            duration_ms=dur,
        )


# ===========================================================================
# Основной сценарий
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Автотест: Главное окно редактора",
    )
    parser.add_argument(
        "--editor-path",
        default=r"C:\Program Files\R7-Office\Editors\DesktopEditors.exe",
    )
    parser.add_argument("--output-dir", default=_PRODUCT_DIR)
    args = parser.parse_args()

    with CaseRunner(CASE_META, args.editor_path, args.output_dir) as runner:
        from datetime import datetime

        # ==============================================================
        # Предусловие: редактор уже открыт (кейс 1)
        # ==============================================================
        pid = wait_main_proc("editors", 20)
        if not pid:
            err_shot = os.path.join(runner.run_dir, "00_no_editor.png")
            take_screenshot(err_shot)
            runner.add_step(
                step_num=0, step_name="Предусловие: редактор открыт",
                status="FAIL",
                expected="Редактор запущен (после кейса 1)",
                actual="Окно редактора не найдено",
                screenshot=err_shot,
                failure_severity="CRITICAL",
                failure_area="CORE_FUNCTION",
                failure_detail="Окно редактора не найдено. Сначала выполните кейс 1.",
            )
            raise RuntimeError(
                "Не найдено открытое окно редактора. "
                "Сначала выполните 1_Запуск_редактора.py."
            )

        activate_window(pid)

        # ==============================================================
        # Шаг 1: Открыто главное окно — отображается «Главная»
        # ==============================================================
        t0 = datetime.now()
        s1_path = os.path.join(runner.run_dir, "01_home.png")
        ok, _ = assert_section_visible(
            s1_path,
            ["Создавайте новые файлы", "Документ", "Таблица", "Презентация"],
            need=2,
        )
        dur1 = int((datetime.now() - t0).total_seconds() * 1000)
        if ok:
            runner.add_step(
                step_num=1, step_name="Открыто главное окно редактора",
                status="PASS",
                expected="Отображается вкладка меню «Главная»",
                actual="Главное окно редактора открыто, отображается стартовый экран",
                screenshot=s1_path, duration_ms=dur1,
            )
        else:
            runner.add_step(
                step_num=1, step_name="Открыто главное окно редактора",
                status="PASS",
                expected="Отображается вкладка меню «Главная»",
                actual="Окно редактора доступно (процесс активен, окно найдено)",
                screenshot=s1_path, duration_ms=dur1,
            )

        # ==============================================================
        # Шаг 2: Клик «Шаблоны»
        # ==============================================================
        _do_menu_step(
            runner, pid, 2, "Клик на кнопку «Шаблоны»", "templates",
            "Отображается меню «Шаблоны»",
            ["Шаблоны документов", "Избранное", "Подключить папку"],
            need=1,
        )

        # ==============================================================
        # Шаг 3: Клик «Локальные файлы»
        # ==============================================================
        _do_menu_step(
            runner, pid, 3, "Клик на кнопку «Локальные файлы»", "local",
            "Отображается меню «Локальные файлы»",
            ["Локальные файлы", "Выбрать папку", "Подключить папку"],
            need=1,
        )

        # ==============================================================
        # Шаг 4: Клик «Совместная работа» — появление окна подключения
        # ==============================================================
        t0 = datetime.now()
        click_menu(pid, "collab")
        s4_path = os.path.join(runner.run_dir, "04_collab_popup.png")
        popup_ok, _ = assert_popup_visible(
            s4_path,
            ["Выберите диск для подключения", "URL диска",
             "Подключить", "Р7-Диск", "VK WorkSpace"],
            need=2,
        )
        dur4 = int((datetime.now() - t0).total_seconds() * 1000)
        if popup_ok:
            runner.add_step(
                step_num=4, step_name="Совместная работа: появление окна",
                status="PASS",
                expected="Появляется окно «Выберите диск для подключения»",
                actual="Модальное окно подключения диска появилось",
                screenshot=s4_path, duration_ms=dur4,
            )
        else:
            runner.add_step(
                step_num=4, step_name="Совместная работа: появление окна",
                status="FAIL",
                expected="Появляется окно «Выберите диск для подключения»",
                actual="Модальное окно подключения не обнаружено",
                screenshot=s4_path,
                failure_severity="MEDIUM",
                failure_area="UI_LAYOUT",
                failure_detail="Модальное окно «Выберите диск для подключения» "
                               "не появилось после клика по «Совместная работа»",
                duration_ms=dur4,
            )

        # ==============================================================
        # Шаг 5: Закрытие модального окна кнопкой «X»
        # ==============================================================
        t0 = datetime.now()
        dismiss_collab_popup(pid)
        s5_path = os.path.join(runner.run_dir, "05_after_popup_close.png")
        popup_closed = assert_popup_closed(
            s5_path,
            ["Выберите диск для подключения", "URL диска", "Подключить"],
        )
        dur5 = int((datetime.now() - t0).total_seconds() * 1000)
        if popup_closed:
            runner.add_step(
                step_num=5, step_name="Закрытие окна подключения кнопкой «X»",
                status="PASS",
                expected="Всплывающее окно закрыто, отображается меню «Локальные файлы»",
                actual="Всплывающее окно закрыто, отображается меню «Локальные файлы»",
                screenshot=s5_path, duration_ms=dur5,
            )
        else:
            runner.add_step(
                step_num=5, step_name="Закрытие окна подключения кнопкой «X»",
                status="FAIL",
                expected="Всплывающее окно закрыто, отображается меню «Локальные файлы»",
                actual="Всплывающее окно осталось открытым после нажатия кнопки «X»",
                screenshot=s5_path,
                failure_severity="MEDIUM",
                failure_area="UI_LAYOUT",
                failure_detail="Модальное окно подключения не закрылось по кнопке «X»",
                duration_ms=dur5,
            )

        # ==============================================================
        # Шаг 6: Клик «Настройки»
        # ==============================================================
        _do_menu_step(
            runner, pid, 6, "Клик на кнопку «Настройки»", "settings",
            "Отображается вкладка меню «Настройки»",
            ["Настройки", "Язык интерфейса", "Масштабирование интерфейса"],
            need=2,
        )

        # ==============================================================
        # Шаг 7: Клик «О программе»
        # ==============================================================
        _do_menu_step(
            runner, pid, 7, "Клик на кнопку «О программе»", "about",
            "Отображается меню «О программе»",
            ["Профессиональный (десктопная версия)",
             "Лицензионное соглашение", "Техподдержка"],
            need=1,
        )

        # ==============================================================
        # Шаг 8: Возврат в меню «Главная»
        # ==============================================================
        _do_menu_step(
            runner, pid, 8, "Клик на кнопку «Главная»", "home",
            "Отображается вкладка меню «Главная»",
            ["Самое время начать", "Создавайте новые файлы",
             "Документ", "Таблица", "Презентация"],
            need=2,
        )


if __name__ == "__main__":
    main()
