"""Формирование решения о релизе по правилам DECISION_ENGINE."""

from typing import Dict, List


_VERDICT_RANK = {"GO": 0, "GO_WITH_RISK": 1, "NO_GO": 2}
_SEV_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def _confidence_from_steps(
    total: int,
    infra_failed: int,
    blocked: int,
    critical_total: int,
    critical_covered: int,
) -> Dict[str, str]:
    """Рассчитать run_confidence по DECISION_ENGINE §9."""
    if total <= 0:
        return {
            "run_confidence": "INSUFFICIENT",
            "run_confidence_detail": "Нет шагов в результате прогона.",
        }

    uncertain = infra_failed + blocked
    ratio = uncertain / total
    uncovered_critical = max(0, critical_total - critical_covered)

    if ratio > 0.5 or uncovered_critical >= 2:
        level = "INSUFFICIENT"
    elif ratio > 0.2 or uncovered_critical == 1:
        level = "DEGRADED"
    elif uncertain > 0:
        level = "SUFFICIENT"
    else:
        level = "FULL"

    detail = (
        f"{uncertain} из {total} шагов имеют статус INFRA_FAIL/BLOCKED; "
        f"critical coverage: {critical_covered}/{critical_total}."
    )
    return {"run_confidence": level, "run_confidence_detail": detail}


def _verdict_for_product_signals(test_fails: List[dict]) -> str:
    """Рассчитать продуктовый вердикт только по TEST_FAIL."""
    if not test_fails:
        return "GO"

    if any(
        f.get("failure_severity") in ("CRITICAL", "HIGH") and f.get("critical_path")
        for f in test_fails
    ):
        return "NO_GO"

    if any(f.get("failure_severity") in ("CRITICAL", "HIGH") for f in test_fails):
        return "GO_WITH_RISK"

    severities = {f.get("failure_severity", "MEDIUM") for f in test_fails}
    if severities == {"LOW"}:
        return "GO"

    medium_count = sum(1 for f in test_fails if f.get("failure_severity") == "MEDIUM")
    if medium_count > 3:
        return "NO_GO"

    return "GO_WITH_RISK"


def _max_verdict(*values: str) -> str:
    return max(values, key=lambda v: _VERDICT_RANK.get(v, 0))


def build_release_decision(steps: list, case_meta: dict) -> dict:
    total = len(steps)
    passed = sum(1 for s in steps if s["status"] == "PASS")

    fails = [s for s in steps if s["status"] == "FAIL"]
    test_fails = [s for s in fails if s.get("failure_type", "TEST_FAIL") == "TEST_FAIL"]
    infra_fails = [s for s in fails if s.get("failure_type") == "INFRA_FAIL"]
    blocked_steps = [s for s in steps if s["status"] == "BLOCKED"]

    critical_total = sum(1 for s in steps if s.get("critical_path"))
    critical_covered = sum(
        1
        for s in steps
        if s.get("critical_path")
        and (s["status"] == "PASS" or (s["status"] == "FAIL" and s.get("failure_type", "TEST_FAIL") == "TEST_FAIL"))
    )

    conf = _confidence_from_steps(
        total=total,
        infra_failed=len(infra_fails),
        blocked=len(blocked_steps),
        critical_total=critical_total,
        critical_covered=critical_covered,
    )
    run_confidence = conf["run_confidence"]
    run_confidence_detail = conf["run_confidence_detail"]

    product_verdict = _verdict_for_product_signals(test_fails)
    coverage_verdict = "GO_WITH_RISK" if critical_covered < critical_total else "GO"

    confidence_verdict = "GO"
    if run_confidence in ("DEGRADED", "INSUFFICIENT"):
        confidence_verdict = "GO_WITH_RISK"

    verdict = _max_verdict(product_verdict, coverage_verdict, confidence_verdict)

    reasons = []
    risks = []
    infra_issues = []
    blocked_cases = []
    warnings = []

    if not test_fails:
        reasons.append("Продуктовых TEST_FAIL не обнаружено.")
    else:
        for f in test_fails:
            sev = f.get("failure_severity", "MEDIUM")
            reasons.append(f"TEST_FAIL: шаг «{f.get('step_name')}» (severity {sev}).")
            area = f.get("failure_area", "CORE_FUNCTION")
            risks.append(
                f"{sev} / {area}: {f.get('failure_detail', f.get('actual', ''))}"
            )

    for f in infra_fails:
        infra_issues.append(
            f"Шаг «{f.get('step_name')}»: {f.get('failure_detail', f.get('actual', ''))}"
        )

    for b in blocked_steps:
        blocked_cases.append(
            f"Шаг «{b.get('step_name')}»: {b.get('failure_detail', b.get('actual', ''))}"
        )

    for s in steps:
        for w in s.get("warnings", []) or []:
            msg = str(w.get("message", "")).strip()
            sev = str(w.get("severity", "LOW")).upper()
            if msg:
                warnings.append(f"{sev}: {msg} (шаг {s.get('step')})")

    if critical_covered < critical_total:
        reasons.append(
            f"Не все critical-path шаги покрыты: {critical_covered}/{critical_total}."
        )
        risks.append("Неполное покрытие критических путей снижает достоверность прогона.")

    reasons.append(f"Run confidence: {run_confidence}. {run_confidence_detail}")

    recommendations = []
    if verdict == "NO_GO":
        recommendations.append("Релиз заблокирован до исправления критических продуктовых сбоев.")
    elif verdict == "GO_WITH_RISK":
        recommendations.append("Разрешить релиз с учётом выявленных рисков.")
    else:
        recommendations.append("Релиз разрешён.")

    if infra_issues or blocked_cases or run_confidence != "FULL":
        recommendations.append("Повторить прогон после устранения инфраструктурных ограничений.")
    if warnings:
        recommendations.append("Обновить UI-каталог/автотесты по зафиксированным предупреждениям.")

    # Удаляем дубли, сохраняя порядок.
    dedup = []
    for item in recommendations:
        if item not in dedup:
            dedup.append(item)
    recommendations = dedup

    worst_test_sev = "NONE"
    if test_fails:
        worst_test_sev = max(
            (f.get("failure_severity", "MEDIUM") for f in test_fails),
            key=lambda s: _SEV_RANK.get(s, 1),
        )

    return {
        "verdict": verdict,
        "reasons": reasons,
        "risks": risks,
        "infra_issues": infra_issues,
        "blocked_cases": blocked_cases,
        "warnings": warnings,
        "recommendations": recommendations,
        "run_confidence": run_confidence,
        "run_confidence_detail": run_confidence_detail,
        "stats": {
            "total": total,
            "passed": passed,
            "test_failed": len(test_fails),
            "infra_failed": len(infra_fails),
            "blocked": len(blocked_steps),
            "warnings_total": sum(len(s.get("warnings", []) or []) for s in steps),
            "critical_path_coverage": f"{critical_covered}/{critical_total}",
            "worst_test_severity": worst_test_sev,
        },
    }
