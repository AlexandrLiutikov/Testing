"""Генерация отчётов: HTML, MD, CSV (REPORT_STYLE_RULES)."""

import csv
import os
from datetime import datetime


def _signal_strength_ru(value: str) -> str:
    mapping = {
        "STRONG": "СИЛЬНЫЙ",
        "MEDIUM": "СРЕДНИЙ",
        "WEAK": "СЛАБЫЙ",
    }
    key = str(value or "").strip().upper()
    return mapping.get(key, key or "Н/Д")


def _warnings_text(step: dict) -> str:
    warnings = step.get("warnings", []) or []
    fallback_source = step.get("fallback_source")
    fallback_reason = step.get("fallback_reason")
    chunks = []

    for item in warnings:
        sev = str(item.get("severity", "LOW")).upper()
        msg = str(item.get("message", "")).strip()
        if msg:
            chunks.append(f"[{sev}] {msg}")

    if fallback_source:
        fb = f"FALLBACK: {fallback_source}"
        if fallback_reason:
            fb += f" ({fallback_reason})"
        chunks.append(fb)

    sources = step.get("verification_sources", []) or []
    signal_strength = step.get("signal_strength")
    signal_notes = step.get("signal_notes", []) or []
    if signal_strength or sources:
        signal_chunk = "СИГНАЛ"
        if signal_strength:
            signal_chunk += f": {_signal_strength_ru(signal_strength)}"
        if sources:
            signal_chunk += f" через {', '.join(str(s) for s in sources)}"
        chunks.append(signal_chunk)
    for note in signal_notes:
        note_text = str(note).strip()
        if note_text:
            chunks.append(f"ПРИМЕЧАНИЕ СИГНАЛА: {note_text}")

    return " | ".join(chunks)


def _steps_html_rows(steps: list) -> str:
    rows = []
    for s in steps:
        cls_map = {"PASS": "pass", "FAIL": "fail", "BLOCKED": "blocked"}
        cls = cls_map.get(s["status"], "fail")
        sev_cell = ""
        if s["status"] in ("FAIL", "BLOCKED"):
            sev = s.get("failure_severity", "")
            if sev:
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
        wf_cell = _warnings_text(s)
        rows.append(
            f"      <tr>\n"
            f"        <td>{s['step']}</td>\n"
            f"        <td>{s['step_name']}</td>\n"
            f"        <td class='{cls}'>{s['status']}</td>\n"
            f"        <td>{sev_cell}</td>\n"
            f"        <td>{wf_cell}</td>\n"
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
    infra_li = "\n".join(
        f"      <li>{r}</li>" for r in decision.get("infra_issues", [])
    )
    blocked_li = "\n".join(
        f"      <li>{r}</li>" for r in decision.get("blocked_cases", [])
    )
    warns_li = "\n".join(
        f"      <li>{r}</li>" for r in decision.get("warnings", [])
    )
    stats = decision.get("stats", {})
    run_conf = decision.get("run_confidence", "н/д")
    run_conf_detail = decision.get("run_confidence_detail", "")

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
    <div class='decision-section'>
      <strong>INFRA issues:</strong>
      <ul>
{infra_li}
      </ul>
    </div>
    <div class='decision-section'>
      <strong>BLOCKED cases:</strong>
      <ul>
{blocked_li}
      </ul>
    </div>
    <div class='decision-section'>
      <strong>Warnings:</strong>
      <ul>
{warns_li}
      </ul>
    </div>
    <div class='decision-stats'>
      Всего шагов: {stats.get('total', 0)} | PASS: {stats.get('passed', 0)} | TEST_FAIL: {stats.get('test_failed', 0)} | INFRA_FAIL: {stats.get('infra_failed', 0)} | BLOCKED: {stats.get('blocked', 0)} | WARN: {stats.get('warnings_total', 0)} | Критические пути: {stats.get('critical_path_coverage', 'н/д')}
      <br>Run confidence: {run_conf} {run_conf_detail}
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
    blocked = sum(1 for s in steps if s["status"] == "BLOCKED")
    warnings_total = sum(len(s.get("warnings", [])) for s in steps)
    fallback_steps = sum(1 for s in steps if s.get("fallback_source"))
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
    <div>Длительность: {dur} сек</div>
    <div class='env-info'>
      ОС: {env.get('os_name', 'н/д')} | Архитектура: {env.get('architecture', 'н/д')} | Пакет: {env.get('package', 'н/д')}<br>
      Разрешение: {env.get('screen_resolution', 'н/д')} | Масштаб: {env.get('display_scale', 'н/д')} | Версия: {env.get('editor_version', 'н/д')} | Стенд: {env.get('hostname', 'н/д')}
    </div>
    <div>Результат: <span class='badge {badge_cls}'>{overall}</span></div>
    <div>PASS: {passed} | FAIL: {failed} | BLOCKED: {blocked} | WARN: {warnings_total} | FALLBACK_STEPS: {fallback_steps}</div>
  </div>

{_decision_html(decision)}

  <div class='table-wrap'>
  <table class='steps-table'>
    <thead>
      <tr>
        <th>ID</th>
        <th>Шаг</th>
        <th>Статус</th>
        <th>Severity</th>
        <th>Warnings/Fallback</th>
        <th>Ожидание</th>
        <th>Факт</th>
        <th>Скриншот</th>
      </tr>
    </thead>
    <tbody>
{_steps_html_rows(steps)}
    </tbody>
  </table>
  </div>
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
    lines.append("# Отчёт по автотесту R7 Office\n")
    lines.append(f"## Кейс: {case_name}\n")
    lines.append("## Среда\n")
    lines.append(f"- ОС: {env.get('os_name', 'н/д')}")
    lines.append(f"- Архитектура: {env.get('architecture', 'н/д')}")
    lines.append(f"- Пакет: {env.get('package', 'н/д')}")
    lines.append(f"- Разрешение экрана: {env.get('screen_resolution', 'н/д')}")
    lines.append(f"- Масштаб: {env.get('display_scale', 'н/д')}")
    lines.append(f"- Версия редактора: {env.get('editor_version', 'н/д')}")
    lines.append(f"- Стенд: {env.get('hostname', 'н/д')}\n")

    lines.append("## Решение о релизе\n")
    lines.append(f"**{decision['verdict']}**\n")
    for r in decision.get("reasons", []):
        lines.append(f"- {r}")
    if decision.get("infra_issues"):
        lines.append("\n### INFRA issues")
        for item in decision.get("infra_issues", []):
            lines.append(f"- {item}")
    if decision.get("blocked_cases"):
        lines.append("\n### BLOCKED cases")
        for item in decision.get("blocked_cases", []):
            lines.append(f"- {item}")
    if decision.get("warnings"):
        lines.append("\n### Warnings")
        for item in decision.get("warnings", []):
            lines.append(f"- {item}")
    lines.append(f"\n- Run confidence: {decision.get('run_confidence', 'н/д')}")
    if decision.get("run_confidence_detail"):
        lines.append(f"- Детали confidence: {decision.get('run_confidence_detail')}")
    lines.append("")

    lines.append("## Результаты шагов\n")
    lines.append(
        "| Step | Шаг | Статус | Severity | Warnings/Fallback | Ожидание | Факт | Скриншот |"
    )
    lines.append("|------|-----|--------|----------|-------------------|----------|------|----------|")
    for s in steps:
        sev = s.get("failure_severity", "") if s["status"] in ("FAIL", "BLOCKED") else ""
        wf = _warnings_text(s)
        scr = os.path.basename(s["screenshot"]) if s.get("screenshot") else ""
        lines.append(
            f"| {s['step']} | {s['step_name']} | {s['status']} | {sev} | {wf} "
            f"| {s['expected']} | {s['actual']} | {scr} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_csv(csv_path: str, steps: list):
    csv_fields = [
        "step",
        "step_name",
        "status",
        "failure_type",
        "failure_severity",
        "failure_area",
        "fallback_source",
        "fallback_reason",
        "warnings",
        "verification_sources",
        "signal_strength",
        "signal_notes",
        "expected",
        "actual",
        "screenshot",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(steps)
