"""
Автотест: Создание нового документа и проверка вкладок на панели инструментов.
Кейс 3 — Smoke (Документы).

Предусловие: редактор запущен (после кейса 2), отображается главное окно редактора.
Постусловие: редактор остаётся открытым с созданным документом для продолжения цепочки smoke.
"""

import argparse
import os
import sys

# --- Корень проекта в sys.path для импортов shared/ ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PRODUCT_DIR = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_PRODUCT_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from shared.infra import CaseRunner, StepVerifier, capture_step, DurationTimer
from shared.infra.waits import wait_main_proc, wait_until
from shared.drivers import get_driver

from products.Editors.actions.editor_actions import (
    create_document,
    click_toolbar_tab,
    calibrate_toolbar_tabs,
)
from products.Editors.assertions.editor_assertions import (
    assert_document_created,
    assert_tab_active,
)


CASE_META = {
    "case_id": 3,
    "case_name": "Создание нового документа и проверка вкладок на панели инструментов",
    "area": "Editors/Документы",
    "risk_level": "HIGH",
    "critical_path": True,
}


TABS_PLAN = [
    (2, "Файл", "Вкладка «Файл» активна. Открыто меню «Сведения о документе»", ["Сведения", "Сохранить как", "Скачать как", "Версия"], 2),
    (3, "Вставка", "Вкладка «Вставка» активна, подчёркнута синей линией", ["Таблица", "Изображение", "Диаграмма", "Колонтитулы"], 2),
    (4, "Рисование", "Вкладка «Рисование» активна, подчёркнута синей линией", ["Выбрать", "Перо", "Маркер", "Ластик"], 1),
    (5, "Макет", "Вкладка «Макет» активна, подчёркнута синей линией", ["Поля", "Ориентация", "Размер", "Колонки"], 2),
    (6, "Ссылки", "Вкладка «Ссылки» активна, подчёркнута синей линией", ["Оглавление", "Сноска", "Закладка", "Гиперссылка"], 2),
    (7, "Совместная работа", "Вкладка «Совместная работа» активна, подчёркнута синей линией", ["Комментарий", "Сравнить"], 1),
    (8, "Защита", "Вкладка «Защита» активна, подчёркнута синей линией", ["Зашифровать", "Подпись"], 1),
    (9, "Вид", "Вкладка «Вид» активна, подчёркнута синей линией", ["Масштаб", "Линейка", "Непечатаемые"], 1),
    (10, "Плагины", "Вкладка «Плагины» активна, подчёркнута синей линией", ["Макросы", "Менеджер"], 1),
]


def _add_blocked_tabs(runner, reason):
    for step_num, tab_name, expected, _, _ in TABS_PLAN:
        shot = capture_step(runner.run_dir, step_num, f"tab_{step_num}")
        runner.add_step(
            step_num=step_num,
            step_name=f"Клик по вкладке «{tab_name}»",
            status="BLOCKED",
            expected=expected,
            actual="Шаг не выполнен из-за сбоя на шаге создания документа",
            screenshot=shot,
            failure_detail=reason,
        )


def _run_tab_step(runner, pid, tab_data, positions=None):
    step_num, tab_name, expected, tokens, need = tab_data
    click_toolbar_tab(pid, tab_name, positions=positions)
    shot = capture_step(runner.run_dir, step_num, f"tab_{step_num}", activate_driver=get_driver(), pid=pid)
    ok, _ = assert_tab_active(shot, tab_name, tokens, need)

    with StepVerifier(
        runner,
        step_num=step_num,
        step_name=f"Клик по вкладке «{tab_name}»",
        expected=expected,
        severity="HIGH",
        failure_area="CORE_FUNCTION",
    ) as step:
        step.screenshot(shot)
        step.check(
            condition=ok,
            pass_msg=f"Вкладка «{tab_name}» активна, содержимое панели отображается",
            fail_msg=f"Вкладка «{tab_name}» не подтверждена на экране после клика",
        )

    if tab_name == "Файл":
        get_driver().send_escape(pid)


def main():
    parser = argparse.ArgumentParser(
        description="Автотест: Создание документа и проверка вкладок",
    )
    parser.add_argument(
        "--editor-path",
        default=r"C:\Program Files\R7-Office\Editors\DesktopEditors.exe",
    )
    parser.add_argument("--output-dir", default=_PRODUCT_DIR)
    args = parser.parse_args()

    with CaseRunner(CASE_META, args.editor_path, args.output_dir) as runner:
        driver = get_driver()
        pid = None
        try:
            pid = wait_main_proc("editors", 20)
            if not pid:
                shot = capture_step(runner.run_dir, 0, "no_editor")
                runner.add_step(
                    step_num=0,
                    step_name="Предусловие: редактор открыт",
                    status="BLOCKED",
                    expected="Редактор запущен (после кейса 2)",
                    actual="Окно редактора не найдено",
                    screenshot=shot,
                    failure_detail=(
                        "Окно редактора не найдено. "
                        "Кейс 3 заблокирован до успешного выполнения кейсов 1 и 2."
                    ),
                )
                return

            driver.activate_window(pid)

            step_timer = DurationTimer()
            create_document(pid, "document")

            new_pid = wait_main_proc("editors", 10)
            if new_pid:
                pid = new_pid
                driver.activate_window(pid)

            s1_path = capture_step(
                runner.run_dir,
                1,
                "new_document",
                activate_driver=driver,
                pid=pid,
            )
            doc_tokens = ["Междустрочный", "Множитель", "Страница", "Количество"]
            wait_until(
                lambda: assert_document_created(s1_path, tokens=doc_tokens, need=2)[0],
                timeout_sec=10,
                poll_interval=1.0,
            )
            created_ok, _ = assert_document_created(s1_path, tokens=doc_tokens, need=2)

            if created_ok:
                runner.add_step(
                    step_num=1,
                    step_name="Создание нового документа",
                    status="PASS",
                    expected="Новый документ создан, вкладка «Главная» активна",
                    actual="Новый документ создан, элементы вкладки «Главная» отображаются",
                    screenshot=s1_path,
                    duration_ms=step_timer.elapsed_ms(),
                )
            else:
                runner.add_step(
                    step_num=1,
                    step_name="Создание нового документа",
                    status="FAIL",
                    expected="Новый документ создан, вкладка «Главная» активна",
                    actual="Документ не создан или панель инструментов не отображается",
                    screenshot=s1_path,
                    duration_ms=step_timer.elapsed_ms(),
                    failure_type="TEST_FAIL",
                    failure_severity="HIGH",
                    failure_area="CORE_FUNCTION",
                    failure_detail="Не удалось создать новый документ из стартового экрана",
                )
                _add_blocked_tabs(
                    runner,
                    "Проверка вкладок заблокирована, потому что документ не создан.",
                )
                return

            tab_positions = calibrate_toolbar_tabs(s1_path)
            for tab_data in TABS_PLAN:
                _run_tab_step(runner, pid, tab_data, positions=tab_positions)

        except Exception as exc:
            error_shot = capture_step(
                runner.run_dir,
                99,
                "error",
                activate_driver=driver if pid else None,
                pid=pid,
            )
            runner.add_step(
                step_num=99,
                step_name="Ошибка выполнения",
                status="FAIL",
                expected="Кейс выполняется без инфраструктурных сбоев",
                actual=str(exc),
                screenshot=error_shot,
                failure_type="INFRA_FAIL",
                failure_severity="MEDIUM",
                failure_area="INFRASTRUCTURE",
                failure_detail=str(exc),
            )


if __name__ == "__main__":
    main()
