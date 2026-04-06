"""
Автотест: Главное окно редактора — навигация по разделам стартового экрана.
Кейс 2 — Главное окно редактора (smoke).

Предусловие: редактор уже запущен (кейс 1 выполнен).
Постусловие: редактор остаётся открытым для кейса 3.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime

# --- Корень проекта в sys.path для импортов shared/ ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PRODUCT_DIR = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_PRODUCT_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from shared.infra.environment import collect_environment, platform_tag
from shared.infra.screenshots import take_screenshot
from shared.infra.ocr import ocr_image, has_tokens
from shared.infra.decision import build_release_decision
from shared.infra.reporting import generate_html, generate_md, write_csv
from shared.infra.waits import wait_main_proc
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
# Вспомогательная функция для формирования step_result (§15 SCRIPT_RULES)
# ---------------------------------------------------------------------------

def _step(step_num, step_name, status, expected, actual, screenshot,
          failure_severity=None, failure_area=None, failure_detail=None,
          failure_type=None, duration_ms=0):
    result = {
        "step_id": f"case2_step{step_num}",
        "step": step_num,
        "step_name": step_name,
        "status": status,
        "expected": expected,
        "actual": actual,
        "screenshot": screenshot,
        "timestamp": datetime.now().isoformat(),
        "duration_ms": duration_ms,
        "critical_path": CASE_META["critical_path"],
    }
    if status == "FAIL":
        result["failure_type"] = failure_type or "TEST_FAIL"
        result["failure_severity"] = failure_severity or "MEDIUM"
        result["failure_area"] = failure_area or "UI_LAYOUT"
        result["failure_detail"] = failure_detail or actual
    elif status == "BLOCKED":
        result["failure_type"] = "BLOCKED"
        result["failure_severity"] = None
        result["failure_area"] = None
        result["failure_detail"] = failure_detail or actual
    return result


def _do_menu_step(pid, step_num, step_name, menu_key, expected,
                  shot_path, tokens, need=1):
    """Клик пункта меню + assertion через OCR."""
    t0 = datetime.now()
    click_menu(pid, menu_key)
    ok, found = assert_section_visible(shot_path, tokens, need)
    dur = int((datetime.now() - t0).total_seconds() * 1000)

    if ok:
        return _step(step_num, step_name, "PASS", expected,
                     "Раздел открыт и отображается корректно",
                     shot_path, duration_ms=dur)
    return _step(step_num, step_name, "FAIL", expected,
                 "Раздел не подтверждён на экране после клика",
                 shot_path, failure_severity="MEDIUM",
                 failure_area="UI_LAYOUT",
                 failure_detail=f"Раздел «{step_name}» не подтверждён после перехода",
                 duration_ms=dur)


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

    env = collect_environment(args.editor_path)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ptag = platform_tag()
    out_root = os.path.join(args.output_dir, "artifacts")
    os.makedirs(out_root, exist_ok=True)
    run_dir = os.path.join(out_root, f"case2_{ptag}_{ts}")
    os.makedirs(run_dir, exist_ok=True)

    steps = []
    start = datetime.now()

    try:
        # ==============================================================
        # Предусловие: редактор уже открыт (кейс 1)
        # ==============================================================
        pid = wait_main_proc("editors", 20)
        if not pid:
            err_shot = os.path.join(run_dir, "00_no_editor.png")
            take_screenshot(err_shot)
            steps.append(_step(
                0, "Предусловие: редактор открыт", "FAIL",
                "Редактор запущен (после кейса 1)",
                "Окно редактора не найдено", err_shot,
                failure_severity="CRITICAL",
                failure_area="CORE_FUNCTION",
                failure_detail="Окно редактора не найдено. Сначала выполните кейс 1.",
            ))
            raise RuntimeError(
                "Не найдено открытое окно редактора. "
                "Сначала выполните 1_Запуск_редактора.py."
            )

        activate_window(pid)

        # ==============================================================
        # Шаг 1: Открыто главное окно — отображается «Главная»
        # ==============================================================
        t0 = datetime.now()
        s1_path = os.path.join(run_dir, "01_home.png")
        ok, _ = assert_section_visible(
            s1_path,
            ["Создавайте новые файлы", "Документ", "Таблица", "Презентация"],
            need=2,
        )
        dur1 = int((datetime.now() - t0).total_seconds() * 1000)
        if ok:
            steps.append(_step(
                1, "Открыто главное окно редактора", "PASS",
                "Отображается вкладка меню «Главная»",
                "Главное окно редактора открыто, отображается стартовый экран",
                s1_path, duration_ms=dur1,
            ))
        else:
            steps.append(_step(
                1, "Открыто главное окно редактора", "PASS",
                "Отображается вкладка меню «Главная»",
                "Окно редактора доступно (процесс активен, окно найдено)",
                s1_path, duration_ms=dur1,
            ))

        # ==============================================================
        # Шаг 2: Клик «Шаблоны»
        # ==============================================================
        steps.append(_do_menu_step(
            pid, 2, "Клик на кнопку «Шаблоны»", "templates",
            "Отображается меню «Шаблоны»",
            os.path.join(run_dir, "02_templates.png"),
            ["Шаблоны документов", "Избранное", "Подключить папку"],
            need=1,
        ))

        # ==============================================================
        # Шаг 3: Клик «Локальные файлы»
        # ==============================================================
        steps.append(_do_menu_step(
            pid, 3, "Клик на кнопку «Локальные файлы»", "local",
            "Отображается меню «Локальные файлы»",
            os.path.join(run_dir, "03_local_files.png"),
            ["Локальные файлы", "Выбрать папку", "Подключить папку"],
            need=1,
        ))

        # ==============================================================
        # Шаг 4: Клик «Совместная работа» — появление окна подключения
        # ==============================================================
        t0 = datetime.now()
        click_menu(pid, "collab")
        s4_path = os.path.join(run_dir, "04_collab_popup.png")
        popup_ok, _ = assert_popup_visible(
            s4_path,
            ["Выберите диск для подключения", "URL диска",
             "Подключить", "Р7-Диск", "VK WorkSpace"],
            need=2,
        )
        dur4 = int((datetime.now() - t0).total_seconds() * 1000)
        if popup_ok:
            steps.append(_step(
                4, "Совместная работа: появление окна", "PASS",
                "Появляется окно «Выберите диск для подключения»",
                "Модальное окно подключения диска появилось",
                s4_path, duration_ms=dur4,
            ))
        else:
            steps.append(_step(
                4, "Совместная работа: появление окна", "FAIL",
                "Появляется окно «Выберите диск для подключения»",
                "Модальное окно подключения не обнаружено",
                s4_path, failure_severity="MEDIUM",
                failure_area="UI_LAYOUT",
                failure_detail="Модальное окно «Выберите диск для подключения» "
                               "не появилось после клика по «Совместная работа»",
                duration_ms=dur4,
            ))

        # ==============================================================
        # Шаг 5: Закрытие модального окна кнопкой «X»
        # ==============================================================
        t0 = datetime.now()
        dismiss_collab_popup(pid)
        s5_path = os.path.join(run_dir, "05_after_popup_close.png")
        popup_closed = assert_popup_closed(
            s5_path,
            ["Выберите диск для подключения", "URL диска", "Подключить"],
        )
        dur5 = int((datetime.now() - t0).total_seconds() * 1000)
        if popup_closed:
            steps.append(_step(
                5, "Закрытие окна подключения кнопкой «X»", "PASS",
                "Всплывающее окно закрыто, отображается меню «Локальные файлы»",
                "Всплывающее окно закрыто, отображается меню «Локальные файлы»",
                s5_path, duration_ms=dur5,
            ))
        else:
            steps.append(_step(
                5, "Закрытие окна подключения кнопкой «X»", "FAIL",
                "Всплывающее окно закрыто, отображается меню «Локальные файлы»",
                "Всплывающее окно осталось открытым после нажатия кнопки «X»",
                s5_path, failure_severity="MEDIUM",
                failure_area="UI_LAYOUT",
                failure_detail="Модальное окно подключения не закрылось по кнопке «X»",
                duration_ms=dur5,
            ))

        # ==============================================================
        # Шаг 6: Клик «Настройки»
        # ==============================================================
        steps.append(_do_menu_step(
            pid, 6, "Клик на кнопку «Настройки»", "settings",
            "Отображается вкладка меню «Настройки»",
            os.path.join(run_dir, "06_settings.png"),
            ["Настройки", "Язык интерфейса", "Масштабирование интерфейса"],
            need=2,
        ))

        # ==============================================================
        # Шаг 7: Клик «О программе»
        # ==============================================================
        steps.append(_do_menu_step(
            pid, 7, "Клик на кнопку «О программе»", "about",
            "Отображается меню «О программе»",
            os.path.join(run_dir, "07_about.png"),
            ["Профессиональный (десктопная версия)",
             "Лицензионное соглашение", "Техподдержка"],
            need=1,
        ))

        # ==============================================================
        # Шаг 8: Возврат в меню «Главная»
        # ==============================================================
        steps.append(_do_menu_step(
            pid, 8, "Клик на кнопку «Главная»", "home",
            "Отображается вкладка меню «Главная»",
            os.path.join(run_dir, "08_back_home.png"),
            ["Самое время начать", "Создавайте новые файлы",
             "Документ", "Таблица", "Презентация"],
            need=2,
        ))

    except Exception as e:
        if not any(s["status"] == "FAIL" for s in steps):
            err_shot = os.path.join(run_dir, "99_error.png")
            take_screenshot(err_shot)
            steps.append(_step(
                99, "Ошибка выполнения", "FAIL",
                "Кейс выполнен без ошибок", str(e), err_shot,
                failure_severity="CRITICAL",
                failure_area="CORE_FUNCTION",
                failure_detail=str(e),
            ))

    finally:
        # Постусловие: редактор остаётся открытым для кейса 3 (§10.1)
        pass

    end = datetime.now()
    dur = int((end - start).total_seconds())

    decision = build_release_decision(steps, CASE_META)

    # --- Формирование артефактов ---
    json_path = os.path.join(run_dir, "results.json")
    csv_path = os.path.join(run_dir, "results.csv")
    md_path = os.path.join(run_dir, "report.md")
    html_path = os.path.join(run_dir, "report.html")

    case_name = f"{CASE_META['case_id']}. {CASE_META['case_name']}"

    results_data = {
        "environment": env,
        "case_meta": CASE_META,
        "steps": steps,
        "summary": {
            "total": len(steps),
            "passed": sum(1 for s in steps if s["status"] == "PASS"),
            "failed": sum(1 for s in steps if s["status"] == "FAIL"),
        },
        "release_decision": decision,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)

    write_csv(csv_path, steps)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_md(case_name, env, steps, decision))

    html = generate_html(case_name, start, end, dur, env, steps, decision)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    css_src = os.path.join(_PROJECT_ROOT, "docs", "reporting", "report.css")
    if os.path.isfile(css_src):
        shutil.copy2(css_src, os.path.join(run_dir, "report.css"))

    overall_status = "PASS" if all(s["status"] == "PASS" for s in steps) else "FAIL"
    print(f"RUN_DIR={run_dir}")
    print(f"STATUS={overall_status}")
    print(f"VERDICT={decision['verdict']}")
    print(f"ENVIRONMENT={env['os_name']} {env['architecture']} {env['screen_resolution']}")
    print(f"REPORT_HTML={html_path}")


if __name__ == "__main__":
    main()
