"""Infrastructure package — reexports для удобства."""

from shared.infra.waits import wait_until, wait_main_proc, wait_window_stable
from shared.infra.screenshots import take_screenshot
from shared.infra.step_helpers import (
    DurationTimer,
    screenshot_path,
    capture_step,
    StepVerifier,
)
from shared.infra.test_runner import CaseRunner
from shared.infra.verification import VerificationResult, build_result, merge_results
from shared.infra.geometry import (
    Rect,
    NormalizedRect,
    rect_from_tuple,
    rect_from_bbox,
    normalize_rect,
    denormalize_rect,
    build_standard_regions,
    normalize_regions,
    relative_anchor,
    anchor_to_point,
    intersection_rect,
    overlap_ratio,
    is_contained,
    is_left_aligned,
    is_below,
)

__all__ = [
    "wait_until",
    "wait_main_proc",
    "wait_window_stable",
    "take_screenshot",
    "DurationTimer",
    "screenshot_path",
    "capture_step",
    "StepVerifier",
    "CaseRunner",
    "VerificationResult",
    "build_result",
    "merge_results",
    "Rect",
    "NormalizedRect",
    "rect_from_tuple",
    "rect_from_bbox",
    "normalize_rect",
    "denormalize_rect",
    "build_standard_regions",
    "normalize_regions",
    "relative_anchor",
    "anchor_to_point",
    "intersection_rect",
    "overlap_ratio",
    "is_contained",
    "is_left_aligned",
    "is_below",
]
