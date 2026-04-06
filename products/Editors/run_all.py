"""
Оркестратор запуска тест-кейсов R7 Office Editors.

Запускает указанные кейсы последовательно (цепочка), агрегирует результаты
и формирует сводный отчёт с RELEASE_DECISION.

Использование:
    python run_all.py                         # кейсы 1,2 (по умолчанию)
    python run_all.py --cases 1 2             # только кейсы 1 и 2
    python run_all.py --cases 1 2 --editor-path "C:\\path\\to\\editors.exe"
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# --- Корень проекта ---
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.infra.environment import collect_environment, platform_tag

# ---------------------------------------------------------------------------
# Карта кейсов: id → относительный путь скрипта (от products/Editors)
# ---------------------------------------------------------------------------

CASE_SCRIPTS = {
    "1": os.path.join("scenarios", "smoke", "1_Запуск_редактора.py"),
    "2": os.path.join("scenarios", "smoke", "2_Главное_окно_редактора.py"),
}

AVAILABLE_CASES = sorted(CASE_SCRIPTS.keys())

# ---------------------------------------------------------------------------
# Парсинг stdout кейса
# ---------------------------------------------------------------------------

_KV_RE = re.compile(r"^(RUN_DIR|STATUS|VERDICT|REPORT_HTML|ENVIRONMENT)=(.+)$", re.M)


def _parse_output(raw: str) -> dict:
    """Извлекает ключевые переменные из stdout кейса."""
    result = {}
    for m in _KV_RE.finditer(raw):
        result[m.group(1)] = m.group(2).strip()
    return result


# ---------------------------------------------------------------------------
# Агрегация RELEASE_DECISION
# ---------------------------------------------------------------------------

_VERDICT_RANK = {"GO": 0, "GO_WITH_RISK": 1, "NO_GO": 2}
_VERDICT_BY_RANK = {v: k for k, v in _VERDICT_RANK.items()}


def _aggregate_decision(case_results: list) -> dict:
    """Сводное решение = наихудший вердикт из кейсов (DECISION_ENGINE §6)."""
    verdicts = [r.get("verdict", "GO") for r in case_results]
    worst_rank = max(_VERDICT_RANK.get(v, 0) for v in verdicts)
    overall = _VERDICT_BY_RANK[worst_rank]

    reasons = []
    risks = []
    recommendations = []
    total_pass = 0
    total_fail = 0
    total_cases = len(case_results)

    for r in case_results:
        cid = r["case_id"]
        v = r.get("verdict", "GO")
        s = r.get("status", "PASS")
        if s == "PASS":
            total_pass += 1
        else:
            total_fail += 1

        if v != "GO":
            reasons.append(
                f"Кейс {cid} ({r['case_name']}): {v} — {r.get('fact', '')}"
            )
            risks.append(f"Кейс {cid}: вердикт {v}")
        else:
            reasons.append(f"Кейс {cid} ({r['case_name']}): PASS")

    if overall == "NO_GO":
        recommendations.append(
            "Релиз заблокирован — требуется исправление критических сбоев"
        )
    elif overall == "GO_WITH_RISK":
        recommendations.append("Разрешить релиз с учётом рисков")
        recommendations.append("Создать задачу на исправление выявленных дефектов")
    else:
        recommendations.append("Релиз разрешён")

    return {
        "verdict": overall,
        "reasons": reasons,
        "risks": risks,
        "recommendations": recommendations,
        "stats": {
            "total_cases": total_cases,
            "passed": total_pass,
            "failed": total_fail,
            "critical_path_coverage": f"{total_pass}/{total_cases}",
        },
    }


# ---------------------------------------------------------------------------
# Генерация сводного HTML (REPORT_STYLE_RULES §13)
# ---------------------------------------------------------------------------


def _decision_html(decision: dict) -> str:
    verdict = decision["verdict"]
    css_map = {"GO": "go", "GO_WITH_RISK": "go-with-risk", "NO_GO": "no-go"}
    css_cls = css_map.get(verdict, "go")

    reasons_li = "\n".join(
        f"      <li>{r}</li>" for r in decision.get("reasons", [])
    )
    risks_li = "\n".join(
        f"      <li>{r}</li>" for r in decision.get("risks", [])
    )
    recs_li = "\n".join(
        f"      <li>{r}</li>" for r in decision.get("recommendations", [])
    )
    stats = decision.get("stats", {})

    return f"""  <div class='decision {css_cls}'>
    <div class='decision-badge {css_cls}'>RELEASE DECISION: {verdict}</div>
    <div class='decision-section'>
      <strong>Обоснование:</strong>
      <ul>
{reasons_li}
      </ul>
    </div>
    <div class='decision-section'>
      <strong>Риски:</strong>
      <ul>
{risks_li}
      </ul>
    </div>
    <div class='decision-section'>
      <strong>Рекомендации:</strong>
      <ul>
{recs_li}
      </ul>
    </div>
    <div class='decision-stats'>
      Всего кейсов: {stats.get('total_cases', 0)} | PASS: {stats.get('passed', 0)} | FAIL: {stats.get('failed', 0)} | Критические пути: {stats.get('critical_path_coverage', 'н/д')}
    </div>
  </div>"""


def _case_rows_html(case_results: list) -> str:
    rows = []
    for r in case_results:
        status_cls = "pass" if r["status"] == "PASS" else "fail"
        verdict = r.get("verdict", "")
        verdict_cls = {"GO": "go", "GO_WITH_RISK": "go-with-risk", "NO_GO": "no-go"}.get(verdict, "")

        report_link = ""
        if r.get("report_html"):
            report_link = f"<a href='file:///{r['report_html'].replace(chr(92), '/')}' target='_blank'>Открыть отчёт кейса</a>"

        run_dir_text = r.get("run_dir", "-") or "-"
        log_link = ""
        if r.get("log_file"):
            log_link = f"<br><a href='{os.path.basename(r['log_file'])}' class='log-link'>Лог</a>"

        rows.append(
            f"      <tr>\n"
            f"        <td>{r['case_id']}</td>\n"
            f"        <td>{r['case_name']}</td>\n"
            f"        <td class='{status_cls}'>{r['status']}</td>\n"
            f"        <td><span class='verdict-cell {verdict_cls}'>{verdict}</span></td>\n"
            f"        <td>{r.get('fact', '')}</td>\n"
            f"        <td>{run_dir_text}</td>\n"
            f"        <td>{report_link}{log_link}</td>\n"
            f"      </tr>"
        )
    return "\n".join(rows)


def _generate_summary_html(
    start: datetime,
    end: datetime,
    dur: int,
    env: dict,
    case_results: list,
    decision: dict,
) -> str:
    total = len(case_results)
    passed = sum(1 for r in case_results if r["status"] == "PASS")
    failed = total - passed
    overall = "PASS" if failed == 0 else "FAIL"
    badge_cls = "pass" if overall == "PASS" else "fail"

    return f"""<!doctype html>
<html lang='ru'>
<head>
  <meta charset='UTF-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1.0'>
  <title>R7 Office — Сводный отчёт</title>
  <link rel='stylesheet' href='report.css'>
  <link rel='stylesheet' href='report_all.css'>
</head>
<body>
  <h1>Сводный отчёт по запуску тест-кейсов R7 Office</h1>

  <div class='meta'>
    <div>Запуск: {start.strftime('%Y-%m-%d %H:%M:%S')}</div>
    <div>Окончание: {end.strftime('%Y-%m-%d %H:%M:%S')}</div>
    <div>Длительность: {dur} сек</div>
    <div class='env-info'>
      ОС: {env.get('os_name', 'н/д')} | Архитектура: {env.get('architecture', 'н/д')} | Пакет: {env.get('package', 'н/д')}<br>
      Разрешение: {env.get('screen_resolution', 'н/д')} | Масштаб: {env.get('display_scale', 'н/д')} | Версия: {env.get('editor_version', 'н/д')} | Стенд: {env.get('hostname', 'н/д')}
    </div>
    <div>Результат: <span class='badge {badge_cls}'>{overall}</span></div>
  </div>

  <div class='summary-grid'>
    <div class='summary-card'>
      <span class='number'>{total}</span>
      <span class='label'>Кейсов запущено</span>
    </div>
    <div class='summary-card'>
      <span class='number pass-num'>{passed}</span>
      <span class='label'>PASS</span>
    </div>
    <div class='summary-card'>
      <span class='number fail-num'>{failed}</span>
      <span class='label'>FAIL</span>
    </div>
  </div>

{_decision_html(decision)}

  <table class='cases-table'>
    <thead>
      <tr>
        <th>Кейс</th>
        <th>Скрипт</th>
        <th>Статус</th>
        <th>Вердикт</th>
        <th>Факт</th>
        <th>Папка прогона</th>
        <th>Детальный отчёт</th>
      </tr>
    </thead>
    <tbody>
{_case_rows_html(case_results)}
    </tbody>
  </table>

  <div class='footer'>
    JSON: results_all.json | CSV: results_all.csv
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Основная логика
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Оркестратор запуска тест-кейсов R7 Office Editors",
    )
    parser.add_argument(
        "--cases",
        nargs="+",
        default=AVAILABLE_CASES,
        help=f"Номера кейсов для запуска (доступны: {', '.join(AVAILABLE_CASES)})",
    )
    parser.add_argument(
        "--editor-path",
        default=r"C:\Program Files\R7-Office\Editors\DesktopEditors.exe",
        help="Путь к исполняемому файлу редактора",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_SCRIPT_DIR),
        help="Корневой каталог для артефактов",
    )
    args = parser.parse_args()

    # --- Валидация кейсов ---
    for c in args.cases:
        if c not in CASE_SCRIPTS:
            print(
                f"ОШИБКА: Неизвестный кейс: {c}. Разрешены: {', '.join(AVAILABLE_CASES)}.",
                file=sys.stderr,
            )
            sys.exit(1)

    # --- Подготовка каталога прогона ---
    ptag = platform_tag()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    artifacts_root = os.path.join(args.output_dir, "artifacts")
    os.makedirs(artifacts_root, exist_ok=True)
    multi_dir = os.path.join(artifacts_root, f"multi_{ptag}_{ts}")
    os.makedirs(multi_dir, exist_ok=True)

    env = collect_environment(args.editor_path)

    start = datetime.now()
    case_results = []

    # --- Последовательный запуск кейсов (цепочка) ---
    python_exe = sys.executable

    for case_id in args.cases:
        script_rel = CASE_SCRIPTS[case_id]
        script_path = os.path.join(str(_SCRIPT_DIR), script_rel)

        case_name = os.path.splitext(os.path.basename(script_rel))[0]

        if not os.path.isfile(script_path):
            case_results.append({
                "case_id": case_id,
                "case_name": case_name,
                "status": "FAIL",
                "verdict": "NO_GO",
                "exit_code": 1,
                "run_dir": "",
                "report_html": "",
                "log_file": "",
                "fact": f"Файл скрипта не найден: {script_path}",
            })
            continue

        cmd = [
            python_exe, script_path,
            "--editor-path", args.editor_path,
            "--output-dir", args.output_dir,
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                encoding="utf-8",
                errors="replace",
            )
            raw_output = proc.stdout + "\n" + proc.stderr
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            raw_output = ""
            exit_code = -1
        except Exception as e:
            raw_output = str(e)
            exit_code = -2

        # Сохранение лога
        log_path = os.path.join(multi_dir, f"case{case_id}.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(raw_output)

        parsed = _parse_output(raw_output)

        status = parsed.get("STATUS", "")
        if not status:
            status = "PASS" if exit_code == 0 else "FAIL"
        if exit_code != 0:
            status = "FAIL"

        verdict = parsed.get("VERDICT", "GO" if status == "PASS" else "NO_GO")

        fact = (
            "Кейс выполнен успешно."
            if status == "PASS"
            else "Кейс завершился с ошибкой. Подробности в логе."
        )

        case_results.append({
            "case_id": case_id,
            "case_name": case_name,
            "status": status,
            "verdict": verdict,
            "exit_code": exit_code,
            "run_dir": parsed.get("RUN_DIR", ""),
            "report_html": parsed.get("REPORT_HTML", ""),
            "log_file": log_path,
            "fact": fact,
        })

    end = datetime.now()
    dur = int((end - start).total_seconds())

    # --- Одиночный кейс: упрощённый вывод ---
    if len(args.cases) == 1:
        single = case_results[0]
        print(f"CASES_RUN=1")
        print(f"CASE_ID={single['case_id']}")
        print(f"RESULT={single['status']}")
        print(f"VERDICT={single['verdict']}")
        if single["run_dir"]:
            print(f"RUN_DIR={single['run_dir']}")
        if single["report_html"]:
            print(f"REPORT_HTML={single['report_html']}")
        print("AGGREGATE_REPORT=SKIPPED")
        sys.exit(0)

    # --- Агрегация и сводный отчёт ---
    decision = _aggregate_decision(case_results)

    # JSON
    json_path = os.path.join(multi_dir, "results_all.json")
    json_data = {
        "environment": env,
        "cases": case_results,
        "summary": {
            "total_cases": len(case_results),
            "passed": sum(1 for r in case_results if r["status"] == "PASS"),
            "failed": sum(1 for r in case_results if r["status"] != "PASS"),
        },
        "release_decision": decision,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    # CSV
    csv_path = os.path.join(multi_dir, "results_all.csv")
    csv_fields = ["case_id", "case_name", "status", "verdict", "exit_code", "run_dir", "report_html", "fact"]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(case_results)

    # HTML
    html_path = os.path.join(multi_dir, "report_all.html")
    html = _generate_summary_html(start, end, dur, env, case_results, decision)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Копирование CSS в каталог прогона
    css_src = os.path.join(str(_PROJECT_ROOT), "docs", "reporting", "report.css")
    css_all_src = os.path.join(str(_PROJECT_ROOT), "docs", "reporting", "report_all.css")
    if os.path.isfile(css_src):
        shutil.copy2(css_src, os.path.join(multi_dir, "report.css"))
    if os.path.isfile(css_all_src):
        shutil.copy2(css_all_src, os.path.join(multi_dir, "report_all.css"))

    # --- Stdout ---
    overall = decision["verdict"]
    pass_count = sum(1 for r in case_results if r["status"] == "PASS")
    fail_count = len(case_results) - pass_count

    print(f"CASES_RUN={len(case_results)}")
    print(f"OVERALL_RESULT={'PASS' if fail_count == 0 else 'FAIL'}")
    print(f"OVERALL_VERDICT={overall}")
    print(f"PASS={pass_count} FAIL={fail_count}")
    print(f"RUN_DIR={multi_dir}")
    print(f"REPORT_HTML={html_path}")


if __name__ == "__main__":
    main()
