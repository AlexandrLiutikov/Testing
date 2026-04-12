# -*- coding: utf-8 -*-
"""
Кейс 2 — Главное окно редактора: навигация по разделам стартового экрана.

Предусловие: редактор уже запущен (кейс 1 выполнен).
Постусловие: редактор остаётся открытым для кейса 3.

Каждый шаг: действие (action) → подтверждающая проверка (assertion).
Вся инфраструктура — через reusable-слой (StepVerifier, capture_step).
"""

import argparse
import os
import sys

# --- Корень проекта в sys.path для импортов shared/ ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SCENARIOS_DIR = os.path.dirname(_SCRIPT_DIR)
_PRODUCT_DIR = os.path.dirname(_SCENARIOS_DIR)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_PRODUCT_DIR))
sys.path.insert(0, _PROJECT_ROOT)

# === Reuseable инфраструктура ===
from shared.infra import (
    CaseRunner,
    StepVerifier,
    apply_action_trace,
    apply_verification_result,
    capture_step,
)
from shared.infra.waits import wait_main_proc
from shared.drivers import get_driver

# === Продуктовый слой: actions ===
from products.Editors.actions.editor_actions import (
    click_menu,
    consume_action_trace,
    dismiss_collab_popup,
    list_start_menu_items_dom,
)

# === Продуктовый слой: assertions ===
from products.Editors.assertions.editor_assertions import (
    assert_section_visible,
    assert_popup_visible,
    assert_popup_closed,
)
from products.Editors.assertions.ui_catalog import (
    START_MENU_EXPECTED,
    diff_ui_items,
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


def _menu_drift_warnings():
    observed = list_start_menu_items_dom()
    if not observed:
        return []
    drift = diff_ui_items(observed, START_MENU_EXPECTED)
    out = []
    for item in drift.get("extra", []):
        out.append({
            "code": "UI_NEW_ELEMENT",
            "severity": "LOW",
            "message": f"Обнаружен новый элемент стартового меню: «{item}».",
        })
    for item in drift.get("missing", []):
        out.append({
            "code": "UI_MISSING_ELEMENT",
            "severity": "LOW",
            "message": f"В каталоге ожидается пункт меню «{item}», но он не найден.",
        })
    return out


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
        # Предусловие: редактор уже открыт (после кейса 1)
        # ==============================================================
        pid = wait_main_proc("editors", 20)
        if not pid:
            err_shot = capture_step(runner.run_dir, 0, "no_editor")
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
        s1_path = capture_step(runner.run_dir, 1, "home",
                               activate_driver=driver, pid=pid)
        home_result = assert_section_visible(
            s1_path,
            ["Создавайте новые файлы", "Документ", "Таблица", "Презентация"],
            need=2,
        )

        with StepVerifier(
            runner, step_num=1,
            step_name="Проверка: главное окно — «Главная» видна",
            expected="Отображается вкладка меню «Главная»",
            severity="HIGH",
            failure_area="UI_LAYOUT",
        ) as step:
            step.screenshot(s1_path)
            apply_verification_result(step, home_result, context="home_visible")
            for w in _menu_drift_warnings():
                step.add_warning(
                    code=w["code"],
                    severity=w["severity"],
                    message=w["message"],
                )
            step.check(
                condition=bool(home_result),
                pass_msg="Главное окно редактора открыто, отображается стартовый экран",
                fail_msg="Токены «Главная» не обнаружены на стартовом экране",
            )

        # ==============================================================
        # Шаг 2: Клик «Шаблоны» → проверка что раздел открыт
        # ==============================================================
        menu_trace = click_menu(pid, "templates")

        s2_path = capture_step(runner.run_dir, 2, "templates",
                               activate_driver=driver, pid=pid)
        templates_result = assert_section_visible(
            s2_path,
            ["Шаблоны документов", "Избранное", "Подключить папку"],
            need=1,
        )

        with StepVerifier(
            runner, step_num=2,
            step_name="Проверка: раздел «Шаблоны» открыт",
            expected="Отображается меню «Шаблоны»",
            severity="HIGH",
            failure_area="UI_LAYOUT",
        ) as step:
            step.screenshot(s2_path)
            apply_action_trace(
                step,
                menu_trace or consume_action_trace("click_menu"),
                "click_menu",
                primary_modes=("DOM_CDP", "DOM_FOCUS"),
            )
            apply_verification_result(step, templates_result, context="templates_visible")
            for w in _menu_drift_warnings():
                step.add_warning(
                    code=w["code"],
                    severity=w["severity"],
                    message=w["message"],
                )
            step.check(
                condition=bool(templates_result),
                pass_msg="Раздел «Шаблоны» открыт и отображается корректно",
                fail_msg="Раздел «Шаблоны» не подтверждён на экране после клика",
            )

        # ==============================================================
        # Шаг 3: Клик «Локальные файлы» → проверка что раздел открыт
        # ==============================================================
        menu_trace = click_menu(pid, "local")

        s3_path = capture_step(runner.run_dir, 3, "local",
                               activate_driver=driver, pid=pid)
        local_result = assert_section_visible(
            s3_path,
            ["Локальные файлы", "Выбрать папку", "Подключить папку"],
            need=1,
        )

        with StepVerifier(
            runner, step_num=3,
            step_name="Проверка: раздел «Локальные файлы» открыт",
            expected="Отображается меню «Локальные файлы»",
            severity="HIGH",
            failure_area="UI_LAYOUT",
        ) as step:
            step.screenshot(s3_path)
            apply_action_trace(
                step,
                menu_trace or consume_action_trace("click_menu"),
                "click_menu",
                primary_modes=("DOM_CDP", "DOM_FOCUS"),
            )
            apply_verification_result(step, local_result, context="local_visible")
            for w in _menu_drift_warnings():
                step.add_warning(
                    code=w["code"],
                    severity=w["severity"],
                    message=w["message"],
                )
            step.check(
                condition=bool(local_result),
                pass_msg="Раздел «Локальные файлы» открыт и отображается корректно",
                fail_msg="Раздел «Локальные файлы» не подтверждён на экране после клика",
            )

        # ==============================================================
        # Шаг 4: Клик «Совместная работа» → проверка модального окна
        # ==============================================================
        menu_trace = click_menu(pid, "collab")

        s4_path = capture_step(runner.run_dir, 4, "collab_popup",
                               activate_driver=driver, pid=pid)
        popup_result = assert_popup_visible(
            s4_path,
            ["Выберите диск для подключения", "URL диска",
             "Подключить", "Р7-Диск", "VK WorkSpace"],
            need=2,
        )

        with StepVerifier(
            runner, step_num=4,
            step_name="Проверка: окно подключения появилось",
            expected="Появляется окно «Выберите диск для подключения»",
            severity="HIGH",
            failure_area="UI_LAYOUT",
        ) as step:
            step.screenshot(s4_path)
            apply_action_trace(
                step,
                menu_trace or consume_action_trace("click_menu"),
                "click_menu",
                primary_modes=("DOM_CDP", "DOM_FOCUS"),
            )
            apply_verification_result(step, popup_result, context="collab_popup_visible")
            for w in _menu_drift_warnings():
                step.add_warning(
                    code=w["code"],
                    severity=w["severity"],
                    message=w["message"],
                )
            step.check(
                condition=bool(popup_result),
                pass_msg="Модальное окно подключения диска появилось",
                fail_msg="Модальное окно подключения не обнаружено",
            )

        # ==============================================================
        # Шаг 5: Закрытие модального окна → проверка что закрыто
        # ==============================================================
        dismiss_collab_popup(pid)

        s5_path = capture_step(runner.run_dir, 5, "after_popup_close",
                               activate_driver=driver, pid=pid)
        popup_closed_result = assert_popup_closed(
            s5_path,
            ["Выберите диск для подключения", "URL диска", "Подключить"],
        )

        with StepVerifier(
            runner, step_num=5,
            step_name="Проверка: окно подключения закрыто",
            expected="Всплывающее окно закрыто, отображается меню «Локальные файлы»",
            severity="HIGH",
            failure_area="UI_LAYOUT",
        ) as step:
            step.screenshot(s5_path)
            apply_verification_result(step, popup_closed_result, context="collab_popup_closed")
            step.check(
                condition=bool(popup_closed_result),
                pass_msg="Всплывающее окно закрыто, отображается меню «Локальные файлы»",
                fail_msg="Модальное окно подключения не закрылось по кнопке «X»",
            )

        # ==============================================================
        # Шаг 6: Клик «Настройки» → проверка что раздел открыт
        # ==============================================================
        menu_trace = click_menu(pid, "settings")

        s6_path = capture_step(runner.run_dir, 6, "settings",
                               activate_driver=driver, pid=pid)
        settings_result = assert_section_visible(
            s6_path,
            ["Настройки", "Язык интерфейса", "Масштабирование интерфейса"],
            need=2,
        )

        with StepVerifier(
            runner, step_num=6,
            step_name="Проверка: раздел «Настройки» открыт",
            expected="Отображается вкладка меню «Настройки»",
            severity="HIGH",
            failure_area="UI_LAYOUT",
        ) as step:
            step.screenshot(s6_path)
            apply_action_trace(
                step,
                menu_trace or consume_action_trace("click_menu"),
                "click_menu",
                primary_modes=("DOM_CDP", "DOM_FOCUS"),
            )
            apply_verification_result(step, settings_result, context="settings_visible")
            for w in _menu_drift_warnings():
                step.add_warning(
                    code=w["code"],
                    severity=w["severity"],
                    message=w["message"],
                )
            step.check(
                condition=bool(settings_result),
                pass_msg="Раздел «Настройки» открыт и отображается корректно",
                fail_msg="Раздел «Настройки» не подтверждён на экране после клика",
            )

        # ==============================================================
        # Шаг 7: Клик «О программе» → проверка что раздел открыт
        # ==============================================================
        menu_trace = click_menu(pid, "about")

        s7_path = capture_step(runner.run_dir, 7, "about",
                               activate_driver=driver, pid=pid)
        about_result = assert_section_visible(
            s7_path,
            ["Профессиональный (десктопная версия)",
             "Лицензионное соглашение", "Техподдержка"],
            need=1,
        )

        with StepVerifier(
            runner, step_num=7,
            step_name="Проверка: раздел «О программе» открыт",
            expected="Отображается меню «О программе»",
            severity="HIGH",
            failure_area="UI_LAYOUT",
        ) as step:
            step.screenshot(s7_path)
            apply_action_trace(
                step,
                menu_trace or consume_action_trace("click_menu"),
                "click_menu",
                primary_modes=("DOM_CDP", "DOM_FOCUS"),
            )
            apply_verification_result(step, about_result, context="about_visible")
            for w in _menu_drift_warnings():
                step.add_warning(
                    code=w["code"],
                    severity=w["severity"],
                    message=w["message"],
                )
            step.check(
                condition=bool(about_result),
                pass_msg="Раздел «О программе» открыт и отображается корректно",
                fail_msg="Раздел «О программе» не подтверждён на экране после клика",
            )

        # ==============================================================
        # Шаг 8: Клик «Главная» → проверка возврата на стартовый экран
        # ==============================================================
        menu_trace = click_menu(pid, "home")

        s8_path = capture_step(runner.run_dir, 8, "home_return",
                               activate_driver=driver, pid=pid)
        home_return_result = assert_section_visible(
            s8_path,
            ["Самое время начать", "Создавайте новые файлы",
             "Документ", "Таблица", "Презентация"],
            need=2,
        )

        with StepVerifier(
            runner, step_num=8,
            step_name="Проверка: возврат на «Главная»",
            expected="Отображается вкладка меню «Главная»",
            severity="HIGH",
            failure_area="UI_LAYOUT",
        ) as step:
            step.screenshot(s8_path)
            apply_action_trace(
                step,
                menu_trace or consume_action_trace("click_menu"),
                "click_menu",
                primary_modes=("DOM_CDP", "DOM_FOCUS"),
            )
            apply_verification_result(step, home_return_result, context="home_return_visible")
            for w in _menu_drift_warnings():
                step.add_warning(
                    code=w["code"],
                    severity=w["severity"],
                    message=w["message"],
                )
            step.check(
                condition=bool(home_return_result),
                pass_msg="Возврат на «Главная» выполнен, стартовый экран отображается",
                fail_msg="Возврат на «Главная» не подтверждён по OCR-токенам",
            )


if __name__ == "__main__":
    main()
