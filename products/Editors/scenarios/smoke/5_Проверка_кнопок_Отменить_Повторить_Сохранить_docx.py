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

from shared.infra import CaseRunner, StepVerifier, capture_step
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
        pre_ok, _ = assert_section_visible(
            pre_shot,
            SMOKE_TEXT_ASSERT_TOKENS,
            need=2,
        )
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
        shot1 = capture_step(runner.run_dir, 1, "undo", activate_driver=driver, pid=pid)

        last_ok = False

        def _probe_undo() -> bool:
            nonlocal last_ok
            driver.activate_window(pid)
            last_ok, _ = assert_text_absent(shot1, SMOKE_TEXT_ASSERT_TOKENS, max_found=0)
            return last_ok

        undo_ok = False
        for _ in range(5):
            click_ok = undo_last_action(pid, allow_hotkey_fallback=False)
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
        shot2 = capture_step(runner.run_dir, 2, "redo", activate_driver=driver, pid=pid)

        def _probe_redo() -> bool:
            nonlocal last_ok
            driver.activate_window(pid)
            last_ok, _ = assert_section_visible(shot2, SMOKE_TEXT_ASSERT_TOKENS, need=2)
            return last_ok

        redo_ok = False
        for _ in range(5):
            click_ok = redo_last_action(pid, allow_hotkey_fallback=False)
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
            step.check(
                condition=redo_ok,
                pass_msg="Команда «Повторить» выполнена, текст снова отображается",
                fail_msg=(
                    "Не удалось выполнить клик по UI-кнопке «Повторить» "
                    "или подтвердить возврат текста"
                ),
            )

        # Шаг 3. Сохранение документа
        save_active_document(pid, allow_hotkey_fallback=False)
        shot3 = capture_step(
            runner.run_dir,
            3,
            "save_dialog",
            activate_driver=driver,
            pid=pid,
        )

        def _probe_save_dialog() -> bool:
            nonlocal last_ok
            driver.activate_window(pid)
            last_ok, _ = assert_save_dialog_opened(shot3)
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

        def _probe_dialog_closed() -> bool:
            nonlocal last_ok
            driver.activate_window(pid)
            still_open, _ = assert_save_dialog_opened(shot4)
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
            step.check(
                condition=dialog_closed_ok,
                pass_msg="Системное окно сохранения закрыто после Enter",
                fail_msg="Системное окно сохранения не закрылось после Enter",
            )

        # Шаг 5. Проверка существования файла
        candidates = _candidate_save_paths()
        saved_path = {"value": ""}

        def _probe_file_exists() -> bool:
            for path in candidates:
                if assert_file_exists(path):
                    saved_path["value"] = path
                    return True
            # fallback: быстрый поиск по профилю пользователя
            home = Path.home()
            for pattern in ("Документ1.docx", "Document1.docx"):
                try:
                    for found in home.rglob(pattern):
                        saved_path["value"] = str(found)
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
                ["Создавайте", "новые", "файлы", "Документ", "Таблица", "Презентация"],
                need=3,
            )
            title_absent, _ = assert_text_absent(
                shot6,
                ["Документ1.docx", "Document1.docx", "*Документ1.docx", "*Document1.docx"],
                max_found=0,
            )
            last_ok = home_ok and title_absent
            return last_ok

        post_ok = False
        for _ in range(3):
            close_clicked = close_active_document_tab(pid, allow_hotkey_fallback=False)
            if not close_clicked:
                break
            if wait_until(_probe_main_screen, timeout_sec=3.0, poll_interval=0.5) and last_ok:
                post_ok = True
                break

        with StepVerifier(
            runner,
            step_num=6,
            step_name="Закрыть вкладку документа",
            expected="Вкладка закрыта, отображается главное окно редактора",
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot6)
            step.check(
                condition=post_ok,
                pass_msg="Вкладка документа закрыта, отображается главное окно редактора",
                fail_msg=(
                    "Не удалось выполнить клик по UI-кнопке закрытия вкладки "
                    "или подтвердить возврат на главное окно редактора"
                ),
            )


if __name__ == "__main__":
    main()
