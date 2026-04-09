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
    if mode and mode not in ("DOM_CDP", "LAUNCH_DEBUG", "KEYBOARD"):
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

        # Шаг 2. Клик «По размеру страницы».
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
        zoom_ok = bool(zoom_trace.get("ok")) and (zoom_label_ok or zoom_status_ok)

        with StepVerifier(
            runner,
            step_num=2,
            step_name="В строке состояния кликнуть «По размеру страницы»",
            expected=(
                "Масштаб изменён, страница целиком помещается в рабочей области"
            ),
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot2)
            _attach_action_trace(step, zoom_trace, "click_zoom_to_page")
            step.check(
                condition=zoom_ok,
                pass_msg=(
                    "Команда «По размеру страницы» выполнена, строка масштаба доступна"
                ),
                fail_msg=(
                    "Не удалось выполнить команду «По размеру страницы» "
                    "или подтвердить строку состояния масштаба"
                ),
            )

        # Шаг 3. Проверить содержимое 4-х страниц эталона.
        missing_pages = []
        page_found_tokens = {}

        for page_index in (1, 2, 3, 4):
            if page_index > 1:
                go_to_next_page(pid)

            page_shot = capture_step(
                runner.run_dir,
                20 + page_index,
                f"reference_page_{page_index}",
                activate_driver=driver,
                pid=pid,
            )

            page_ok_state = {"ok": False, "found": []}

            def _probe_page() -> bool:
                driver.activate_window(pid)
                ok, found = assert_reference_document_page_content(page_shot, page_index)
                page_ok_state["ok"] = ok
                page_ok_state["found"] = found
                return ok

            page_ok = wait_until(_probe_page, timeout_sec=8, poll_interval=1.0) and page_ok_state["ok"]
            page_found_tokens[page_index] = page_ok_state["found"]
            if not page_ok:
                missing_pages.append(page_index)

        shot3 = capture_step(
            runner.run_dir,
            3,
            "reference_pages_check",
            activate_driver=driver,
            pid=pid,
        )
        pages_ok = not missing_pages
        found_detail = "; ".join(
            f"стр. {idx}: {', '.join(tokens) if tokens else 'нет OCR-токенов'}"
            for idx, tokens in page_found_tokens.items()
        )

        with StepVerifier(
            runner,
            step_num=3,
            step_name="Проверка отображения содержимого всех 4-х страниц",
            expected=(
                "Содержимое всех 4-х страниц отображается без визуальных нарушений"
            ),
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot3)
            step.check(
                condition=pages_ok,
                pass_msg=(
                    "Проверено содержимое 4-х страниц эталонного документа: "
                    "текстовые маркеры каждой страницы обнаружены"
                ),
                fail_msg=(
                    f"Не подтверждено отображение страниц: {missing_pages}. "
                    f"Найденные OCR-маркеры: {found_detail}"
                ),
            )


if __name__ == "__main__":
    main()
