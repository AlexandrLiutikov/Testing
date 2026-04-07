"""
Автотест: Создание нового документа и проверка вкладок на панели инструментов.
Кейс 3 — Smoke (Документы).

Предусловие: редактор запущен (после кейса 2), отображается главное окно редактора вкладка «Главная».
Постусловие: редактор остаётся открытым с созданным документом, вкладка
«Плагины» активна (цепочка smoke-прогона).
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
from shared.drivers import get_driver

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


# Уникальное содержимое панелей вкладок — проверяется через OCR.
# Имена вкладок НЕ используются как токены: они видны в ленте всегда.
# (см. память: OCR assertions — check unique panel content)
TABS_PLAN = [
    # (step_num, tab_name, expected, tokens, need)
    (2, "Файл",
     "Вкладка «Файл» активна. Открыто меню «Сведения о документе»",
     ["Сведения", "Сохранить как", "Скачать как", "Версия"], 2),
    (3, "Вставка",
     "Вкладка «Вставка» активна, подчёркнута синей линией",
     ["Таблица", "Изображение", "Диаграмма", "Колонтитулы"], 2),
    (4, "Рисование",
     "Вкладка «Рисование» активна, подчёркнута синей линией",
     ["Выбрать", "Перо", "Маркер", "Ластик"], 1),
    (5, "Макет",
     "Вкладка «Макет» активна, подчёркнута синей линией",
     ["Поля", "Ориентация", "Размер", "Колонки"], 2),
    (6, "Ссылки",
     "Вкладка «Ссылки» активна, подчёркнута синей линией",
     ["Оглавление", "Сноска", "Закладка", "Гиперссылка"], 2),
    (7, "Совместная работа",
     "Вкладка «Совместная работа» активна, подчёркнута синей линией",
     ["Комментарий", "Сравнить"], 1),
    (8, "Защита",
     "Вкладка «Защита» активна, подчёркнута синей линией",
     ["Зашифровать", "Подпись"], 1),
    (9, "Вид",
     "Вкладка «Вид» активна, подчёркнута синей линией",
     ["Масштаб", "Линейка", "Непечатаемые"], 1),
    (10, "Плагины",
     "Вкладка «Плагины» активна, подчёркнута синей линией",
     ["Макросы", "Менеджер"], 1),
]


# ---------------------------------------------------------------------------
# Helper формирования step_result (§15 SCRIPT_RULES)
# ---------------------------------------------------------------------------

def _step(num, name, status, expected, actual, shot,
          failure_severity=None, failure_area=None, failure_detail=None,
          failure_type=None, duration_ms=0):
    r = {
        "step_id": f"case3_step{num}",
        "step": num,
        "step_name": name,
        "status": status,
        "expected": expected,
        "actual": actual,
        "screenshot": shot,
        "timestamp": datetime.now().isoformat(),
        "duration_ms": duration_ms,
        "critical_path": CASE_META["critical_path"],
    }
    if status == "FAIL":
        r["failure_type"] = failure_type or "TEST_FAIL"
        # Smoke-правило: все сбои HIGH (см. память: Smoke severity rule)
        r["failure_severity"] = failure_severity or "HIGH"
        r["failure_area"] = failure_area or "CORE_FUNCTION"
        r["failure_detail"] = failure_detail or actual
    return r


def _tab_step(pid, num, tab_name, expected, shot_path, tokens, need):
    """Клик по вкладке + семантическая проверка через уникальный контент панели."""
    t0 = datetime.now()
    click_toolbar_tab(pid, tab_name)
    ok, _ = assert_tab_active(shot_path, tab_name, tokens, need)
    dur = int((datetime.now() - t0).total_seconds() * 1000)

    if ok:
        return _step(
            num, f"Клик по вкладке «{tab_name}»", "PASS", expected,
            f"Вкладка «{tab_name}» активна, содержимое панели отображается",
            shot_path, duration_ms=dur,
        )
    return _step(
        num, f"Клик по вкладке «{tab_name}»", "FAIL", expected,
        f"Вкладка «{tab_name}» не подтверждена на экране после клика",
        shot_path,
        failure_detail=(
            f"Вкладка «{tab_name}» не отображается — базовая функция "
            f"панели инструментов недоступна"
        ),
        duration_ms=dur,
    )


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
        # ------------------------------------------------------------
        # Предусловие: редактор открыт (кейс 2 выполнен)
        # ------------------------------------------------------------
        pid = wait_main_proc("editors", 20)
        if not pid:
            err_shot = os.path.join(run_dir, "00_no_editor.png")
            take_screenshot(err_shot)
            steps.append(_step(
                0, "Предусловие: редактор открыт", "FAIL",
                "Редактор запущен (после кейса 2)",
                "Окно редактора не найдено", err_shot,
                failure_detail=(
                    "Окно редактора не найдено. "
                    "Сначала выполните кейсы 1 и 2."
                ),
            ))
            raise RuntimeError("Редактор не запущен")

        get_driver().activate_window(pid)

        # ------------------------------------------------------------
        # Шаг 1: Создание нового документа (critical path)
        # Ожидание: до 10 сек на загрузку документа (§10.5, ТК).
        # ------------------------------------------------------------
        t0 = datetime.now()
        s1_path = os.path.join(run_dir, "01_new_document.png")

        create_document(pid, "document")

        # После создания процесс редактора может переключиться — переполучить pid
        new_pid = wait_main_proc("editors", 10)
        if new_pid:
            pid = new_pid
            get_driver().activate_window(pid)

        # Ожидание загрузки документа через семантический assertion
        # Токены, устойчивые к OCR-искажениям и масштабам экрана.
        # «Междустрочный» — заголовок правой панели стилей абзаца, появляется
        # только после создания документа. «Множитель» — её содержимое.
        # «Страница» — индикатор статус-бара документа.
        doc_tokens = ["Междустрочный", "Множитель", "Страница", "Количество"]
        wait_until(
            lambda: assert_document_created(s1_path, tokens=doc_tokens, need=2)[0],
            timeout_sec=10,
            poll_interval=1.0,
        )
        ok, _ = assert_document_created(s1_path, tokens=doc_tokens, need=2)
        dur1 = int((datetime.now() - t0).total_seconds() * 1000)

        if ok:
            steps.append(_step(
                1, "Создание нового документа", "PASS",
                "Новый документ создан. Вкладка «Главная» активна, "
                "подчёркнута синей линией",
                "Новый документ создан. На панели инструментов отображаются "
                "элементы вкладки «Главная»",
                s1_path, duration_ms=dur1,
            ))
        else:
            steps.append(_step(
                1, "Создание нового документа", "FAIL",
                "Новый документ создан. Вкладка «Главная» активна, "
                "подчёркнута синей линией",
                "Документ не создан или панель инструментов не отображается",
                s1_path,
                failure_detail="Не удалось создать новый документ из стартового экрана",
                duration_ms=dur1,
            ))
            raise RuntimeError("Не удалось создать новый документ")

        # ------------------------------------------------------------
        # Шаги 2–10: клик по вкладкам ленты + проверка их содержимого
        # ------------------------------------------------------------
        for num, tab_name, expected, tokens, need in TABS_PLAN:
            shot = os.path.join(run_dir, f"{num:02d}_tab_{num}.png")
            steps.append(_tab_step(pid, num, tab_name, expected, shot, tokens, need))

    except Exception as e:
        if not any(s["status"] == "FAIL" for s in steps):
            err_shot = os.path.join(run_dir, "99_error.png")
            try:
                take_screenshot(err_shot)
            except Exception:
                pass
            steps.append(_step(
                99, "Ошибка выполнения", "FAIL",
                "Кейс выполнен без ошибок", str(e), err_shot,
                failure_detail=str(e),
            ))

    finally:
        # Постусловие (§10.1): редактор остаётся открытым для следующего кейса
        pass

    end = datetime.now()
    dur = int((end - start).total_seconds())

    decision = build_release_decision(steps, CASE_META)

    # --- Артефакты ---
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

    overall_status = "PASS" if steps and all(s["status"] == "PASS" for s in steps) else "FAIL"
    print(f"RUN_DIR={run_dir}")
    print(f"STATUS={overall_status}")
    print(f"VERDICT={decision['verdict']}")
    print(f"ENVIRONMENT={env['os_name']} {env['architecture']} {env['screen_resolution']}")
    print(f"REPORT_HTML={html_path}")


if __name__ == "__main__":
    main()
