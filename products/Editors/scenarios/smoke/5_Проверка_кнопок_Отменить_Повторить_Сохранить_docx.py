# -*- coding: utf-8 -*-
"""
Кейс 5 — Проверка кнопок Отменить, Повторить, Сохранить (.docx).

Предусловие: после кейса 4 открыт документ с введённым текстом.
Постусловие: вкладка документа закрыта, открыт стартовый экран редактора.
"""

import argparse
import os
import sys
from pathlib import Path

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SCENARIOS_DIR = os.path.dirname(_SCRIPT_DIR)
_PRODUCT_DIR = os.path.dirname(_SCENARIOS_DIR)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_PRODUCT_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from shared.infra import (
    CaseRunner,
    StepVerifier,
    apply_action_trace,
    apply_verification_result,
    capture_step,
    merge_results,
)
from shared.infra.waits import wait_main_proc, wait_until
from shared.drivers import get_driver

from products.Editors.actions.editor_actions import (
    undo_last_action,
    redo_last_action,
    save_active_document,
    confirm_active_dialog,
    close_active_document_tab,
)
from products.Editors.assertions.editor_assertions import (
    SMOKE_TEXT_ASSERT_TOKENS,
    assert_section_visible,
    assert_text_absent,
    assert_save_dialog_opened,
    assert_file_exists,
)


CASE_META = {
    "case_id": 5,
    "case_name": "Проверка кнопок Отменить, Повторить, Сохранить .docx",
    "area": "Editors/Документы",
    "risk_level": "HIGH",
    "critical_path": True,
}


def _candidate_save_paths() -> list:
    """Сформировать кандидаты пути документа по умолчанию."""
    home = Path.home()
    folders = [
        home / "Documents",
        home / "Документы",
        home / "Pictures",
        home / "Изображения",
        home / "Картинки",
        home / "OneDrive" / "Documents",
        home / "OneDrive" / "Документы",
        home / "OneDrive" / "Pictures",
        home / "OneDrive" / "Изображения",
    ]
    names = ["Документ1.docx", "Document1.docx"]
    result = []
    for folder in folders:
        for name in names:
            result.append(str(folder / name))
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Автотест: Проверка кнопок Отменить, Повторить, Сохранить",
    )
    parser.add_argument(
        "--editor-path",
        default=r"C:\Program Files\R7-Office\Editors\DesktopEditors.exe",
    )
    parser.add_argument("--output-dir", default=_PRODUCT_DIR)
    args = parser.parse_args()

    with CaseRunner(CASE_META, args.editor_path, args.output_dir) as runner:
        driver = get_driver()
        pid = wait_main_proc("editors", 5)

        if not pid:
            shot = capture_step(runner.run_dir, 0, "blocked_no_editor")
            runner.add_step(
                step_num=0,
                step_name="Предусловие: документ открыт",
                status="BLOCKED",
                expected="Открыт документ после выполнения кейса 4",
                actual="Окно редактора не найдено",
                screenshot=shot,
                failure_detail=(
                    "Кейс 5 заблокирован: отсутствует окно редактора. "
                    "Сначала выполните кейсы 1-4."
                ),
            )
            return

        driver.activate_window(pid)

        pre_shot = capture_step(
            runner.run_dir,
            0,
            "precondition_text",
            activate_driver=driver,
            pid=pid,
        )
        pre_result = assert_section_visible(
            pre_shot,
            SMOKE_TEXT_ASSERT_TOKENS,
            need=2,
        )
        pre_ok = bool(pre_result)
        if not pre_ok:
            runner.add_step(
                step_num=0,
                step_name="Предусловие: в документе есть введённый текст",
                status="BLOCKED",
                expected="В документе отображается текст из кейса 4",
                actual="Не удалось подтвердить введённый текст перед проверкой Undo/Redo",
                screenshot=pre_shot,
                failure_detail=(
                    "Кейс 5 заблокирован: предусловие кейса 4 не подтверждено."
                ),
            )
            return

        # Шаг 1. Отменить ввод текста
        undo_clicked = False
        undo_trace = {}
        shot1 = capture_step(runner.run_dir, 1, "undo", activate_driver=driver, pid=pid)

        last_ok = False
        last_undo_result = None

        def _probe_undo() -> bool:
            nonlocal last_ok, last_undo_result
            driver.activate_window(pid)
            last_undo_result = assert_text_absent(shot1, SMOKE_TEXT_ASSERT_TOKENS, max_found=0)
            last_ok = bool(last_undo_result)
            return last_ok

        undo_ok = False
        for _ in range(5):
            undo_trace = undo_last_action(pid, allow_hotkey_fallback=False)
            click_ok = bool(undo_trace.get("ok"))
            undo_clicked = undo_clicked or click_ok
            if not undo_clicked:
                break
            if wait_until(_probe_undo, timeout_sec=2.0, poll_interval=0.5) and last_ok:
                undo_ok = True
                break

        with StepVerifier(
            runner,
            step_num=1,
            step_name="Клик по кнопке «Отменить»",
            expected=(
                "Отменено действие ввода текста. Текст на странице отсутствует."
            ),
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot1)
            apply_action_trace(
                step,
                undo_trace,
                "undo_last_action",
                primary_modes=("DOM_CDP", "DOM_FOCUS", "UIA"),
            )
            apply_verification_result(step, last_undo_result, context="undo_text_absent")
            step.check(
                condition=undo_ok,
                pass_msg="Команда «Отменить» выполнена, текст на странице отсутствует",
                fail_msg=(
                    "Не удалось выполнить клик по UI-кнопке «Отменить» "
                    "или текст всё ещё присутствует после нажатия"
                ),
            )

        # Шаг 2. Повторить ввод текста
        redo_clicked = False
        redo_trace = {}
        shot2 = capture_step(runner.run_dir, 2, "redo", activate_driver=driver, pid=pid)
        last_redo_result = None

        def _probe_redo() -> bool:
            nonlocal last_ok, last_redo_result
            driver.activate_window(pid)
            last_redo_result = assert_section_visible(shot2, SMOKE_TEXT_ASSERT_TOKENS, need=2)
            last_ok = bool(last_redo_result)
            return last_ok

        redo_ok = False
        for _ in range(5):
            redo_trace = redo_last_action(pid, allow_hotkey_fallback=False)
            click_ok = bool(redo_trace.get("ok"))
            redo_clicked = redo_clicked or click_ok
            if not redo_clicked:
                break
            if wait_until(_probe_redo, timeout_sec=2.0, poll_interval=0.5) and last_ok:
                redo_ok = True
                break

        with StepVerifier(
            runner,
            step_num=2,
            step_name="Клик по кнопке «Повторить»",
            expected="Повторено действие ввода текста, текст снова отображается",
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot2)
            apply_action_trace(
                step,
                redo_trace,
                "redo_last_action",
                primary_modes=("DOM_CDP", "DOM_FOCUS", "UIA"),
            )
            apply_verification_result(step, last_redo_result, context="redo_text_present")
            step.check(
                condition=redo_ok,
                pass_msg="Команда «Повторить» выполнена, текст снова отображается",
                fail_msg=(
                    "Не удалось выполнить клик по UI-кнопке «Повторить» "
                    "или подтвердить возврат текста"
                ),
            )

        # Шаг 3. Сохранение документа
        save_trace = save_active_document(pid, allow_hotkey_fallback=False)
        shot3 = capture_step(
            runner.run_dir,
            3,
            "save_dialog",
            activate_driver=driver,
            pid=pid,
        )

        last_save_dialog_result = None
        def _probe_save_dialog() -> bool:
            nonlocal last_ok, last_save_dialog_result
            driver.activate_window(pid)
            last_save_dialog_result = assert_save_dialog_opened(shot3)
            last_ok = bool(last_save_dialog_result)
            return last_ok

        save_dialog_ok = (
            wait_until(
                _probe_save_dialog,
                timeout_sec=10,
                poll_interval=1.0,
            )
            and last_ok
        )

        with StepVerifier(
            runner,
            step_num=3,
            step_name="Клик по кнопке «Сохранить»",
            expected=(
                "Открыто системное окно сохранения с именем документа по умолчанию"
            ),
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot3)
            apply_action_trace(
                step,
                save_trace,
                "save_active_document",
                primary_modes=("DOM_CDP", "DOM_FOCUS", "UIA"),
            )
            apply_verification_result(step, last_save_dialog_result, context="save_dialog_open")
            step.check(
                condition=save_dialog_ok,
                pass_msg="Открыто системное окно сохранения, имя документа по умолчанию отображается",
                fail_msg=(
                    "Не удалось выполнить клик по UI-кнопке «Сохранить» "
                    "или подтвердить открытие системного окна сохранения"
                ),
            )

        # Шаг 4. Подтверждение сохранения
        confirm_active_dialog(pid)
        shot4 = capture_step(
            runner.run_dir,
            4,
            "save_confirmed",
            activate_driver=driver,
            pid=pid,
        )

        last_dialog_state_result = None
        def _probe_dialog_closed() -> bool:
            nonlocal last_ok, last_dialog_state_result
            driver.activate_window(pid)
            last_dialog_state_result = assert_save_dialog_opened(shot4)
            still_open = bool(last_dialog_state_result)
            last_ok = not still_open
            return last_ok

        dialog_closed_ok = wait_until(
            _probe_dialog_closed,
            timeout_sec=10,
            poll_interval=1.0,
        ) and last_ok

        with StepVerifier(
            runner,
            step_num=4,
            step_name="Нажать клавишу Enter в окне сохранения",
            expected="Системное окно сохранения закрыто, документ сохранён",
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot4)
            apply_verification_result(step, last_dialog_state_result, context="save_dialog_state")
            step.add_signal_note("save_dialog_state.inverted=true")
            step.check(
                condition=dialog_closed_ok,
                pass_msg="Системное окно сохранения закрыто после Enter",
                fail_msg="Системное окно сохранения не закрылось после Enter",
            )

        # Шаг 5. Проверка существования файла
        candidates = _candidate_save_paths()
        saved_path = {"value": ""}
        recursive_search_used = {"value": False}
        last_file_result = None

        def _probe_file_exists() -> bool:
            nonlocal last_file_result
            for path in candidates:
                probe = assert_file_exists(path)
                if probe:
                    last_file_result = probe
                    saved_path["value"] = path
                    return True
            # fallback: быстрый поиск по профилю пользователя
            home = Path.home()
            for pattern in ("Документ1.docx", "Document1.docx"):
                try:
                    for found in home.rglob(pattern):
                        recursive_search_used["value"] = True
                        saved_path["value"] = str(found)
                        last_file_result = assert_file_exists(saved_path["value"])
                        return True
                except OSError:
                    continue
            return False

        file_ok = wait_until(_probe_file_exists, timeout_sec=15, poll_interval=1.0)
        shot5 = capture_step(
            runner.run_dir,
            5,
            "file_exists",
            activate_driver=driver,
            pid=pid,
        )

        with StepVerifier(
            runner,
            step_num=5,
            step_name="Проверить наличие сохранённого документа",
            expected="Сохранённый файл Документ1.docx существует в каталоге документов",
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot5)
            apply_verification_result(step, last_file_result, context="saved_file_exists")
            if recursive_search_used["value"]:
                step.set_fallback(
                    "FILESYSTEM_RECURSIVE_SEARCH",
                    "Файл не найден в стандартных каталогах; применён рекурсивный поиск в профиле пользователя.",
                )
                step.add_warning(
                    code="FILE_SEARCH_FALLBACK",
                    severity="LOW",
                    message="Путь сохранённого файла получен через рекурсивный fallback-поиск.",
                )
            step.check(
                condition=file_ok,
                pass_msg=f"Сохранённый файл найден: {saved_path['value']}",
                fail_msg=(
                    "Не удалось найти сохранённый файл Документ1.docx "
                    "в стандартных каталогах документов"
                ),
            )

        # Постусловие. Закрыть вкладку документа
        shot6 = capture_step(
            runner.run_dir,
            6,
            "document_tab_closed",
            activate_driver=driver,
            pid=pid,
        )

        def _probe_main_screen() -> bool:
            nonlocal last_ok
            driver.activate_window(pid)
            home_ok, _ = assert_section_visible(
                shot6,
                ["Главная", "Последние", "файлы", "Документ", "Таблица", "Презентация"],
                need=3,
            )
            recent_name = Path(saved_path["value"]).name if saved_path["value"] else "Документ1.docx"
            recent_ok, _ = assert_section_visible(
                shot6,
                [recent_name, "Документ1.docx", "Document1.docx"],
                need=1,
            )
            last_ok = home_ok and recent_ok
            return last_ok

        post_ok = False
        close_trace = {}
        for _ in range(3):
            close_trace = close_active_document_tab(pid, allow_hotkey_fallback=False)
            close_clicked = bool(close_trace.get("ok"))
            if not close_clicked:
                break
            if wait_until(_probe_main_screen, timeout_sec=3.0, poll_interval=0.5) and last_ok:
                post_ok = True
                break

        with StepVerifier(
            runner,
            step_num=6,
            step_name="Закрыть вкладку документа",
            expected=(
                "Вкладка закрыта, отображается главное окно редактора, "
                "сохранённый документ есть в списке последних файлов"
            ),
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot6)
            apply_action_trace(
                step,
                close_trace,
                "close_active_document_tab",
                primary_modes=("DOM_CDP", "DOM_FOCUS", "UIA"),
            )
            home_probe = assert_section_visible(
                shot6,
                ["Главная", "Последние", "файлы", "Документ", "Таблица", "Презентация"],
                need=3,
            )
            recent_name = Path(saved_path["value"]).name if saved_path["value"] else "Документ1.docx"
            recent_probe = assert_section_visible(
                shot6,
                [recent_name, "Документ1.docx", "Document1.docx"],
                need=1,
            )
            post_probe = merge_results([home_probe, recent_probe], mode="all")
            apply_verification_result(step, post_probe, context="postcondition_home_recent")
            step.check(
                condition=post_ok,
                pass_msg=(
                    "Вкладка документа закрыта, открыт главный экран, "
                    "сохранённый файл отображается в списке последних"
                ),
                fail_msg=(
                    "Не удалось выполнить клик по UI-кнопке закрытия вкладки "
                    "или подтвердить главный экран со списком последних файлов"
                ),
            )


if __name__ == "__main__":
    main()
