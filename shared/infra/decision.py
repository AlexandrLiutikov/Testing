"""Формирование решения о релизе (§11.2–11.3, DECISION_ENGINE)."""


def build_release_decision(steps: list, case_meta: dict) -> dict:
    failed = [s for s in steps if s["status"] == "FAIL"]
    total = len(steps)
    passed = total - len(failed)

    if not failed:
        return {
            "verdict": "GO",
            "reasons": ["Все шаги пройдены, критический путь покрыт"],
            "risks": [],
            "recommendations": ["Релиз разрешён"],
            "stats": {
                "total": total,
                "passed": passed,
                "failed": len(failed),
                "critical_path_coverage": "1/1",
            },
        }

    worst = max(
        failed,
        key=lambda s: ["LOW", "MEDIUM", "HIGH", "CRITICAL"].index(
            s.get("failure_severity", "MEDIUM")
        ),
    )
    worst_sev = worst.get("failure_severity", "MEDIUM")

    if worst_sev in ("CRITICAL", "HIGH") and case_meta.get("critical_path"):
        verdict = "NO_GO"
    elif worst_sev in ("CRITICAL", "HIGH"):
        verdict = "GO_WITH_RISK"
    elif worst_sev == "MEDIUM":
        verdict = "GO_WITH_RISK"
    else:
        verdict = "GO"

    medium_count = sum(
        1 for f in failed if f.get("failure_severity") == "MEDIUM"
    )
    if medium_count > 3:
        verdict = "NO_GO"

    reasons = []
    risks = []
    recommendations = []

    for f in failed:
        sev = f.get("failure_severity", "MEDIUM")
        area = f.get("failure_area", "CORE_FUNCTION")
        reasons.append(f"Сбой на шаге «{f['step_name']}» (severity {sev})")
        risks.append(f"{sev} — {f.get('failure_detail', f['actual'])} ({area})")

    if verdict == "NO_GO":
        recommendations.append(
            "Релиз заблокирован — требуется исправление критических сбоев"
        )
    elif verdict == "GO_WITH_RISK":
        recommendations.append("Разрешить релиз с учётом р��сков")
        recommendations.append(
            "Создать задачу на исправление выявленных дефектов"
        )
    else:
        recommendations.append("Релиз разрешён")

    return {
        "verdict": verdict,
        "reasons": reasons,
        "risks": risks,
        "recommendations": recommendations,
        "stats": {
            "total": total,
            "passed": passed,
            "failed": len(failed),
            "critical_path_coverage": "1/1" if passed > 0 else "0/1",
        },
    }
