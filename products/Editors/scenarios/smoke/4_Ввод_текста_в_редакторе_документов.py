# -*- coding: utf-8 -*-
"""
Кейс 4 — Ввод текста в редакторе документов.

Предусловие: после кейса 3 открыт новый документ.
Постусловие: текст введён, документ остаётся открытым для кейса 5.
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

from products.Editors.actions.editor_actions import type_document_text
from products.Editors.assertions.editor_assertions import (
    SMOKE_TEXT_ASSERT_TOKENS,
    assert_text_entered_and_left_aligned,
)


CASE_META = {
    "case_id": 4,
    "case_name": "Ввод текста в редакторе документов",
    "area": "Editors/Документы",
    "risk_level": "HIGH",
    "critical_path": True,
}


TEXT_TO_TYPE = (
    "Задача организации, в особенности же сложившаяся структура организации позволяет "
    "выполнять важные задания по разработке новых предложений. Товарищи! рамки и место "
    "обучения кадров представляет собой интересный эксперимент проверки существенных "
    "финансовых и административных условий. Задача организации, в особенности же "
    "сложившаяся структура организации способствует подготовки и реализации форм развития. "
    "Повседневная практика показывает, что постоянный количественный рост и сфера нашей "
    "активности влечет за собой процесс внедрения и модернизации систем массового участия. "
    "Значимость этих проблем настолько очевидна, что постоянное "
    "информационно-пропагандистское обеспечение нашей деятельности представляет собой "
    "интересный эксперимент проверки систем массового участия. Идейные соображения высшего "
    "порядка, а также дальнейшее развитие различных форм деятельности представляет собой "
    "интересный эксперимент проверки систем массового участия. 1234567890!\"№;%:?*()_+-="
)

def main():
    parser = argparse.ArgumentParser(
        description="Автотест: Ввод текста в редакторе документов",
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
                expected="Открыт документ после выполнения кейса 3",
                actual="Окно редактора не найдено",
                screenshot=shot,
                failure_detail=(
                    "Кейс 4 заблокирован: отсутствует окно редактора. "
                    "Сначала выполните кейсы 1-3."
                ),
            )
            return

        driver.activate_window(pid)

        try:
            type_document_text(pid, TEXT_TO_TYPE, align_left=False)
        except NotImplementedError as exc:
            shot = capture_step(
                runner.run_dir,
                1,
                "input_not_supported",
                activate_driver=driver,
                pid=pid,
            )
            runner.add_step(
                step_num=1,
                step_name="Ввести текст в документ",
                status="FAIL",
                expected="Текст введён и выровнен по левому краю",
                actual="Платформенный драйвер не поддерживает ввод текста для этой ОС",
                screenshot=shot,
                failure_type="INFRA_FAIL",
                failure_severity="MEDIUM",
                failure_area="INFRASTRUCTURE",
                failure_detail=str(exc),
            )
            return

        shot = capture_step(
            runner.run_dir,
            1,
            "text_input",
            activate_driver=driver,
            pid=pid,
        )

        last_ok = False

        def _probe_text_ready() -> bool:
            nonlocal last_ok
            driver.activate_window(pid)
            last_ok, _ = assert_text_entered_and_left_aligned(
                shot,
                tokens=SMOKE_TEXT_ASSERT_TOKENS,
                need=2,
                anchor_token="Задача",
                max_left_ratio=0.35,
            )
            return last_ok

        ready = wait_until(_probe_text_ready, timeout_sec=10, poll_interval=1.0)
        ok = ready and last_ok

        with StepVerifier(
            runner,
            step_num=1,
            step_name="Ввести/вставить текст",
            expected="Текст введён. Выровнен по левому краю.",
            severity="HIGH",
            failure_area="CORE_FUNCTION",
        ) as step:
            step.screenshot(shot)
            step.check(
                condition=ok,
                pass_msg="Текст введён в документ и расположен у левого поля страницы",
                fail_msg=(
                    "Не удалось подтвердить ввод текста или выравнивание по левому краю"
                ),
            )


if __name__ == "__main__":
    main()
