# -*- coding: utf-8 -*-
"""
Кейс 6 — Открытие файла эталона .docx.

Предусловие: кейс 5 завершён, отображается главное окно редактора.
Постусловие: эталонный документ остаётся открытым для кейса 7.
"""

import argparse
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SCENARIOS_DIR = os.path.dirname(_SCRIPT_DIR)
_PRODUCT_DIR = os.path.dirname(_SCENARIOS_DIR)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_PRODUCT_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from shared.infra import CaseRunner, StepVerifier, capture_step
from shared.infra.waits import wait_main_proc, wait_until
from shared.drivers import get_driver

from products.Editors.actions.editor_actions import (
    click_zoom_to_page,
    go_to_next_page,
    open_document_by_path,
)
from products.Editors.assertions.editor_assertions import (
    assert_reference_document_opened,
    assert_reference_document_page_content,
    assert_section_visible,
)


CASE_META = {
    "case_id": 6,
    "case_name": "Открытие файла эталона .docx",
    "area": "Editors/Документы",
    "risk_level": "HIGH",
    "critical_path": True,
}

REFERENCE_DOC_NAME = "Document_dlya_proverki_vozmozhnostey_tekstovogo_redaktora.docx"


def _attach_action_trace(step, trace: dict, action_name: str):
    if not trace:
        return

    if trace.get("fallback_used"):
        step.set_fallback(
            trace.get("fallback_source", ""),
            trace.get("fallback_reason", ""),
        )

    mode = str(trace.get("mode", "")).strip()
    if mode and mode not in ("DOM_CDP", "LAUNCH_DEBUG", "KEYBOARD", "MOUSE_WHEEL"):
        step.add_warning(
            code=f"{action_name.upper()}_MODE",
            severity="LOW",
            message=f"Action выполнился в режиме {mode}, а не в primary-пути.",
        )

    for w in trace.get("warnings", []) or []:
        step.add_warning(
            code=w.get("code", "ACTION_WARNING"),
            severity=w.get("severity", "LOW"),
            message=w.get("message", ""),
        )


def main():
    parser = argparse.ArgumentParser(
        description="Автотест: Открытие файла эталона .docx",
    )
    parser.add_argument(
        "--editor-path",
        default=r"C:\Program Files\R7-Office\Editors\DesktopEditors.exe",
    )
    parser.add_argument("--output-dir", default=_PRODUCT_DIR)
    args = parser.parse_args()

    reference_path = os.path.join(_PRODUCT_DIR, "test_data", REFERENCE_DOC_NAME)

    with CaseRunner(CASE_META, args.editor_path, args.output_dir) as runner:
        driver = get_driver()
        pid = wait_main_proc("editors", 5)

        if not pid:
            shot = capture_step(runner.run_dir, 0, "blocked_no_editor")
            runner.add_step(
                step_num=0,
                step_name="Предусловие: главное окно редактора открыто",
                status="BLOCKED",
                expected=(
                    "После кейса 5 открыто главное окно редактора со списком последних файлов"
                ),
                actual="Окно редактора не найдено",
                screenshot=shot,
                failure_detail=(
                    "Кейс 6 заблокирован: отсутствует окно редактора. "
                    "Сначала выполните кейсы 1-5."
                ),
            )
            return

        if not os.path.isfile(reference_path):
            shot = capture_step(
                runner.run_dir,
                0,
                "blocked_no_reference_file",
                activate_driver=driver,
                pid=pid,
            )
            runner.add_step(
                step_num=0,
                step_name="Предусловие: файл эталона доступен",
                status="BLOCKED",
                expected=f"Файл {REFERENCE_DOC_NAME} доступен в каталоге test_data",
                actual="Файл эталона не найден",
                screenshot=shot,
                failure_detail=f"Отсутствует файл: {reference_path}",
            )
            return

        driver.activate_window(pid)

        # Шаг 1. Открыть эталонный файл скриптом.
        open_trace = open_document_by_path(
            args.editor_path,
            reference_path,
            enable_debug=True,
        )

        shot1 = capture_step(
            runner.run_dir,
            1,
            "reference_doc_opened",
            activate_driver=driver,
            pid=pid,
        )
        last_ok = False

        def _probe_opened() -> bool:
            nonlocal pid, last_ok
            new_pid = wait_main_proc("editors", 2)
            if new_pid:
                pid = new_pid
            driver.activate_window(pid)
            last_ok, _ = assert_reference_document_opened(shot1)
            return last_ok

        opened_ok = wait_until(_probe_opened, timeout_sec=12, poll_interval=1.0) and last_ok

        if not opened_ok:
            open_trace = open_document_by_path(
                args.editor_path,
                reference_path,
                enable_debug=False,
            )
            opened_ok = wait_until(_probe_opened, timeout_sec=12, poll_interval=1.0) and last_ok

        with StepVerifier(
            runner,
            step_num=1,
            step_name="Открыть файл с помощью скрипта",
            expected=(
                f"Файл «{REFERENCE_DOC_NAME}» открыт в редакторе документов"
            ),
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot1)
            _attach_action_trace(step, open_trace, "open_document_by_path")
            step.check(
                condition=opened_ok,
                pass_msg=f"Файл «{REFERENCE_DOC_NAME}» открыт",
                fail_msg=(
                    f"Не удалось открыть файл «{REFERENCE_DOC_NAME}» "
                    "через запуск редактора с путём к документу"
                ),
            )

        # Шаг 2. Клик «По размеру страницы» + подтверждение страницы 1 целиком.
        zoom_trace = click_zoom_to_page(pid)
        shot2 = capture_step(
            runner.run_dir,
            2,
            "zoom_to_page",
            activate_driver=driver,
            pid=pid,
        )
        zoom_label_ok, _ = assert_section_visible(
            shot2,
            ["По размеру страницы", "Fit Page"],
            need=1,
        )
        zoom_status_ok, _ = assert_section_visible(
            shot2,
            ["Масштаб", "100%"],
            need=1,
        )
        page1_full_ok, page1_full_found = assert_section_visible(
            shot2,
            ["Это особый колонтитул для первой страницы", "Страница 1 из 4", "Страница 1 из4"],
            need=2,
        )
        page1_token_ok, page1_token_found = assert_reference_document_page_content(shot2, 1)
        zoom_expected = "Масштаб изменён, страница целиком помещается в рабочей области"
        page1_match_msg = "Содержание и форма первой страницы совпадают с эталоном"
        zoom_ok = (
            bool(zoom_trace.get("ok"))
            and (zoom_label_ok or zoom_status_ok)
            and page1_full_ok
            and page1_token_ok
        )

        with StepVerifier(
            runner,
            step_num=2,
            step_name="В строке состояния кликнуть «По размеру страницы»",
            expected=zoom_expected,
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot2)
            _attach_action_trace(step, zoom_trace, "click_zoom_to_page")
            step.check(
                condition=zoom_ok,
                pass_msg=f"{zoom_expected}. {page1_match_msg}.",
                fail_msg=(
                    "Не подтверждено отображение страницы 1 целиком после команды "
                    f"«По размеру страницы». Маркеры full-page: "
                    f"{page1_full_found if page1_full_found else 'нет'}; "
                    f"маркеры страницы 1: {page1_token_found if page1_token_found else 'нет'}"
                ),
            )

        # Шаг 3. Проверка страницы 2.
        page2_nav_trace = go_to_next_page(pid)
        shot3 = capture_step(
            runner.run_dir,
            3,
            "reference_page_2_check",
            activate_driver=driver,
            pid=pid,
        )
        page2_state = {"ok": False, "found": []}

        def _probe_page2() -> bool:
            driver.activate_window(pid)
            ok, found = assert_reference_document_page_content(shot3, 2)
            page2_state["ok"] = ok
            page2_state["found"] = found
            return ok

        page2_ok = wait_until(_probe_page2, timeout_sec=8, poll_interval=1.0) and page2_state["ok"]
        page2_expected = "Отображается страница 2 эталонного документа"

        with StepVerifier(
            runner,
            step_num=3,
            step_name="Проверка страницы 2",
            expected=page2_expected,
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot3)
            _attach_action_trace(step, page2_nav_trace, "go_to_next_page")
            step.check(
                condition=page2_ok,
                pass_msg=page2_expected,
                fail_msg=(
                    "Не подтверждено отображение страницы 2. "
                    f"Найденные OCR-маркеры: "
                    f"{page2_state['found'] if page2_state['found'] else 'нет OCR-токенов'}"
                ),
            )

        # Шаг 4. Проверка страницы 3.
        page3_nav_trace = go_to_next_page(pid)
        shot4 = capture_step(
            runner.run_dir,
            4,
            "reference_page_3_check",
            activate_driver=driver,
            pid=pid,
        )
        page3_state = {"ok": False, "found": []}

        def _probe_page3() -> bool:
            driver.activate_window(pid)
            ok, found = assert_reference_document_page_content(shot4, 3)
            page3_state["ok"] = ok
            page3_state["found"] = found
            return ok

        page3_ok = wait_until(_probe_page3, timeout_sec=8, poll_interval=1.0) and page3_state["ok"]
        page3_expected = "Отображается страница 3 эталонного документа"

        with StepVerifier(
            runner,
            step_num=4,
            step_name="Проверка страницы 3",
            expected=page3_expected,
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot4)
            _attach_action_trace(step, page3_nav_trace, "go_to_next_page")
            step.check(
                condition=page3_ok,
                pass_msg=page3_expected,
                fail_msg=(
                    "Не подтверждено отображение страницы 3. "
                    f"Найденные OCR-маркеры: "
                    f"{page3_state['found'] if page3_state['found'] else 'нет OCR-токенов'}"
                ),
            )

        # Шаг 5. Проверка страницы 4.
        page4_nav_trace = go_to_next_page(pid)
        shot5 = capture_step(
            runner.run_dir,
            5,
            "reference_page_4_check",
            activate_driver=driver,
            pid=pid,
        )
        page4_state = {"ok": False, "found": []}

        def _probe_page4() -> bool:
            driver.activate_window(pid)
            ok, found = assert_reference_document_page_content(shot5, 4)
            page4_state["ok"] = ok
            page4_state["found"] = found
            return ok

        page4_ok = wait_until(_probe_page4, timeout_sec=8, poll_interval=1.0) and page4_state["ok"]
        page4_expected = "Отображается страница 4 эталонного документа"

        with StepVerifier(
            runner,
            step_num=5,
            step_name="Проверка страницы 4",
            expected=page4_expected,
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot5)
            _attach_action_trace(step, page4_nav_trace, "go_to_next_page")
            step.check(
                condition=page4_ok,
                pass_msg=page4_expected,
                fail_msg=(
                    "Не подтверждено отображение страницы 4. "
                    f"Найденные OCR-маркеры: "
                    f"{page4_state['found'] if page4_state['found'] else 'нет OCR-токенов'}"
                ),
            )


if __name__ == "__main__":
    main()
