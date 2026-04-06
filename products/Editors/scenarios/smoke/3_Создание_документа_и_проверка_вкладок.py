"""
Автотест: Создание нового документа и проверка вкладок на панели инструментов.
Кейс 3 — Smoke (Документы).

Предусловие: редактор запущен (кейс 2 выполнен), отображается вкладка «Главная».
Постусловие: редактор остаётся открытым с созданным документом, вкладка «Плагины» активна.
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
from shared.infra.decision import build_release_decision
from shared.infra.reporting import generate_html, generate_md, write_csv
from shared.infra.waits import wait_main_proc, wait_until
from shared.drivers.base import activate_window

from products.Editors.actions.editor_actions import (
    create_document,
    click_toolbar_tab,
)
from products.Editors.assertions.editor_assertions import (
    assert_document_created,
    assert_tab_active,
)


# ---------------------------------------------------------------------------
# Метаданные кейса (§11.1 SCRIPT_RULES)
# ---------------------------------------------------------------------------

CASE_META = {
    "case_id": 3,
    "case_name": "Создание нового документа и проверка вкладок на панели инструментов",
    "area": "Editors/Документы",
    "risk_level": "HIGH",
    "critical_path": True,
}


# ---------------------------------------------------------------------------
# Вспомогательная функция для формирования step_result (§15 SCRIPT_RULES)
# ---------------------------------------------------------------------------

def _step(step_num, step_name, status, expected, actual, screenshot,
          failure_severity=None, failure_area=None, failure_detail=None,
          failure_type=None, duration_ms=0, critical_path=None):
    result = {
        "step_id": f"case3_step{step_num}",
        "step": step_num,
        "step_name": step_name,
        "status": status,
        "expected": expected,
        "actual": actual,
        "screenshot": screenshot,
        "timestamp": datetime.now().isoformat(),
        "duration_ms": duration_ms,
        "critical_path": critical_path if critical_path is not None else CASE_META["critical_path"],
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


# ---------------------------------------------------------------------------
# Шаблон проверки вкладки панели инструментов
# ---------------------------------------------------------------------------

def _do_tab_step(pid, step_num, tab_name, expected, shot_path,
                 extra_tokens=None, need=1):
    """Клик по вкладке + assertion через OCR."""
    t0 = datetime.now()
    click_toolbar_tab(pid, tab_name)
    ok, found = assert_tab_active(shot_path, tab_name, extra_tokens, need)
    dur = int((datetime.now() - t0).total_seconds() * 1000)

    if ok:
        return _step(step_num, f"Клик по вкладке «{tab_name}»", "PASS",
                     expected,
                     f"Вкладка «{tab_name}» активна, содержимое панели отображается",
                     shot_path, duration_ms=dur)
    return _step(step_num, f"Клик по вкладке «{tab_name}»", "FAIL",
                 expected,
                 f"Вкладка «{tab_name}» не подтверждена на экране после клика",
                 shot_path, failure_severity="MEDIUM",
                 failure_area="UI_LAYOUT",
                 failure_detail=f"Вкладка «{tab_name}» не подтверждена после перехода",
                 duration_ms=dur)


# ===========================================================================
# Основной сценарий
# ===========================================================================

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

    env = collect_environment(args.editor_path)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ptag = platform_tag()
    out_root = os.path.join(args.output_dir, "artifacts")
    os.makedirs(out_root, exist_ok=True)
    run_dir = os.path.join(out_root, f"case3_{ptag}_{ts}")
    os.makedirs(run_dir, exist_ok=True)

    steps = []
    start = datetime.now()

    try:
        # ==============================================================
        # Предусловие: редактор уже открыт (кейс 2)
        # ==============================================================
        pid = wait_main_proc("editors", 20)
        if not pid:
            err_shot = os.path.join(run_dir, "00_no_editor.png")
            take_screenshot(err_shot)
            steps.append(_step(
                0, "Предусловие: редактор открыт", "FAIL",
                "Редактор запущен (после кейса 2)",
                "Окно редактора не найдено", err_shot,
                failure_severity="CRITICAL",
                failure_area="CORE_FUNCTION",
                failure_detail="Окно редактора не найдено. Сначала выполните кейсы 1 и 2.",
            ))
            raise RuntimeError(
                "Не найдено открытое окно редактора. "
                "Сначала выполните 1_Запуск_редактора.py и 2_Главное_окно_редактора.py."
            )

        activate_window(pid)

        # ==============================================================
        # Шаг 1: Кликнуть на кнопку «Документ» — создание нового документа
        # Критический путь: создание нового документа
        # ==============================================================
        t0 = datetime.now()
        s1_path = os.path.join(run_dir, "01_new_document.png")

        create_document(pid, "document")

        # Ожидание загрузки документа (§10.5)
        wait_until(lambda: wait_main_proc("editors", 1) is not None, timeout_sec=5)

        pid = wait_main_proc("editors", 10)
        if pid:
            activate_window(pid)

        ok, found = assert_document_created(
            s1_path,
            tokens=["Главная", "Вставка", "Макет", "Рисование"],
            need=2,
        )
        dur1 = int((datetime.now() - t0).total_seconds() * 1000)

        if ok:
            steps.append(_step(
                1, "Создание нового документа", "PASS",
                "Новый документ создан. Вкладка «Главная» активна, подчёркнута синей линией",
                "Новый документ создан. На панели инструментов отображаются вкладки редактора",
                s1_path, duration_ms=dur1, critical_path=True,
            ))
        else:
            steps.append(_step(
                1, "Создание нового документа", "FAIL",
                "Новый документ создан. Вкладка «Главная» активна, подчёркнута синей линией",
                "Документ не создан или панель инструментов не отображается",
                s1_path,
                failure_severity="HIGH",
                failure_area="CORE_FUNCTION",
                failure_detail="Не удалось создать новый документ из стартового экрана",
                duration_ms=dur1, critical_path=True,
            ))
            raise RuntimeError("Не удалось создать новый документ")

        # ==============================================================
        # Шаг 2: Клик по вкладке «Файл»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 2, "Файл",
            "Вкладка «Файл» активна. Открыто меню «Сведения о документе»",
            os.path.join(run_dir, "02_tab_file.png"),
            extra_tokens=["Сведения", "Сохранить", "Скачать"],
            need=1,
        ))

        # ==============================================================
        # Шаг 3: Клик по вкладке «Вставка»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 3, "Вставка",
            "Вкладка «Вставка» активна, подчёркнута синей линией",
            os.path.join(run_dir, "03_tab_insert.png"),
            extra_tokens=["Таблица", "Изображение", "Диаграмма"],
            need=1,
        ))

        # ==============================================================
        # Шаг 4: Клик по вкладке «Рисование»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 4, "Рисование",
            "Вкладка «Рисование» активна, подчёркнута синей линией",
            os.path.join(run_dir, "04_tab_draw.png"),
        ))

        # ==============================================================
        # Шаг 5: Клик по вкладке «Макет»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 5, "Макет",
            "Вкладка «Макет» активна, подчёркнута синей линией",
            os.path.join(run_dir, "05_tab_layout.png"),
            extra_tokens=["Поля", "Ориентация", "Размер"],
            need=1,
        ))

        # ==============================================================
        # Шаг 6: Клик по вкладке «Ссылки»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 6, "Ссылки",
            "Вкладка «Ссылки» активна, подчёркнута синей линией",
            os.path.join(run_dir, "06_tab_references.png"),
            extra_tokens=["Оглавление", "Сноска"],
            need=1,
        ))

        # ==============================================================
        # Шаг 7: Клик по вкладке «Совместная работа»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 7, "Совместная работа",
            "Вкладка «Совместная работа» активна, подчёркнута синей линией",
            os.path.join(run_dir, "07_tab_collab.png"),
        ))

        # ==============================================================
        # Шаг 8: Клик по вкладке «Защита»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 8, "Защита",
            "Вкладка «Защита» активна, подчёркнута синей линией",
            os.path.join(run_dir, "08_tab_protect.png"),
        ))

        # ==============================================================
        # Шаг 9: Клик по вкладке «Вид»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 9, "Вид",
            "Вкладка «Вид» активна, подчёркнута синей линией",
            os.path.join(run_dir, "09_tab_view.png"),
        ))

        # ==============================================================
        # Шаг 10: Клик по вкладке «Плагины»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 10, "Плагины",
            "Вкладка «Плагины» активна, подчёркнута синей линией",
            os.path.join(run_dir, "10_tab_plugins.png"),
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
        # Постусловие: редактор остаётся открытым (§10.1, цепочка кейсов)
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
