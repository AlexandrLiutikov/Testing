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
        result["failure_severity"] = failure_severity or "HIGH"
        result["failure_area"] = failure_area or "CORE_FUNCTION"
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
                 content_tokens=None, need=1):
    """Клик по вкладке + assertion через OCR по уникальному контенту панели."""
    t0 = datetime.now()
    click_toolbar_tab(pid, tab_name)
    ok, found = assert_tab_active(shot_path, tab_name, content_tokens, need)
    dur = int((datetime.now() - t0).total_seconds() * 1000)

    if ok:
        return _step(step_num, f"Клик по вкладке «{tab_name}»", "PASS",
                     expected,
                     f"Вкладка «{tab_name}» активна, содержимое панели отображается",
                     shot_path, duration_ms=dur)
    return _step(step_num, f"Клик по вкладке «{tab_name}»", "FAIL",
                 expected,
                 f"Вкладка «{tab_name}» не подтверждена на экране после клика",
                 shot_path, failure_severity="HIGH",
                 failure_area="CORE_FUNCTION",
                 failure_detail=f"Вкладка «{tab_name}» не отображается — базовая функция недоступна",
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

        # Ожидание загрузки документа — до 10 сек, минимум 5 сек (§10.5, ТК)
        # Документ должен полностью прогрузиться перед проверкой вкладок.
        pid = wait_main_proc("editors", 10)
        if pid:
            activate_window(pid)

        def _doc_loaded():
            """Проверить что документ прогрузился (лента видна)."""
            take_screenshot(s1_path)
            from shared.infra.ocr import ocr_image, has_tokens as _ht
            text = ocr_image(s1_path)
            ok, _ = _ht(text, ["Обычный", "Без интервала", "Заголовок"], 2)
            return ok

        wait_until(_doc_loaded, timeout_sec=10, poll_interval=1.0)

        ok, found = assert_document_created(
            s1_path,
            tokens=["Обычный", "Без интервала", "Заголовок"],
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
        # Уникальный контент: меню «Сведения», «Сохранить как», «Скачать как»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 2, "Файл",
            "Вкладка «Файл» активна. Открыто меню «Сведения о документе»",
            os.path.join(run_dir, "02_tab_file.png"),
            content_tokens=["Сведения", "Сохранить как", "Скачать как", "Версия"],
            need=2,
        ))

        # ==============================================================
        # Шаг 3: Клик по вкладке «Вставка»
        # Уникальный контент панели: «Таблица», «Изображение», «Диаграмма»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 3, "Вставка",
            "Вкладка «Вставка» активна, подчёркнута синей линией",
            os.path.join(run_dir, "03_tab_insert.png"),
            content_tokens=["Таблица", "Изображение", "Диаграмма", "Колонтитулы"],
            need=2,
        ))

        # ==============================================================
        # Шаг 4: Клик по вкладке «Рисование»
        # Уникальный контент: «Выбрать», «Перо», «Маркер», «Ластик»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 4, "Рисование",
            "Вкладка «Рисование» активна, подчёркнута синей линией",
            os.path.join(run_dir, "04_tab_draw.png"),
            content_tokens=["Выбрать", "Перо", "Маркер", "Ластик"],
            need=1,
        ))

        # ==============================================================
        # Шаг 5: Клик по вкладке «Макет»
        # Уникальный контент: «Поля», «Ориентация», «Размер», «Колонки»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 5, "Макет",
            "Вкладка «Макет» активна, подчёркнута синей линией",
            os.path.join(run_dir, "05_tab_layout.png"),
            content_tokens=["Поля", "Ориентация", "Размер", "Колонки"],
            need=2,
        ))

        # ==============================================================
        # Шаг 6: Клик по вкладке «Ссылки»
        # Уникальный контент: «Оглавление», «Сноска», «Закладка»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 6, "Ссылки",
            "Вкладка «Ссылки» активна, подчёркнута синей линией",
            os.path.join(run_dir, "06_tab_references.png"),
            content_tokens=["Оглавление", "Сноска", "Закладка", "Гиперссылка"],
            need=2,
        ))

        # ==============================================================
        # Шаг 7: Клик по вкладке «Совместная работа»
        # Уникальный контент: «Комментарий», «Сравнить»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 7, "Совместная работа",
            "Вкладка «Совместная работа» активна, подчёркнута синей линией",
            os.path.join(run_dir, "07_tab_collab.png"),
            content_tokens=["Комментарий", "Сравнить"],
            need=1,
        ))

        # ==============================================================
        # Шаг 8: Клик по вкладке «Защита»
        # Уникальный контент: «Зашифровать», «Подпись»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 8, "Защита",
            "Вкладка «Защита» активна, подчёркнута синей линией",
            os.path.join(run_dir, "08_tab_protect.png"),
            content_tokens=["Зашифровать", "Подпись"],
            need=1,
        ))

        # ==============================================================
        # Шаг 9: Клик по вкладке «Вид»
        # Уникальный контент: «Масштаб», «Линейка»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 9, "Вид",
            "Вкладка «Вид» активна, подчёркнута синей линией",
            os.path.join(run_dir, "09_tab_view.png"),
            content_tokens=["Масштаб", "Линейка", "Непечатаемые"],
            need=1,
        ))

        # ==============================================================
        # Шаг 10: Клик по вкладке «Плагины»
        # Уникальный контент: «Макросы», «Менеджер»
        # ==============================================================
        steps.append(_do_tab_step(
            pid, 10, "Плагины",
            "Вкладка «Плагины» активна, подчёркнута синей линией",
            os.path.join(run_dir, "10_tab_plugins.png"),
            content_tokens=["Макросы", "Менеджер"],
            need=1,
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
