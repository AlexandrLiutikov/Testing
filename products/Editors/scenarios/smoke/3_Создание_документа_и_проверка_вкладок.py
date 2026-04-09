"""
Автотест: Создание нового документа и проверка вкладок на панели инструментов.
Кейс 3 — Smoke (Документы).

Предусловие: редактор запущен (после кейса 2), отображается главное окно редактора.
Постусловие: редактор остаётся открытым с созданным документом для продолжения цепочки smoke.
"""

import argparse
import os
import re
import sys

# --- Корень проекта в sys.path для импортов shared/ ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PRODUCT_DIR = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_PRODUCT_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from shared.infra import CaseRunner, StepVerifier, capture_step
from shared.infra.waits import wait_main_proc, wait_until
from shared.drivers import get_driver

from products.Editors.actions.editor_actions import (
    create_document,
    click_toolbar_tab,
    calibrate_toolbar_tabs,
    list_toolbar_tabs_dom,
)
from products.Editors.assertions.editor_assertions import (
    assert_document_created,
    assert_tab_active,
)
from products.Editors.assertions.ui_catalog import (
    TOOLBAR_TABS,
    diff_ui_items,
    toolbar_tab_names,
)


CASE_META = {
    "case_id": 3,
    "case_name": "Создание нового документа и проверка вкладок на панели инструментов",
    "area": "Editors/Документы",
    "risk_level": "HIGH",
    "critical_path": True,
}


_TAB_EXPECTED_TEXT = {
    "Файл": "Вкладка «Файл» активна. Открыто меню «Сведения о документе»",
    "Вставка": "Вкладка «Вставка» активна, подчёркнута синей линией",
    "Рисование": "Вкладка «Рисование» активна, подчёркнута синей линией",
    "Макет": "Вкладка «Макет» активна, подчёркнута синей линией",
    "Ссылки": "Вкладка «Ссылки» активна, подчёркнута синей линией",
    "Совместная работа": "Вкладка «Совместная работа» активна, подчёркнута синей линией",
    "Защита": "Вкладка «Защита» активна, подчёркнута синей линией",
    "Вид": "Вкладка «Вид» активна, подчёркнута синей линией",
    "Плагины": "Вкладка «Плагины» активна, подчёркнута синей линией",
}


def _build_tabs_plan():
    plan = []
    step_num = 2
    for item in TOOLBAR_TABS:
        name = item["name"]
        required = list(item.get("required", []))
        optional = list(item.get("optional", []))
        need = int(item.get("need", max(1, len(required))))
        tokens = required + optional
        expected = _TAB_EXPECTED_TEXT.get(name, f"Вкладка «{name}» активна.")
        plan.append((step_num, name, expected, tokens, need))
        step_num += 1
    return plan


TABS_PLAN = _build_tabs_plan()


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


def _attach_action_trace(step, trace: dict, action_name: str):
    if not trace:
        return

    if trace.get("fallback_used"):
        step.set_fallback(
            trace.get("fallback_source", ""),
            trace.get("fallback_reason", ""),
        )

    mode = str(trace.get("mode", "")).strip()
    if mode and mode not in ("DOM_CDP", "DOM_FOCUS"):
        step.add_warning(
            code=f"{action_name.upper()}_MODE",
            severity="LOW",
            message=f"Action выполнился в режиме {mode}, а не в DOM primary.",
        )

    for w in trace.get("warnings", []) or []:
        step.add_warning(
            code=w.get("code", "ACTION_WARNING"),
            severity=w.get("severity", "LOW"),
            message=w.get("message", ""),
        )


def _toolbar_drift_warnings():
    observed_raw = list_toolbar_tabs_dom()
    if not observed_raw:
        return []

    observed = []
    for item in observed_raw:
        text = " ".join(str(item).split())
        if not text:
            continue
        if len(text) > 40:
            continue
        if not re.fullmatch(r"[A-Za-zА-Яа-яЁё\-\s]{2,40}", text):
            continue
        observed.append(text)

    if not observed:
        return []

    drift = diff_ui_items(observed, toolbar_tab_names())
    out = []
    for item in drift.get("extra", [])[:6]:
        out.append({
            "code": "UI_NEW_ELEMENT",
            "severity": "LOW",
            "message": f"Обнаружена новая вкладка/элемент панели: «{item}».",
        })
    for item in drift.get("missing", [])[:6]:
        out.append({
            "code": "UI_MISSING_ELEMENT",
            "severity": "LOW",
            "message": f"Ожидаемая вкладка «{item}» не обнаружена в DOM-каталоге.",
        })
    return out


def _run_tab_step(runner, pid, tab_data, positions=None):
    step_num, tab_name, expected, tokens, need = tab_data
    tab_trace = click_toolbar_tab(pid, tab_name, positions=positions)
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
        _attach_action_trace(step, tab_trace, "click_toolbar_tab")
        for w in _toolbar_drift_warnings():
            step.add_warning(
                code=w["code"],
                severity=w["severity"],
                message=w["message"],
            )
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
            pid = wait_main_proc("editors", 3)
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

            create_trace = create_document(pid, "document")

            new_pid = wait_main_proc("editors", 3)
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
            last_probe_ok = False

            def probe_document_created() -> bool:
                nonlocal last_probe_ok
                driver.activate_window(pid)
                last_probe_ok, _ = assert_document_created(s1_path, tokens=doc_tokens, need=2)
                return last_probe_ok

            ready = wait_until(
                probe_document_created,
                timeout_sec=10,
                poll_interval=1.0,
            )
            created_ok = ready and last_probe_ok

            with StepVerifier(
                runner,
                step_num=1,
                step_name="Создание нового документа",
                expected="Новый документ создан, вкладка «Главная» активна",
                severity="HIGH",
                failure_area="CORE_FUNCTION",
            ) as step:
                step.screenshot(s1_path)
                _attach_action_trace(step, create_trace, "create_document")
                for w in _toolbar_drift_warnings():
                    step.add_warning(
                        code=w["code"],
                        severity=w["severity"],
                        message=w["message"],
                    )
                step.check(
                    condition=created_ok,
                    pass_msg="Новый документ создан, элементы вкладки «Главная» отображаются",
                    fail_msg="Документ не создан или панель инструментов не отображается",
                )

            if not created_ok:
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
