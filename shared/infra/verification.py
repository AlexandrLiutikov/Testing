"""Reusable verification result model for assertion-layer signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Sequence


@dataclass
class VerificationResult:
    """Structured verification output used by semantic assertions."""

    ok: bool
    sources_used: List[str]
    signal_strength: float
    tolerance_applied: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.signal_strength = max(0.0, min(1.0, float(self.signal_strength)))
        self.sources_used = [str(item) for item in self.sources_used if str(item).strip()]
        self.tolerance_applied = [
            str(item) for item in self.tolerance_applied if str(item).strip()
        ]
        self.evidence = dict(self.evidence or {})

    def __bool__(self) -> bool:
        return self.ok

    def __iter__(self):
        # Backward compatibility for legacy `ok, found = assertion(...)` call sites.
        yield self.ok
        yield self.found_tokens

    @property
    def found_tokens(self) -> List[str]:
        found = self.evidence.get("found_tokens", [])
        if isinstance(found, list):
            return [str(item) for item in found]
        return []


def build_result(
    ok: bool,
    sources_used: Sequence[str],
    signal_strength: float,
    tolerance_applied: Sequence[str] | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> VerificationResult:
    """Build a normalized structured verification result."""
    return VerificationResult(
        ok=bool(ok),
        sources_used=list(sources_used),
        signal_strength=float(signal_strength),
        tolerance_applied=list(tolerance_applied or []),
        evidence=dict(evidence or {}),
    )


def result_from_token_match(
    *,
    source: str,
    ok: bool,
    found_tokens: Iterable[str],
    expected_tokens: Iterable[str],
    need: int,
    tolerance_applied: Sequence[str] | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> VerificationResult:
    """Build VerificationResult from OCR/token matching signal."""
    found = [str(token) for token in (found_tokens or [])]
    expected = [str(token) for token in (expected_tokens or [])]
    denominator = max(int(need or 1), 1)
    coverage = min(1.0, len(found) / float(denominator))
    signal_strength = 1.0 if ok else coverage
    merged_evidence: Dict[str, Any] = {
        "found_tokens": found,
        "expected_tokens": expected,
        "need": int(need or 1),
        "matched_count": len(found),
    }
    if evidence:
        merged_evidence.update(dict(evidence))
    return build_result(
        ok=ok,
        sources_used=[source],
        signal_strength=signal_strength,
        tolerance_applied=tolerance_applied or [],
        evidence=merged_evidence,
    )


def merge_results(
    results: Sequence[VerificationResult],
    *,
    mode: str,
    evidence: Mapping[str, Any] | None = None,
) -> VerificationResult:
    """Merge multiple verification results via all/any semantics."""
    valid = list(results or [])
    if not valid:
        return build_result(
            ok=False,
            sources_used=[],
            signal_strength=0.0,
            evidence={"reason": "EMPTY_RESULTS"},
        )

    if mode not in {"all", "any"}:
        raise ValueError("mode must be 'all' or 'any'")

    ok = all(item.ok for item in valid) if mode == "all" else any(item.ok for item in valid)
    strengths = [float(item.signal_strength) for item in valid]
    signal_strength = (min(strengths) if mode == "all" else max(strengths)) if strengths else 0.0

    sources_used: List[str] = []
    tolerance_applied: List[str] = []
    for item in valid:
        for source in item.sources_used:
            if source not in sources_used:
                sources_used.append(source)
        for tolerance in item.tolerance_applied:
            if tolerance not in tolerance_applied:
                tolerance_applied.append(tolerance)

    merged_evidence: Dict[str, Any] = {
        "mode": mode,
        "components": [item.evidence for item in valid],
        "found_tokens": [token for item in valid for token in item.found_tokens],
    }
    if evidence:
        merged_evidence.update(dict(evidence))

    return build_result(
        ok=ok,
        sources_used=sources_used,
        signal_strength=signal_strength,
        tolerance_applied=tolerance_applied,
        evidence=merged_evidence,
    )
