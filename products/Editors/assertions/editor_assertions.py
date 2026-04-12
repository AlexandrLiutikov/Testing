"""Semantic assertions для Editors — продуктовый слой (§16, §17 SCRIPT_RULES).

Assertions — это проверяющие функции, которые:
1. Делают скриншот
2. Выполняют проверку (через OCR или делегируя actions)
3. Возвращают структурированный VerificationResult
"""

import os
from typing import List, Optional

from shared.infra.ocr import find_token_bbox, has_tokens, ocr_image
from shared.infra.geometry import (
    Rect,
    build_standard_regions,
    is_below,
    is_contained,
    is_left_aligned,
    normalize_rect,
    overlap_ratio,
    rect_from_bbox,
)
from shared.infra.model_loader import load_yaml_model
from shared.infra.screenshots import take_screenshot
from shared.infra.verification import (
    VerificationResult,
    build_result,
    merge_results,
    result_from_token_match,
)
from shared.infra.waits import wait_main_proc

from products.Editors.actions.editor_actions import detect_warning_window

_REFERENCE_DOC_MODEL = load_yaml_model("products/Editors/models/docs/reference_docx.yaml")

SMOKE_TEXT_ASSERT_TOKENS = list(_REFERENCE_DOC_MODEL.get("smoke_text_assert_tokens", []))
REFERENCE_DOC_OPEN_TOKENS = list(_REFERENCE_DOC_MODEL.get("open_tokens", []))
REFERENCE_DOC_PAGE_TOKENS = {
    int(page): list(tokens)
    for page, tokens in (_REFERENCE_DOC_MODEL.get("page_tokens", {}) or {}).items()
}
REFERENCE_DOC_PAGE_FULL_VIEW_MARKERS = {
    int(page): {
        "top": list((markers or {}).get("top", [])),
        "bottom": list((markers or {}).get("bottom", [])),
    }
    for page, markers in (_REFERENCE_DOC_MODEL.get("full_view_markers", {}) or {}).items()
}
REFERENCE_DOC_TOLERANCES = dict(_REFERENCE_DOC_MODEL.get("tolerances", {}))
_REFERENCE_DOC_LAYOUT_TOLERANCES = REFERENCE_DOC_TOLERANCES.get("layout", {})
DEFAULT_FULL_VIEW_TOP_MAX_RATIO = float(
    _REFERENCE_DOC_LAYOUT_TOLERANCES.get("full_view_top_max_ratio", 0.45)
)
DEFAULT_FULL_VIEW_BOTTOM_MIN_RATIO = float(
    _REFERENCE_DOC_LAYOUT_TOLERANCES.get("full_view_bottom_min_ratio", 0.55)
)


def _image_rect(screenshot_path: str) -> Rect:
    from PIL import Image

    with Image.open(screenshot_path) as image:
        width, height = image.size
    return Rect(left=0, top=0, right=width, bottom=height)


def _image_regions(screenshot_path: str) -> dict:
    return build_standard_regions(_image_rect(screenshot_path))


def _first_token_rect(screenshot_path: str, tokens: List[str]) -> Optional[tuple]:
    for token in tokens:
        bbox = find_token_bbox(screenshot_path, token)
        if bbox:
            return token, rect_from_bbox(bbox)
    return None


def assert_window_exists(
    process_name: str = "editors",
    timeout_sec: int = 20,
) -> VerificationResult:
    """Проверить, что окно редактора появилось (поиск процесса + ожидание)."""
    pid = wait_main_proc(process_name, timeout_sec)
    return build_result(
        ok=pid is not None,
        sources_used=["ui_process_state"],
        signal_strength=1.0 if pid else 0.0,
        evidence={"pid": pid, "process_name": process_name, "timeout_sec": timeout_sec},
    )


def assert_reference_document_opened(
    screenshot_path: str,
) -> VerificationResult:
    """Проверить, что открыт эталонный документ по содержимому первой страницы."""
    return assert_section_visible(
        screenshot_path,
        REFERENCE_DOC_OPEN_TOKENS,
        need=2,
    )


def assert_reference_document_page_content(
    screenshot_path: str,
    page_index: int,
    capture: bool = True,
) -> VerificationResult:
    """Проверить содержимое конкретной страницы эталонного документа."""
    tokens = REFERENCE_DOC_PAGE_TOKENS.get(page_index, [])
    if not tokens:
        if capture:
            take_screenshot(screenshot_path)
        return build_result(
            ok=False,
            sources_used=["semantic_content_model"],
            signal_strength=0.0,
            evidence={
                "found_tokens": [],
                "page_index": page_index,
                "reason": "PAGE_TOKENS_UNDEFINED",
            },
        )
    page_tokens = [
        t for t in tokens
        if str(t).strip().lower().startswith("страница ")
    ]
    content_tokens = [
        t for t in tokens
        if not str(t).strip().lower().startswith("страница ")
    ]

    # Для страниц 2-3 запрещаем PASS по одному лишь номеру страницы из статус-бара:
    # нужен контент этой страницы.
    if page_index in (2, 3):
        probe = content_tokens or tokens
        result = assert_section_visible(screenshot_path, probe, need=1)
        result.sources_used.insert(0, "semantic_content_model")
        result.evidence["page_index"] = page_index
        return result

    # Страница 4 в эталоне почти пустая, OCR контента нестабилен.
    # Сначала пробуем контент, затем fallback на маркер "Страница 4 из 4".
    if page_index == 4:
        probe = content_tokens or tokens
        primary = assert_section_visible(screenshot_path, probe, need=1)
        primary.sources_used.append("semantic_content_model")
        primary.evidence["page_index"] = page_index
        if primary.ok:
            return primary
        if page_tokens:
            fallback = assert_section_visible(screenshot_path, page_tokens, need=1)
            fallback.sources_used.extend(["semantic_content_model", "ocr_fallback"])
            fallback.tolerance_applied.append("PAGE4_STATUS_BAR_FALLBACK")
            fallback.evidence["page_index"] = page_index
            return fallback
        return primary

    if capture:
        take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    # Для страниц 2-3 запрещаем PASS только по токенам статус-бара.
    if page_index in (2, 3):
        probe = content_tokens or tokens
        ok, found = has_tokens(ocr_text, probe, need=1)
        return result_from_token_match(
            source="semantic_content_model",
            ok=ok,
            found_tokens=found,
            expected_tokens=probe,
            need=1,
            evidence={"page_index": page_index},
        )

    # Страница 4 может быть почти пустой: сначала ищем контент, затем page-token.
    if page_index == 4:
        probe = content_tokens or tokens
        ok, found = has_tokens(ocr_text, probe, need=1)
        primary = result_from_token_match(
            source="semantic_content_model",
            ok=ok,
            found_tokens=found,
            expected_tokens=probe,
            need=1,
            evidence={"page_index": page_index},
        )
        if primary.ok:
            return primary
        if page_tokens:
            ok2, found2 = has_tokens(ocr_text, page_tokens, need=1)
            fallback = result_from_token_match(
                source="ocr_fallback",
                ok=ok2,
                found_tokens=found2,
                expected_tokens=page_tokens,
                need=1,
                tolerance_applied=["PAGE4_STATUS_BAR_FALLBACK"],
                evidence={"page_index": page_index},
            )
            if not fallback.evidence.get("found_tokens"):
                fallback.evidence["found_tokens"] = primary.found_tokens
            return fallback
        return primary

    ok, found = has_tokens(ocr_text, tokens, need=1)
    return result_from_token_match(
        source="semantic_content_model",
        ok=ok,
        found_tokens=found,
        expected_tokens=tokens,
        need=1,
        evidence={"page_index": page_index},
    )


def assert_reference_document_page_full_view(
    screenshot_path: str,
    page_index: int,
    capture: bool = True,
    top_max_ratio: float = DEFAULT_FULL_VIEW_TOP_MAX_RATIO,
    bottom_min_ratio: float = DEFAULT_FULL_VIEW_BOTTOM_MIN_RATIO,
) -> VerificationResult:
    """Проверить, что страница отображается целиком (верх+низ страницы видны)."""
    markers = REFERENCE_DOC_PAGE_FULL_VIEW_MARKERS.get(page_index)
    if not markers:
        if capture:
            take_screenshot(screenshot_path)
        return build_result(
            ok=False,
            sources_used=["geometry"],
            signal_strength=0.0,
            evidence={
                "found_tokens": [],
                "page_index": page_index,
                "reason": "FULL_VIEW_MARKERS_UNDEFINED",
            },
        )

    result = assert_full_page_visible(
        screenshot_path=screenshot_path,
        top_tokens=list(markers.get("top", [])),
        bottom_tokens=list(markers.get("bottom", [])),
        capture=capture,
        top_max_ratio=top_max_ratio,
        bottom_min_ratio=bottom_min_ratio,
    )
    result.evidence["page_index"] = page_index
    return result


def assert_element_in_region(
    screenshot_path: str,
    token: str,
    region_name: str = "workspace",
    capture: bool = True,
    tolerance_px: int = 0,
) -> VerificationResult:
    """Проверить, что OCR-элемент находится внутри заданного канонического региона."""
    if capture:
        take_screenshot(screenshot_path)
    regions = _image_regions(screenshot_path)
    if region_name not in regions:
        return build_result(
            ok=False,
            sources_used=["geometry"],
            signal_strength=0.0,
            evidence={"reason": "UNKNOWN_REGION", "region_name": region_name},
        )

    bbox = find_token_bbox(screenshot_path, token)
    if not bbox:
        return build_result(
            ok=False,
            sources_used=["geometry", "feature_visual"],
            signal_strength=0.0,
            evidence={"reason": "TOKEN_NOT_FOUND", "token": token, "region_name": region_name},
        )

    element_rect = rect_from_bbox(bbox)
    region_rect = regions[region_name]
    ok = is_contained(element_rect, region_rect, tolerance_px=tolerance_px)
    return build_result(
        ok=ok,
        sources_used=["geometry", "feature_visual"],
        signal_strength=1.0 if ok else overlap_ratio(element_rect, region_rect, relative_to="a"),
        tolerance_applied=[f"containment_tolerance_px={tolerance_px}"],
        evidence={
            "token": token,
            "region_name": region_name,
            "element_bbox": bbox,
            "region_bbox": {
                "left": region_rect.left,
                "top": region_rect.top,
                "right": region_rect.right,
                "bottom": region_rect.bottom,
            },
            "element_normalized": normalize_rect(element_rect, regions["window"]).to_dict(),
            "region_normalized": normalize_rect(region_rect, regions["window"]).to_dict(),
            "screenshot_path": screenshot_path,
        },
    )


def assert_left_aligned(
    screenshot_path: str,
    token: str,
    reference_region: str = "page",
    capture: bool = True,
    max_offset_ratio: float = 0.08,
) -> VerificationResult:
    """Проверить, что элемент выровнен по левому краю reference-региона."""
    if capture:
        take_screenshot(screenshot_path)
    regions = _image_regions(screenshot_path)
    if reference_region not in regions:
        return build_result(
            ok=False,
            sources_used=["geometry"],
            signal_strength=0.0,
            evidence={"reason": "UNKNOWN_REGION", "reference_region": reference_region},
        )

    bbox = find_token_bbox(screenshot_path, token)
    if not bbox:
        return build_result(
            ok=False,
            sources_used=["geometry", "feature_visual"],
            signal_strength=0.0,
            evidence={"reason": "TOKEN_NOT_FOUND", "token": token},
        )

    element_rect = rect_from_bbox(bbox)
    ref_rect = regions[reference_region]
    ok = is_left_aligned(element_rect, ref_rect, max_offset_ratio=max_offset_ratio)
    offset_ratio = (element_rect.left - ref_rect.left) / float(max(1, ref_rect.width))
    return build_result(
        ok=ok,
        sources_used=["geometry"],
        signal_strength=1.0 if ok else max(0.0, 1.0 - abs(offset_ratio - max_offset_ratio)),
        tolerance_applied=[f"left_offset_ratio<={max_offset_ratio}"],
        evidence={
            "token": token,
            "reference_region": reference_region,
            "element_bbox": bbox,
            "offset_ratio": offset_ratio,
            "max_offset_ratio": max_offset_ratio,
            "screenshot_path": screenshot_path,
        },
    )


def assert_full_page_visible(
    screenshot_path: str,
    top_tokens: List[str],
    bottom_tokens: List[str],
    capture: bool = True,
    top_max_ratio: float = DEFAULT_FULL_VIEW_TOP_MAX_RATIO,
    bottom_min_ratio: float = DEFAULT_FULL_VIEW_BOTTOM_MIN_RATIO,
) -> VerificationResult:
    """Проверить, что верх и низ страницы одновременно видимы в области page."""
    if capture:
        take_screenshot(screenshot_path)
    regions = _image_regions(screenshot_path)
    page_rect = regions["page"]

    top_hit = _first_token_rect(screenshot_path, top_tokens)
    bottom_hit = _first_token_rect(screenshot_path, bottom_tokens)
    if not top_hit or not bottom_hit:
        found = []
        if top_hit:
            found.append(f"top:{top_hit[0]}")
        if bottom_hit:
            found.append(f"bottom:{bottom_hit[0]}")
        return result_from_token_match(
            source="geometry",
            ok=False,
            found_tokens=found,
            expected_tokens=list(top_tokens) + list(bottom_tokens),
            need=2,
            tolerance_applied=[
                f"full_view_top_max_ratio={top_max_ratio}",
                f"full_view_bottom_min_ratio={bottom_min_ratio}",
            ],
            evidence={"screenshot_path": screenshot_path},
        )

    top_token, top_rect = top_hit
    bottom_token, bottom_rect = bottom_hit
    top_ratio = (top_rect.center_y - page_rect.top) / float(max(1, page_rect.height))
    bottom_ratio = (bottom_rect.center_y - page_rect.top) / float(max(1, page_rect.height))

    top_ok = is_contained(top_rect, page_rect) and top_ratio <= top_max_ratio
    bottom_ok = is_contained(bottom_rect, page_rect) and bottom_ratio >= bottom_min_ratio
    ok = top_ok and bottom_ok

    return build_result(
        ok=ok,
        sources_used=["geometry", "feature_visual"],
        signal_strength=1.0 if ok else 0.5,
        tolerance_applied=[
            f"full_view_top_max_ratio={top_max_ratio}",
            f"full_view_bottom_min_ratio={bottom_min_ratio}",
        ],
        evidence={
            "found_tokens": [f"top:{top_token}", f"bottom:{bottom_token}"],
            "top_token_bbox": {
                "left": top_rect.left,
                "top": top_rect.top,
                "right": top_rect.right,
                "bottom": top_rect.bottom,
            },
            "bottom_token_bbox": {
                "left": bottom_rect.left,
                "top": bottom_rect.top,
                "right": bottom_rect.right,
                "bottom": bottom_rect.bottom,
            },
            "top_ratio": top_ratio,
            "bottom_ratio": bottom_ratio,
            "page_normalized": normalize_rect(page_rect, regions["window"]).to_dict(),
            "screenshot_path": screenshot_path,
        },
    )


def assert_toolbar_content_below_active_tab(
    screenshot_path: str,
    active_tab_token: str,
    content_token: str,
    capture: bool = True,
    min_gap_px: int = 0,
) -> VerificationResult:
    """Проверить, что контент вкладки расположен ниже активной вкладки toolbar."""
    if capture:
        take_screenshot(screenshot_path)
    regions = _image_regions(screenshot_path)
    tab_bbox = find_token_bbox(screenshot_path, active_tab_token)
    content_bbox = find_token_bbox(screenshot_path, content_token)
    if not tab_bbox or not content_bbox:
        return build_result(
            ok=False,
            sources_used=["geometry", "feature_visual"],
            signal_strength=0.0,
            evidence={
                "reason": "TOKEN_NOT_FOUND",
                "active_tab_token": active_tab_token,
                "content_token": content_token,
            },
        )

    tab_rect = rect_from_bbox(tab_bbox)
    content_rect = rect_from_bbox(content_bbox)
    toolbar_ok = is_contained(tab_rect, regions["toolbar"], tolerance_px=2)
    workspace_ok = is_contained(content_rect, regions["workspace"], tolerance_px=2)
    below_ok = is_below(content_rect, tab_rect, min_gap_px=min_gap_px)
    ok = toolbar_ok and workspace_ok and below_ok
    return build_result(
        ok=ok,
        sources_used=["geometry", "feature_visual"],
        signal_strength=1.0 if ok else 0.5,
        tolerance_applied=[f"min_gap_px={min_gap_px}"],
        evidence={
            "active_tab_token": active_tab_token,
            "content_token": content_token,
            "tab_bbox": tab_bbox,
            "content_bbox": content_bbox,
            "toolbar_ok": toolbar_ok,
            "workspace_ok": workspace_ok,
            "below_ok": below_ok,
            "screenshot_path": screenshot_path,
        },
    )


def assert_warning_visible(
    pid: int,
    timeout_sec: int = 10,
) -> VerificationResult:
    """Проверить, что предупреждение о регистрации отображается.

    Делегирует detect_warning_window из actions (UIAutomation через PowerShell).
    """
    found = detect_warning_window(pid, timeout_sec)
    return build_result(
        ok=bool(found),
        sources_used=["accessibility"],
        signal_strength=1.0 if found else 0.0,
        evidence={"pid": pid, "timeout_sec": timeout_sec, "warning_visible": bool(found)},
    )


def assert_warning_closed(
    pid: Optional[int],
    timeout_sec: int = 3,
) -> VerificationResult:
    """Проверить, что предупреждение о регистрации закрыто.

    Returns:
        True если предупреждение НЕ обнаружено (т.е. закрыто).
    """
    if not pid:
        return build_result(
            ok=False,
            sources_used=["accessibility"],
            signal_strength=0.0,
            evidence={"pid": pid, "timeout_sec": timeout_sec, "reason": "PID_MISSING"},
        )
    # Если detect_warning_window вернул False — предупреждения нет = закрыто
    found = detect_warning_window(pid, timeout_sec)
    return build_result(
        ok=not found,
        sources_used=["accessibility"],
        signal_strength=1.0 if not found else 0.0,
        evidence={"pid": pid, "timeout_sec": timeout_sec, "warning_visible": bool(found)},
    )


def assert_section_visible(
    screenshot_path: str,
    tokens: List[str],
    need: int = 1,
) -> VerificationResult:
    """Проверить, что раздел отображается (по OCR-токенам на скриншоте).

    Returns:
        (ok, found_tokens)
    """
    take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    ok, found = has_tokens(ocr_text, tokens, need)
    return result_from_token_match(
        source="feature_visual",
        ok=ok,
        found_tokens=found,
        expected_tokens=tokens,
        need=need,
        evidence={"screenshot_path": screenshot_path},
    )


def assert_popup_visible(
    screenshot_path: str,
    tokens: List[str],
    need: int = 2,
) -> VerificationResult:
    """Проверить, что модальное окно отображается."""
    take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    ok, found = has_tokens(ocr_text, tokens, need)
    return result_from_token_match(
        source="feature_visual",
        ok=ok,
        found_tokens=found,
        expected_tokens=tokens,
        need=need,
        evidence={"screenshot_path": screenshot_path},
    )


def assert_popup_closed(
    screenshot_path: str,
    popup_tokens: List[str],
) -> VerificationResult:
    """Проверить, что модальное окно закрыто (токены НЕ обнаружены)."""
    take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    still_open, _ = has_tokens(ocr_text, popup_tokens, need=1)
    return build_result(
        ok=not still_open,
        sources_used=["feature_visual"],
        signal_strength=1.0 if not still_open else 0.0,
        evidence={
            "popup_tokens": popup_tokens,
            "popup_still_open": bool(still_open),
            "screenshot_path": screenshot_path,
        },
    )


def assert_tab_active(
    screenshot_path: str,
    tab_name: str,
    content_tokens: List[str] = None,
    need: int = 1,
) -> VerificationResult:
    """Проверить, что вкладка панели инструментов активна.

    ВАЖНО: имя вкладки НЕ используется как токен для проверки, потому что
    все имена вкладок всегда видны в строке ленты (даже неактивные).
    Проверка выполняется по content_tokens — уникальному содержимому панели
    инструментов данной вкладки (кнопки, подписи, элементы).

    Args:
        screenshot_path: путь для сохранения скриншота
        tab_name: имя вкладки (для логирования, НЕ для проверки)
        content_tokens: токены уникального содержимого панели вкладки
        need: минимальное количество найденных токенов для PASS

    Returns:
        (ok, found_tokens)
    """
    if not content_tokens:
        # Без content_tokens невозможно достоверно проверить активность
        take_screenshot(screenshot_path)
        return build_result(
            ok=False,
            sources_used=["feature_visual"],
            signal_strength=0.0,
            evidence={
                "tab_name": tab_name,
                "screenshot_path": screenshot_path,
                "found_tokens": [],
                "reason": "CONTENT_TOKENS_MISSING",
            },
        )
    take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    ok, found = has_tokens(ocr_text, content_tokens, need)
    return result_from_token_match(
        source="feature_visual",
        ok=ok,
        found_tokens=found,
        expected_tokens=content_tokens,
        need=need,
        evidence={"tab_name": tab_name, "screenshot_path": screenshot_path},
    )


def assert_document_created(
    screenshot_path: str,
    tokens: List[str] = None,
    need: int = 1,
) -> VerificationResult:
    """Проверить, что новый документ создан (редактор перешёл в режим редактирования).

    По умолчанию ищет токены панели инструментов документа.
    """
    if tokens is None:
        tokens = ["Главная", "Вставка", "Макет"]
    take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    ok, found = has_tokens(ocr_text, tokens, need)
    return result_from_token_match(
        source="feature_visual",
        ok=ok,
        found_tokens=found,
        expected_tokens=tokens,
        need=need,
        evidence={"screenshot_path": screenshot_path},
    )


def assert_text_entered_and_left_aligned(
    screenshot_path: str,
    tokens: List[str],
    need: int = 2,
    anchor_token: str = "Задача",
    max_left_ratio: float = 0.35,
) -> VerificationResult:
    """Проверить, что текст введён и начало абзаца расположено у левого поля.

    Критерий:
    1) В OCR-тексте найдено минимум `need` токенов ожидаемого текста.
    2) Якорный токен (`anchor_token`) найден на скриншоте и его координата X
       находится в левой части страницы (<= max_left_ratio * width).
    """
    take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    text_ok, found = has_tokens(ocr_text, tokens, need)
    text_result = result_from_token_match(
        source="semantic_content_model",
        ok=text_ok,
        found_tokens=found,
        expected_tokens=tokens,
        need=need,
        evidence={"screenshot_path": screenshot_path},
    )
    if not text_ok:
        return text_result

    geometry_result = assert_left_aligned(
        screenshot_path=screenshot_path,
        token=anchor_token,
        reference_region="page",
        capture=False,
        max_offset_ratio=max_left_ratio,
    )
    geometry_result.sources_used.insert(0, "semantic_content_model")
    geometry_result.evidence["found_tokens"] = text_result.found_tokens
    return merge_results(
        [text_result, geometry_result],
        mode="all",
        evidence={"tab": "text_entered_left_aligned"},
    )


def assert_text_absent(
    screenshot_path: str,
    tokens: List[str],
    max_found: int = 0,
) -> VerificationResult:
    """Проверить, что ожидаемые токены текста отсутствуют на странице."""
    take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    _, found = has_tokens(ocr_text, tokens, need=1)
    ok = len(found) <= max_found
    allowed = [f"max_found<={max_found}"]
    return build_result(
        ok=ok,
        sources_used=["semantic_content_model"],
        signal_strength=1.0 if ok else max(0.0, 1.0 - min(1.0, len(found) / float(max_found + 1))),
        tolerance_applied=allowed,
        evidence={
            "found_tokens": found,
            "expected_tokens": tokens,
            "max_found": max_found,
            "screenshot_path": screenshot_path,
        },
    )


def assert_save_dialog_opened(
    screenshot_path: str,
    path_tokens: Optional[List[str]] = None,
    filename_tokens: Optional[List[str]] = None,
) -> VerificationResult:
    """Проверить, что открыто системное окно сохранения."""
    if path_tokens is None:
        path_tokens = ["Документы", "Documents"]
    if filename_tokens is None:
        filename_tokens = ["Документ1", "Document1"]
    dialog_tokens = [
        "Сохранить как",
        "Save As",
        "Имя файла",
        "File name",
        "Тип файла",
        "File type",
        "Отмена",
        "Cancel",
        "Сохранить",
        "Save",
    ]

    take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)

    dialog_ok, found_dialog = has_tokens(ocr_text, dialog_tokens, need=2)
    path_ok, found_path = has_tokens(ocr_text, path_tokens, need=1)
    file_ok, found_file = has_tokens(ocr_text, filename_tokens, need=1)
    dialog_result = result_from_token_match(
        source="feature_visual",
        ok=dialog_ok,
        found_tokens=found_dialog,
        expected_tokens=dialog_tokens,
        need=2,
        evidence={"screenshot_path": screenshot_path},
    )
    path_result = result_from_token_match(
        source="file_model",
        ok=path_ok,
        found_tokens=found_path,
        expected_tokens=path_tokens,
        need=1,
        evidence={"screenshot_path": screenshot_path},
    )
    file_result = result_from_token_match(
        source="semantic_content_model",
        ok=file_ok,
        found_tokens=found_file,
        expected_tokens=filename_tokens,
        need=1,
        evidence={"screenshot_path": screenshot_path},
    )
    # OCR имени файла может быть нестабилен при выделении текста в поле ввода.
    # Надёжный критерий: заголовок/структура системного окна + область пути.
    ok = dialog_ok or (path_ok and file_ok)
    merged = merge_results(
        [dialog_result, merge_results([path_result, file_result], mode="all")],
        mode="any",
        evidence={"screenshot_path": screenshot_path},
    )
    merged.ok = ok
    merged.signal_strength = max(
        dialog_result.signal_strength,
        min(path_result.signal_strength, file_result.signal_strength),
    )
    merged.evidence["found_tokens"] = found_dialog + found_path + found_file
    if path_ok and file_ok and not dialog_ok:
        merged.tolerance_applied.append("SAVE_DIALOG_LABELS_RELAXED")
    return merged


def assert_file_exists(file_path: str) -> VerificationResult:
    """Проверить, что файл существует в файловой системе."""
    exists = os.path.isfile(file_path)
    return build_result(
        ok=exists,
        sources_used=["file_model"],
        signal_strength=1.0 if exists else 0.0,
        evidence={"file_path": file_path, "exists": exists},
    )
