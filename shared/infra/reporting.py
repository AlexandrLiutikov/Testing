"""Генерация отчётов: HTML, MD, CSV (REPORT_STYLE_RULES)."""

import csv
import os
from datetime import datetime


def _steps_html_rows(steps: list) -> str:
    rows = []
    for s in steps:
        cls = "pass" if s["status"] == "PASS" else "fail"
        sev_cell = ""
        if s["status"] == "FAIL":
            sev = s.get("failure_severity", "")
            sev_cell = f"<span class='severity {sev.lower()}'>{sev}</span>"
        screenshot_cell = ""
        if s.get("screenshot"):
            fname = os.path.basename(s["screenshot"])
            screenshot_cell = (
                f"<a href='{fname}' target='_blank'>"
                f"<img src='{fname}' alt='{fname}' "
                f"class='screenshot-thumb'>"
                f"</a>"
            )
        rows.append(
            f"      <tr>\n"
            f"        <td>{s['step']}</td>\n"
            f"        <td>{s['step_name']}</td>\n"
            f"        <td class='{cls}'>{s['status']}</td>\n"
            f"        <td>{sev_cell}</td>\n"
            f"        <td>{s['expected']}</td>\n"
            f"        <td>{s['actual']}</td>\n"
            f"        <td>{screenshot_cell}</td>\n"
            f"      </tr>"
        )
    return "\n".join(rows)


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
      <strong>Рекомендац��и:</strong>
      <ul>
{recs_li}
      </ul>
    </div>
    <div class='decision-stats'>
      Всего шагов: {stats.get('total', 0)} | PASS: {stats.get('passed', 0)} | FAIL: {stats.get('failed', 0)} | Критические пути: {stats.get('critical_path_coverage', 'н/д')}
    </div>
  </div>"""


def generate_html(
    case_name: str,
    start: datetime,
    end: datetime,
    dur: int,
    env: dict,
    steps: list,
    decision: dict,
) -> str:
    passed = sum(1 for s in steps if s["status"] == "PASS")
    failed = sum(1 for s in steps if s["status"] == "FAIL")
    overall = "PASS" if failed == 0 else "FAIL"
    badge_cls = "pass" if overall == "PASS" else "fail"

    return f"""<!doctype html>
<html lang='ru'>
<head>
  <meta charset='UTF-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1.0'>
  <title>R7 Office Autotest Report</title>
  <link rel='stylesheet' href='report.css'>
</head>
<body>
  <h1>Отчёт по автотесту R7 Office</h1>
  <div class='meta'>
    <div>Кейс: {case_name}</div>
    <div>Запуск: {start.strftime('%Y-%m-%d %H:%M:%S')}</div>
    <div>Окончание: {end.strftime('%Y-%m-%d %H:%M:%S')}</div>
    <div>Длител��ность: {dur} сек</div>
    <div class='env-info'>
      ОС: {env.get('os_name', 'н/д')} | Архитектура: {env.get('architecture', 'н/д')} | Пакет: {env.get('package', 'н/д')}<br>
      Разрешение: {env.get('screen_resolution', 'н/д')} | Масштаб: {env.get('display_scale', 'н/д')} | Версия: {env.get('editor_version', 'н/д')} | Стенд: {env.get('hostname', 'н/д')}
    </div>
    <div>Результат: <span class='badge {badge_cls}'>{overall}</span></div>
    <div>PASS: {passed} | FAIL: {failed}</div>
  </div>

{_decision_html(decision)}

  <table>
    <thead>
      <tr>
        <th>Step</th>
        <th>Шаг</th>
        <th>Статус</th>
        <th>Severity</th>
        <th>Ожидание</th>
        <th>Факт</th>
        <th>Скриншот</th>
      </tr>
    </thead>
    <tbody>
{_steps_html_rows(steps)}
    </tbody>
  </table>
  <div class='footer'>
    JSON: results.json |
    CSV: results.csv |
    MD: report.md
  </div>
</body>
</html>"""


def generate_md(
    case_name: str,
    env: dict,
    steps: list,
    decision: dict,
) -> str:
    lines = []
    lines.append("# Отчёт п�� автотесту R7 Office\n")
    lines.append(f"## Кейс: {case_name}\n")
    lines.append("## Среда\n")
    lines.append(f"- ОС: {env.get('os_name', 'н/д')}")
    lines.append(f"- Архитектур��: {env.get('architecture', 'н/д')}")
    lines.append(f"- Пакет: {env.get('package', 'н/д')}")
    lines.append(f"- Разрешение ��крана: {env.get('screen_resolution', 'н/д')}")
    lines.append(f"- Масштаб: {env.get('display_scale', 'н/д')}")
    lines.append(f"- Версия редактора: {env.get('editor_version', 'н/д')}")
    lines.append(f"- Стенд: {env.get('hostname', 'н/д')}\n")

    lines.append("## Решение о р��лизе\n")
    lines.append(f"**{decision['verdict']}**\n")
    for r in decision.get("reasons", []):
        lines.append(f"- {r}")
    lines.append("")

    lines.append("## Результаты шагов\n")
    lines.append(
        "| Step | Шаг | Статус | Severity | Ожидание | Факт | ��криншот |"
    )
    lines.append("|------|-----|--------|----------|----------|------|----------|")
    for s in steps:
        sev = s.get("failure_severity", "") if s["status"] == "FAIL" else ""
        scr = os.path.basename(s["screenshot"]) if s.get("screenshot") else ""
        lines.append(
            f"| {s['step']} | {s['step_name']} | {s['status']} | {sev} "
            f"| {s['expected']} | {s['actual']} | {scr} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_csv(csv_path: str, steps: list):
    csv_fields = [
        "step", "step_name", "status", "expected", "actual", "screenshot",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(steps)
