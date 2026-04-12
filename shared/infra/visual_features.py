"""Reusable feature-based visual verification primitives.

MVP scope:
- match_template_in_region
- verify_visual_anchor_set
- compare_feature_presence
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from PIL import Image, ImageChops, ImageStat

from shared.infra.geometry import Rect, build_standard_regions, is_contained, rect_from_bbox
from shared.infra.ocr import find_token_bbox
from shared.infra.verification import VerificationResult, build_result

DEFAULT_RISK_MODEL_PATH = "products/Editors/RISK_MODEL.md"
DEFAULT_UI_SHIFT_TOLERANCE_PX = 5


def _read_ui_shift_tolerance_px(
    risk_model_path: str = DEFAULT_RISK_MODEL_PATH,
    default_px: int = DEFAULT_UI_SHIFT_TOLERANCE_PX,
) -> int:
    """Extract ui-shift tolerance from risk model text (e.g. "<= 5px", "≤ 5px")."""
    try:
        text = Path(risk_model_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return int(default_px)

    patterns = (
        r"ui[_\s-]*shift[^0-9]{0,30}[≤<=]+\s*(\d+)\s*px",
        r"смещение[^0-9]{0,30}[≤<=]+\s*(\d+)\s*px",
        r"≤\s*(\d+)\s*px",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                value = int(match.group(1))
                if value >= 0:
                    return value
            except (ValueError, TypeError):
                continue
    return int(default_px)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _resolve_region(
    screenshot_path: str,
    region: str | Rect | Mapping[str, int] | Sequence[int] | None,
    tolerance_px: int,
) -> Rect:
    with Image.open(screenshot_path) as image:
        width, height = image.size

    window = Rect(left=0, top=0, right=width, bottom=height)
    expanded = int(max(0, tolerance_px))

    if region is None:
        base = window
    elif isinstance(region, str):
        regions = build_standard_regions(window)
        base = regions.get(region, window)
    elif isinstance(region, Rect):
        base = region
    elif isinstance(region, Mapping):
        base = Rect(
            left=int(region.get("left", 0)),
            top=int(region.get("top", 0)),
            right=int(region.get("right", width)),
            bottom=int(region.get("bottom", height)),
        )
    elif len(region) == 4:
        base = Rect(
            left=int(region[0]),
            top=int(region[1]),
            right=int(region[2]),
            bottom=int(region[3]),
        )
    else:
        base = window

    return Rect(
        left=_clamp(base.left - expanded, 0, width),
        top=_clamp(base.top - expanded, 0, height),
        right=_clamp(base.right + expanded, 0, width),
        bottom=_clamp(base.bottom + expanded, 0, height),
    )


def _patch_similarity(a: Image.Image, b: Image.Image) -> float:
    """Return [0..1] similarity where 1.0 means exact match."""
    diff = ImageChops.difference(a, b)
    mean = float(ImageStat.Stat(diff).mean[0]) / 255.0
    return max(0.0, min(1.0, 1.0 - mean))


def match_template_in_region(
    screenshot_path: str,
    template_path: str,
    *,
    region: str | Rect | Mapping[str, int] | Sequence[int] | None = None,
    threshold: float = 0.72,
    stride: int = 3,
    risk_model_path: str = DEFAULT_RISK_MODEL_PATH,
) -> VerificationResult:
    """Match a visual template in a region and return confidence-based signal."""
    tolerance_px = _read_ui_shift_tolerance_px(risk_model_path=risk_model_path)
    region_rect = _resolve_region(screenshot_path, region, tolerance_px=tolerance_px)

    if not Path(template_path).is_file():
        return build_result(
            ok=False,
            sources_used=["feature_visual", "template_match"],
            signal_strength=0.0,
            evidence={
                "reason": "TEMPLATE_NOT_FOUND",
                "template_path": template_path,
                "screenshot_path": screenshot_path,
            },
        )

    with Image.open(screenshot_path) as screenshot:
        screenshot_gray = screenshot.convert("L")
        haystack = screenshot_gray.crop(
            (region_rect.left, region_rect.top, region_rect.right, region_rect.bottom)
        )
    with Image.open(template_path) as template:
        needle = template.convert("L")

    if needle.width <= 0 or needle.height <= 0:
        return build_result(
            ok=False,
            sources_used=["feature_visual", "template_match"],
            signal_strength=0.0,
            evidence={
                "reason": "EMPTY_TEMPLATE",
                "template_path": template_path,
            },
        )

    if haystack.width < needle.width or haystack.height < needle.height:
        return build_result(
            ok=False,
            sources_used=["feature_visual", "template_match"],
            signal_strength=0.0,
            evidence={
                "reason": "TEMPLATE_LARGER_THAN_REGION",
                "template_size": [needle.width, needle.height],
                "region_size": [haystack.width, haystack.height],
            },
        )

    step = max(1, int(stride))
    best_confidence = 0.0
    best_point = (region_rect.left, region_rect.top)

    max_y = haystack.height - needle.height
    max_x = haystack.width - needle.width
    for y in range(0, max_y + 1, step):
        for x in range(0, max_x + 1, step):
            patch = haystack.crop((x, y, x + needle.width, y + needle.height))
            confidence = _patch_similarity(patch, needle)
            if confidence > best_confidence:
                best_confidence = confidence
                best_point = (region_rect.left + x, region_rect.top + y)

    matched = best_confidence >= float(threshold)
    left, top = best_point
    best_bbox = {
        "left": left,
        "top": top,
        "right": left + needle.width,
        "bottom": top + needle.height,
    }

    return build_result(
        ok=matched,
        sources_used=["feature_visual", "template_match"],
        signal_strength=best_confidence,
        tolerance_applied=[
            f"ui_shift_px_max={tolerance_px}",
            f"template_match_threshold={threshold}",
            f"template_stride={step}",
        ],
        evidence={
            "confidence": best_confidence,
            "template_path": template_path,
            "region": region if isinstance(region, str) else None,
            "region_bbox": region_rect.to_dict(),
            "best_match_bbox": best_bbox,
            "screenshot_path": screenshot_path,
        },
    )


def compare_feature_presence(
    expected_features: Iterable[str],
    observed_confidence: Mapping[str, float],
    *,
    min_confidence: float = 0.6,
    required_features: Optional[Iterable[str]] = None,
    max_missing_required: int = 0,
) -> VerificationResult:
    """Compare expected feature set against observed confidences."""
    expected = [str(item) for item in expected_features if str(item).strip()]
    required = (
        [str(item) for item in required_features if str(item).strip()]
        if required_features is not None
        else list(expected)
    )

    observed = {str(k): float(v) for k, v in (observed_confidence or {}).items()}
    present = [name for name in expected if observed.get(name, 0.0) >= min_confidence]
    missing_required = [name for name in required if observed.get(name, 0.0) < min_confidence]

    coverage = (len(present) / float(len(expected))) if expected else 0.0
    avg_conf = (
        sum(max(0.0, min(1.0, observed.get(name, 0.0))) for name in expected) / float(len(expected))
        if expected
        else 0.0
    )
    confidence = max(0.0, min(1.0, 0.6 * coverage + 0.4 * avg_conf))
    ok = len(missing_required) <= int(max_missing_required)

    return build_result(
        ok=ok,
        sources_used=["feature_visual", "feature_presence"],
        signal_strength=confidence,
        tolerance_applied=[
            f"feature_min_confidence={min_confidence}",
            f"max_missing_required={int(max_missing_required)}",
        ],
        evidence={
            "expected_features": expected,
            "required_features": required,
            "present_features": present,
            "missing_required_features": missing_required,
            "observed_confidence": observed,
            "coverage_ratio": coverage,
            "average_confidence": avg_conf,
        },
    )


def verify_visual_anchor_set(
    screenshot_path: str,
    anchors: Sequence[Mapping[str, Any]],
    *,
    risk_model_path: str = DEFAULT_RISK_MODEL_PATH,
    min_feature_confidence: float = 0.6,
    max_missing_required: int = 0,
) -> VerificationResult:
    """Verify visual anchors (tokens/templates in expected regions) with confidence."""
    tolerance_px = _read_ui_shift_tolerance_px(risk_model_path=risk_model_path)
    window = _resolve_region(screenshot_path, None, tolerance_px=0)

    expected: List[str] = []
    required: List[str] = []
    observed: Dict[str, float] = {}
    anchor_evidence: List[Dict[str, Any]] = []
    sources: List[str] = ["feature_visual", "visual_anchor_set"]

    for anchor in anchors or []:
        name = str(anchor.get("name", "")).strip()
        if not name:
            continue
        expected.append(name)
        is_required = bool(anchor.get("required", True))
        if is_required:
            required.append(name)

        anchor_region = anchor.get("region")
        region_rect = _resolve_region(screenshot_path, anchor_region, tolerance_px=tolerance_px)
        local_confidence = 0.0
        details: Dict[str, Any] = {
            "name": name,
            "required": is_required,
            "region": anchor_region,
            "region_bbox": region_rect.to_dict(),
            "matched_by": [],
        }

        template_path = anchor.get("template_path")
        if template_path:
            template_result = match_template_in_region(
                screenshot_path,
                str(template_path),
                region=anchor_region,
                threshold=float(anchor.get("threshold", 0.72)),
                stride=int(anchor.get("stride", 3)),
                risk_model_path=risk_model_path,
            )
            local_confidence = max(local_confidence, template_result.signal_strength)
            details["matched_by"].append("template")
            details["template"] = template_result.evidence

        tokens_raw = anchor.get("tokens", [])
        if isinstance(tokens_raw, str):
            tokens = [tokens_raw]
        else:
            tokens = [str(item) for item in tokens_raw if str(item).strip()]
        if tokens:
            needed = max(1, int(anchor.get("need", 1)))
            token_hits: List[str] = []
            for token in tokens:
                bbox = find_token_bbox(screenshot_path, token)
                if not bbox:
                    continue
                token_rect = rect_from_bbox(bbox)
                if not is_contained(token_rect, region_rect, tolerance_px=tolerance_px):
                    continue
                token_hits.append(token)
            token_confidence = min(1.0, len(token_hits) / float(needed))
            local_confidence = max(local_confidence, token_confidence)
            details["matched_by"].append("token")
            details["token_hits"] = token_hits
            details["token_need"] = needed

        observed[name] = max(0.0, min(1.0, local_confidence))
        anchor_evidence.append(details)

    compare_result = compare_feature_presence(
        expected,
        observed,
        min_confidence=min_feature_confidence,
        required_features=required,
        max_missing_required=max_missing_required,
    )

    return build_result(
        ok=compare_result.ok,
        sources_used=list(dict.fromkeys(sources + compare_result.sources_used)),
        signal_strength=compare_result.signal_strength,
        tolerance_applied=list(
            dict.fromkeys(
                compare_result.tolerance_applied + [f"ui_shift_px_max={tolerance_px}"]
            )
        ),
        evidence={
            "anchors": anchor_evidence,
            "expected_features": expected,
            "required_features": required,
            "observed_confidence": observed,
            "presence": compare_result.evidence,
            "screenshot_path": screenshot_path,
            "window_bbox": window.to_dict(),
        },
    )

