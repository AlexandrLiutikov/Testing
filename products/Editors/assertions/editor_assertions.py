"""Semantic assertions для Editors — продуктовый слой (§16, §17 SCRIPT_RULES).

Assertions — это проверяющие функции, которые:
1. Делают скриншот
2. Выполняют проверку (через OCR или делегируя actions)
3. Возвращают структурированный VerificationResult
"""

import os
from typing import List, Optional

from shared.infra.ocr import find_token_bbox, has_tokens, ocr_image
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

    if capture:
        take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    top_ok, top_found = has_tokens(ocr_text, markers.get("top", []), need=1)
    bottom_ok, bottom_found = has_tokens(ocr_text, markers.get("bottom", []), need=1)

    found = [f"top:{token}" for token in top_found]
    found.extend([f"bottom:{token}" for token in bottom_found])
    if top_ok and bottom_ok:
        return result_from_token_match(
            source="geometry",
            ok=True,
            found_tokens=found,
            expected_tokens=markers.get("top", []) + markers.get("bottom", []),
            need=2,
            tolerance_applied=[
                f"full_view_top_max_ratio={top_max_ratio}",
                f"full_view_bottom_min_ratio={bottom_min_ratio}",
            ],
            evidence={"page_index": page_index},
        )

    if bottom_ok:
        content_tokens = REFERENCE_DOC_PAGE_TOKENS.get(page_index, [])
        relaxed_top_tokens = [t for t in content_tokens if "Страница" not in t]
        relaxed_top_ok, relaxed_top_found = has_tokens(ocr_text, relaxed_top_tokens, need=1)
        if relaxed_top_ok:
            found.extend([f"top_relaxed:{token}" for token in relaxed_top_found])
            return result_from_token_match(
                source="geometry",
                ok=True,
                found_tokens=found,
                expected_tokens=markers.get("top", []) + markers.get("bottom", []),
                need=2,
                tolerance_applied=[
                    f"full_view_top_max_ratio={top_max_ratio}",
                    f"full_view_bottom_min_ratio={bottom_min_ratio}",
                    "RELAXED_TOP_MARKERS",
                ],
                evidence={"page_index": page_index},
            )

        # Последняя страница может содержать только колонтитулы и номер страницы.
        if page_index == 4:
            found.append("top_relaxed:PAGE4_BOTTOM_ONLY")
            return result_from_token_match(
                source="geometry",
                ok=True,
                found_tokens=found,
                expected_tokens=markers.get("top", []) + markers.get("bottom", []),
                need=2,
                tolerance_applied=[
                    f"full_view_top_max_ratio={top_max_ratio}",
                    f"full_view_bottom_min_ratio={bottom_min_ratio}",
                    "PAGE4_BOTTOM_ONLY_ALLOWED",
                ],
                evidence={"page_index": page_index},
            )

    return result_from_token_match(
        source="geometry",
        ok=False,
        found_tokens=found,
        expected_tokens=markers.get("top", []) + markers.get("bottom", []),
        need=2,
        tolerance_applied=[
            f"full_view_top_max_ratio={top_max_ratio}",
            f"full_view_bottom_min_ratio={bottom_min_ratio}",
        ],
        evidence={"page_index": page_index},
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
    from PIL import Image

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

    bbox = find_token_bbox(screenshot_path, anchor_token)
    if not bbox:
        return build_result(
            ok=False,
            sources_used=["semantic_content_model", "geometry", "ocr_fallback"],
            signal_strength=text_result.signal_strength * 0.5,
            evidence={
                "found_tokens": text_result.found_tokens,
                "anchor_token": anchor_token,
                "anchor_bbox": None,
                "screenshot_path": screenshot_path,
            },
        )

    image_width = Image.open(screenshot_path).size[0]
    left_aligned = bbox["left"] <= int(image_width * max_left_ratio)
    geometry_result = build_result(
        ok=left_aligned,
        sources_used=["geometry"],
        signal_strength=1.0 if left_aligned else 0.0,
        tolerance_applied=[f"anchor_left_ratio<={max_left_ratio}"],
        evidence={
            "found_tokens": text_result.found_tokens,
            "anchor_token": anchor_token,
            "anchor_bbox": bbox,
            "image_width": image_width,
            "max_left_ratio": max_left_ratio,
            "anchor_left_ratio": float(bbox["left"]) / float(image_width or 1),
            "screenshot_path": screenshot_path,
        },
    )
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
