"""
Автотест: Главное окно редактора — навигация по разделам стартового экрана.
Кейс 2 — Главное окно редактора (smoke).

Предусловие: редактор уже запущен (кейс 1 выполнен).
Постусловие: редактор остаётся открытым для кейса 3.

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
from shared.infra.ocr import ocr_image, has_tokens
from shared.drivers import get_driver

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
        driver = get_driver()

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

        driver.activate_window(pid)

        # ==============================================================
        # Шаг 1: Проверка — главное окно отображается (assertion only)
        # ==============================================================
        t0 = datetime.now()
        s1_path = os.path.join(runner.run_dir, "01_home.png")
        ok, _ = assert_section_visible(
            s1_path,
            ["Создавайте новые файлы", "Документ", "Табблица", "Презентация"],
            need=2,
        )
        dur1 = int((datetime.now() - t0).total_seconds() * 1000)
        if ok:
            runner.add_step(
                step_num=1, step_name="Проверка: главное окно — «Главная» видна",
                status="PASS",
                expected="Отображается вкладка меню «Главная»",
                actual="Главное окно редактора открыто, отображается стартовый экран",
                screenshot=s1_path, duration_ms=dur1,
            )
        else:
            runner.add_step(
                step_num=1, step_name="Проверка: главное окно — «Главная» видна",
                status="FAIL",
                expected="Отображается вкладка меню «Главная»",
                actual="Стартовый экран не подтверждён по OCR-токенам",
                screenshot=s1_path,
                failure_severity="MEDIUM",
                failure_area="UI_LAYOUT",
                failure_detail="Токены «Главная» не обнаружены на стартовом экране",
                duration_ms=dur1,
            )

        # ==============================================================
        # Шаг 2: Клик «Шаблоны» (action)
        # ==============================================================
        click_menu(pid, "templates")

        # Шаг 2: Проверка — раздел «Шаблоны» открыт (assertion)
        t0 = datetime.now()
        s2_path = os.path.join(runner.run_dir, "02_templates.png")
        ok, _ = assert_section_visible(
            s2_path,
            ["Шаблоны документов", "Избранное", "Подключить папку"],
            need=1,
        )
        dur2 = int((datetime.now() - t0).total_seconds() * 1000)
        if ok:
            runner.add_step(
                step_num=2, step_name="Проверка: раздел «Шаблоны» открыт",
                status="PASS",
                expected="Отображается меню «Шаблоны»",
                actual="Раздел «Шаблоны» открыт и отображается корректно",
                screenshot=s2_path, duration_ms=dur2,
            )
        else:
            runner.add_step(
                step_num=2, step_name="Проверка: раздел «Шаблоны» открыт",
                status="FAIL",
                expected="Отображается меню «Шаблоны»",
                actual="Раздел «Шаблоны» не подтверждён на экране после клика",
                screenshot=s2_path,
                failure_severity="MEDIUM",
                failure_area="UI_LAYOUT",
                failure_detail="Токены «Шаблоны» не обнаружены после перехода",
                duration_ms=dur2,
            )

        # ==============================================================
        # Шаг 3: Клик «Локальные файлы» (action)
        # ==============================================================
        click_menu(pid, "local")

        # Шаг 3: Проверка — раздел «Локальные файлы» открыт (assertion)
        t0 = datetime.now()
        s3_path = os.path.join(runner.run_dir, "03_local.png")
        ok, _ = assert_section_visible(
            s3_path,
            ["Локальные файлы", "Выбрать папку", "Подключить папку"],
            need=1,
        )
        dur3 = int((datetime.now() - t0).total_seconds() * 1000)
        if ok:
            runner.add_step(
                step_num=3, step_name="Проверка: раздел «Локальные файлы» открыт",
                status="PASS",
                expected="Отображается меню «Локальные файлы»",
                actual="Раздел «Локальные файлы» открыт и отображается корректно",
                screenshot=s3_path, duration_ms=dur3,
            )
        else:
            runner.add_step(
                step_num=3, step_name="Проверка: раздел «Локальные файлы» открыт",
                status="FAIL",
                expected="Отображается меню «Локальные файлы»",
                actual="Раздел «Локальные файлы» не подтверждён на экране после клика",
                screenshot=s3_path,
                failure_severity="MEDIUM",
                failure_area="UI_LAYOUT",
                failure_detail="Токены «Локальные файлы» не обнаружены после перехода",
                duration_ms=dur3,
            )

        # ==============================================================
        # Шаг 4: Клик «Совместная работа» (action)
        # ==============================================================
        click_menu(pid, "collab")

        # Шаг 4: Проверка — окно подключения появилось (assertion)
        t0 = datetime.now()
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
                step_num=4, step_name="Проверка: окно подключения появилось",
                status="PASS",
                expected="Появляется окно «Выберите диск для подключения»",
                actual="Модальное окно подключения диска появилось",
                screenshot=s4_path, duration_ms=dur4,
            )
        else:
            runner.add_step(
                step_num=4, step_name="Проверка: окно подключения появилось",
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
        # Шаг 5: Закрытие модального окна кнопкой «X» (action)
        # ==============================================================
        dismiss_collab_popup(pid)

        # Шаг 5: Проверка — окно подключения закрыто (assertion)
        t0 = datetime.now()
        s5_path = os.path.join(runner.run_dir, "05_after_popup_close.png")
        popup_closed = assert_popup_closed(
            s5_path,
            ["Выберите диск для подключения", "URL диска", "Подключить"],
        )
        dur5 = int((datetime.now() - t0).total_seconds() * 1000)
        if popup_closed:
            runner.add_step(
                step_num=5, step_name="Проверка: окно подключения закрыто",
                status="PASS",
                expected="Всплывающее окно закрыто, отображается меню «Локальные файлы»",
                actual="Всплывающее окно закрыто, отображается меню «Локальные файлы»",
                screenshot=s5_path, duration_ms=dur5,
            )
        else:
            runner.add_step(
                step_num=5, step_name="Проверка: окно подключения закрыто",
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
        # Шаг 6: Клик «Настройки» (action)
        # ==============================================================
        click_menu(pid, "settings")

        # Шаг 6: Проверка — раздел «Настройки» открыт (assertion)
        t0 = datetime.now()
        s6_path = os.path.join(runner.run_dir, "06_settings.png")
        ok, _ = assert_section_visible(
            s6_path,
            ["Настройки", "Язык интерфейса", "Масштабирование интерфейса"],
            need=2,
        )
        dur6 = int((datetime.now() - t0).total_seconds() * 1000)
        if ok:
            runner.add_step(
                step_num=6, step_name="Проверка: раздел «Настройки» открыт",
                status="PASS",
                expected="Отображается вкладка меню «Настройки»",
                actual="Раздел «Настройки» открыт и отображается корректно",
                screenshot=s6_path, duration_ms=dur6,
            )
        else:
            runner.add_step(
                step_num=6, step_name="Проверка: раздел «Настройки» открыт",
                status="FAIL",
                expected="Отображается вкладка меню «Настройки»",
                actual="Раздел «Настройки» не подтверждён на экране после клика",
                screenshot=s6_path,
                failure_severity="MEDIUM",
                failure_area="UI_LAYOUT",
                failure_detail="Токены «Настройки» не обнаружены после перехода",
                duration_ms=dur6,
            )

        # ==============================================================
        # Шаг 7: Клик «О программе» (action)
        # ==============================================================
        click_menu(pid, "about")

        # Шаг 7: Проверка — раздел «О программе» открыт (assertion)
        t0 = datetime.now()
        s7_path = os.path.join(runner.run_dir, "07_about.png")
        ok, _ = assert_section_visible(
            s7_path,
            ["Профессиональный (десктопная версия)",
             "Лицензионное соглашение", "Техподдержка"],
            need=1,
        )
        dur7 = int((datetime.now() - t0).total_seconds() * 1000)
        if ok:
            runner.add_step(
                step_num=7, step_name="Проверка: раздел «О программе» открыт",
                status="PASS",
                expected="Отображается меню «О программе»",
                actual="Раздел «О программе» открыт и отображается корректно",
                screenshot=s7_path, duration_ms=dur7,
            )
        else:
            runner.add_step(
                step_num=7, step_name="Проверка: раздел «О программе» открыт",
                status="FAIL",
                expected="Отображается меню «О программе»",
                actual="Раздел «О программе» не подтверждён на экране после клика",
                screenshot=s7_path,
                failure_severity="MEDIUM",
                failure_area="UI_LAYOUT",
                failure_detail="Токены «О программе» не обнаружены после перехода",
                duration_ms=dur7,
            )

        # ==============================================================
        # Шаг 8: Клик «Главная» (action)
        # ==============================================================
        click_menu(pid, "home")

        # Шаг 8: Проверка — возврат на «Главная» (assertion)
        t0 = datetime.now()
        s8_path = os.path.join(runner.run_dir, "08_home_return.png")
        ok, _ = assert_section_visible(
            s8_path,
            ["Самое время начать", "Создавайте новые файлы",
             "Документ", "Табблица", "Презентация"],
            need=2,
        )
        dur8 = int((datetime.now() - t0).total_seconds() * 1000)
        if ok:
            runner.add_step(
                step_num=8, step_name="Проверка: возврат на «Главная»",
                status="PASS",
                expected="Отображается вкладка меню «Главная»",
                actual="Возврат на «Главная» выполнен, стартовый экран отображается",
                screenshot=s8_path, duration_ms=dur8,
            )
        else:
            runner.add_step(
                step_num=8, step_name="Проверка: возврат на «Главная»",
                status="FAIL",
                expected="Отображается вкладка меню «Главная»",
                actual="Возврат на «Главная» не подтверждён по OCR-токенам",
                screenshot=s8_path,
                failure_severity="MEDIUM",
                failure_area="UI_LAYOUT",
                failure_detail="Токены «Главная» не обнаружены после возврата",
                duration_ms=dur8,
            )


if __name__ == "__main__":
    main()
