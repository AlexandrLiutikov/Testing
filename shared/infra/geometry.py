"""Reusable geometry helpers for UI verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple


@dataclass(frozen=True)
class Rect:
    """Rectangle in absolute pixels."""

    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        if self.right <= self.left:
            raise ValueError("right must be greater than left")
        if self.bottom <= self.top:
            raise ValueError("bottom must be greater than top")

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center_x(self) -> int:
        return self.left + self.width // 2

    @property
    def center_y(self) -> int:
        return self.top + self.height // 2

    def to_tuple(self) -> Tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)


@dataclass(frozen=True)
class NormalizedRect:
    """Rectangle normalized relative to a reference rectangle [0..1]."""

    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self) -> None:
        if self.right <= self.left:
            raise ValueError("right must be greater than left")
        if self.bottom <= self.top:
            raise ValueError("bottom must be greater than top")
        for value in (self.left, self.top, self.right, self.bottom):
            if value < 0.0 or value > 1.0:
                raise ValueError("normalized rect coordinates must be in [0..1]")

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
            "center_x": self.center_x,
            "center_y": self.center_y,
        }


def rect_from_tuple(bounds: Tuple[int, int, int, int]) -> Rect:
    return Rect(left=bounds[0], top=bounds[1], right=bounds[2], bottom=bounds[3])


def rect_from_bbox(bbox: Mapping[str, int]) -> Rect:
    left = int(bbox["left"])
    top = int(bbox["top"])
    width = int(bbox["width"])
    height = int(bbox["height"])
    return Rect(left=left, top=top, right=left + width, bottom=top + height)


def normalize_rect(rect: Rect, reference: Rect) -> NormalizedRect:
    ref_w = float(reference.width)
    ref_h = float(reference.height)
    return NormalizedRect(
        left=max(0.0, min(1.0, (rect.left - reference.left) / ref_w)),
        top=max(0.0, min(1.0, (rect.top - reference.top) / ref_h)),
        right=max(0.0, min(1.0, (rect.right - reference.left) / ref_w)),
        bottom=max(0.0, min(1.0, (rect.bottom - reference.top) / ref_h)),
    )


def denormalize_rect(rect: NormalizedRect, reference: Rect) -> Rect:
    return Rect(
        left=int(reference.left + rect.left * reference.width),
        top=int(reference.top + rect.top * reference.height),
        right=int(reference.left + rect.right * reference.width),
        bottom=int(reference.top + rect.bottom * reference.height),
    )


def build_standard_regions(
    window_rect: Rect,
    *,
    toolbar_height_ratio: float = 0.16,
    status_bar_height_ratio: float = 0.06,
    page_margin_x_ratio: float = 0.08,
    page_margin_y_ratio: float = 0.03,
) -> Dict[str, Rect]:
    """Build canonical window regions for editors UI."""
    toolbar_h = max(1, int(window_rect.height * toolbar_height_ratio))
    status_h = max(1, int(window_rect.height * status_bar_height_ratio))

    toolbar = Rect(
        left=window_rect.left,
        top=window_rect.top,
        right=window_rect.right,
        bottom=min(window_rect.bottom - 1, window_rect.top + toolbar_h),
    )
    status_bar = Rect(
        left=window_rect.left,
        top=max(window_rect.top + 1, window_rect.bottom - status_h),
        right=window_rect.right,
        bottom=window_rect.bottom,
    )
    workspace = Rect(
        left=window_rect.left,
        top=toolbar.bottom,
        right=window_rect.right,
        bottom=status_bar.top,
    )

    margin_x = int(workspace.width * page_margin_x_ratio)
    margin_y = int(workspace.height * page_margin_y_ratio)
    page = Rect(
        left=min(workspace.right - 1, workspace.left + margin_x),
        top=min(workspace.bottom - 1, workspace.top + margin_y),
        right=max(workspace.left + 1, workspace.right - margin_x),
        bottom=max(workspace.top + 1, workspace.bottom - margin_y),
    )

    return {
        "window": window_rect,
        "toolbar": toolbar,
        "workspace": workspace,
        "status_bar": status_bar,
        "page": page,
    }


def normalize_regions(regions: Mapping[str, Rect], reference: Rect) -> Dict[str, NormalizedRect]:
    return {name: normalize_rect(rect, reference) for name, rect in regions.items()}


def relative_anchor(rect: Rect, reference: Rect) -> Tuple[float, float]:
    norm = normalize_rect(rect, reference)
    return (norm.center_x, norm.center_y)


def anchor_to_point(anchor_x: float, anchor_y: float, reference: Rect) -> Tuple[int, int]:
    x = int(reference.left + max(0.0, min(1.0, anchor_x)) * reference.width)
    y = int(reference.top + max(0.0, min(1.0, anchor_y)) * reference.height)
    return (x, y)


def intersection_rect(a: Rect, b: Rect) -> Optional[Rect]:
    left = max(a.left, b.left)
    top = max(a.top, b.top)
    right = min(a.right, b.right)
    bottom = min(a.bottom, b.bottom)
    if right <= left or bottom <= top:
        return None
    return Rect(left=left, top=top, right=right, bottom=bottom)


def overlap_ratio(a: Rect, b: Rect, *, relative_to: str = "smaller") -> float:
    """Return overlap ratio between two rectangles."""
    inter = intersection_rect(a, b)
    if inter is None:
        return 0.0
    inter_area = inter.width * inter.height
    area_a = a.width * a.height
    area_b = b.width * b.height
    if relative_to == "a":
        denom = area_a
    elif relative_to == "b":
        denom = area_b
    else:
        denom = min(area_a, area_b)
    return inter_area / float(max(1, denom))


def is_contained(inner: Rect, outer: Rect, *, tolerance_px: int = 0) -> bool:
    return (
        inner.left >= (outer.left - tolerance_px)
        and inner.top >= (outer.top - tolerance_px)
        and inner.right <= (outer.right + tolerance_px)
        and inner.bottom <= (outer.bottom + tolerance_px)
    )


def is_left_aligned(left_rect: Rect, reference_rect: Rect, *, max_offset_ratio: float = 0.08) -> bool:
    offset = left_rect.left - reference_rect.left
    return (offset / float(max(1, reference_rect.width))) <= max_offset_ratio


def is_below(candidate: Rect, anchor: Rect, *, min_gap_px: int = 0) -> bool:
    return candidate.top >= (anchor.bottom + min_gap_px)
