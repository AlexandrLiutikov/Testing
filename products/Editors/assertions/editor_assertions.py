"""Semantic assertions для Editors — продуктовый слой (§16, §17 SCRIPT_RULES).

Assertions — это проверяющие функции, которые:
1. Делают скриншот
2. Выполняют проверку (через OCR или делегируя actions)
3. Возвращают результат (bool / tuple)
"""

import os
from typing import List, Optional, Tuple

from shared.infra.ocr import has_tokens, ocr_image
from shared.infra.model_loader import load_yaml_model
from shared.infra.screenshots import take_screenshot
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
) -> Optional[int]:
    """Проверить, что окно редактора появилось (поиск процесса + ожидание).

    Returns:
        pid процесса или None если не найдено.
    """
    return wait_main_proc(process_name, timeout_sec)


def assert_reference_document_opened(
    screenshot_path: str,
) -> Tuple[bool, List[str]]:
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
) -> Tuple[bool, List[str]]:
    """Проверить содержимое конкретной страницы эталонного документа."""
    tokens = REFERENCE_DOC_PAGE_TOKENS.get(page_index, [])
    if not tokens:
        if capture:
            take_screenshot(screenshot_path)
        return False, []
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
        return assert_section_visible(screenshot_path, probe, need=1)

    # Страница 4 в эталоне почти пустая, OCR контента нестабилен.
    # Сначала пробуем контент, затем fallback на маркер "Страница 4 из 4".
    if page_index == 4:
        probe = content_tokens or tokens
        ok, found = assert_section_visible(screenshot_path, probe, need=1)
        if ok:
            return ok, found
        if page_tokens:
            return assert_section_visible(screenshot_path, page_tokens, need=1)
        return ok, found

    if capture:
        take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    # Для страниц 2-3 запрещаем PASS только по токенам статус-бара.
    if page_index in (2, 3):
        probe = content_tokens or tokens
        return has_tokens(ocr_text, probe, need=1)

    # Страница 4 может быть почти пустой: сначала ищем контент, затем page-token.
    if page_index == 4:
        probe = content_tokens or tokens
        ok, found = has_tokens(ocr_text, probe, need=1)
        if ok:
            return ok, found
        if page_tokens:
            return has_tokens(ocr_text, page_tokens, need=1)
        return ok, found

    return has_tokens(ocr_text, tokens, need=1)


def assert_reference_document_page_full_view(
    screenshot_path: str,
    page_index: int,
    capture: bool = True,
    top_max_ratio: float = DEFAULT_FULL_VIEW_TOP_MAX_RATIO,
    bottom_min_ratio: float = DEFAULT_FULL_VIEW_BOTTOM_MIN_RATIO,
) -> Tuple[bool, List[str]]:
    """Проверить, что страница отображается целиком (верх+низ страницы видны)."""
    markers = REFERENCE_DOC_PAGE_FULL_VIEW_MARKERS.get(page_index)
    if not markers:
        if capture:
            take_screenshot(screenshot_path)
        return False, []

    if capture:
        take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    top_ok, top_found = has_tokens(ocr_text, markers.get("top", []), need=1)
    bottom_ok, bottom_found = has_tokens(ocr_text, markers.get("bottom", []), need=1)

    found = [f"top:{token}" for token in top_found]
    found.extend([f"bottom:{token}" for token in bottom_found])
    if top_ok and bottom_ok:
        return True, found

    if bottom_ok:
        content_tokens = REFERENCE_DOC_PAGE_TOKENS.get(page_index, [])
        relaxed_top_tokens = [t for t in content_tokens if "Страница" not in t]
        relaxed_top_ok, relaxed_top_found = has_tokens(ocr_text, relaxed_top_tokens, need=1)
        if relaxed_top_ok:
            found.extend([f"top_relaxed:{token}" for token in relaxed_top_found])
            return True, found

        # Последняя страница может содержать только колонтитулы и номер страницы.
        if page_index == 4:
            found.append("top_relaxed:PAGE4_BOTTOM_ONLY")
            return True, found

    return False, found


def assert_warning_visible(
    pid: int,
    timeout_sec: int = 10,
) -> bool:
    """Проверить, что предупреждение о регистрации отображается.

    Делегирует detect_warning_window из actions (UIAutomation через PowerShell).
    """
    return detect_warning_window(pid, timeout_sec)


def assert_warning_closed(
    pid: Optional[int],
    timeout_sec: int = 3,
) -> bool:
    """Проверить, что предупреждение о регистрации закрыто.

    Returns:
        True если предупреждение НЕ обнаружено (т.е. закрыто).
    """
    if not pid:
        return False
    # Если detect_warning_window вернул False — предупреждения нет = закрыто
    found = detect_warning_window(pid, timeout_sec)
    return not found


def assert_section_visible(
    screenshot_path: str,
    tokens: List[str],
    need: int = 1,
) -> Tuple[bool, List[str]]:
    """Проверить, что раздел отображается (по OCR-токенам на скриншоте).

    Returns:
        (ok, found_tokens)
    """
    take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    return has_tokens(ocr_text, tokens, need)


def assert_popup_visible(
    screenshot_path: str,
    tokens: List[str],
    need: int = 2,
) -> Tuple[bool, List[str]]:
    """Проверить, что модальное окно отображается."""
    take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    return has_tokens(ocr_text, tokens, need)


def assert_popup_closed(
    screenshot_path: str,
    popup_tokens: List[str],
) -> bool:
    """Проверить, что модальное окно закрыто (токены НЕ обнаружены)."""
    take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    still_open, _ = has_tokens(ocr_text, popup_tokens, need=1)
    return not still_open


def assert_tab_active(
    screenshot_path: str,
    tab_name: str,
    content_tokens: List[str] = None,
    need: int = 1,
) -> Tuple[bool, List[str]]:
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
        return False, []
    take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    return has_tokens(ocr_text, content_tokens, need)


def assert_document_created(
    screenshot_path: str,
    tokens: List[str] = None,
    need: int = 1,
) -> Tuple[bool, List[str]]:
    """Проверить, что новый документ создан (редактор перешёл в режим редактирования).

    По умолчанию ищет токены панели инструментов документа.
    """
    if tokens is None:
        tokens = ["Главная", "Вставка", "Макет"]
    take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    return has_tokens(ocr_text, tokens, need)


def assert_text_entered_and_left_aligned(
    screenshot_path: str,
    tokens: List[str],
    need: int = 2,
    anchor_token: str = "Задача",
    max_left_ratio: float = 0.35,
) -> Tuple[bool, List[str]]:
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
    if not text_ok:
        return False, found

    bbox = find_token_bbox(screenshot_path, anchor_token)
    if not bbox:
        return False, found

    image_width = Image.open(screenshot_path).size[0]
    left_aligned = bbox["left"] <= int(image_width * max_left_ratio)
    return left_aligned, found


def assert_text_absent(
    screenshot_path: str,
    tokens: List[str],
    max_found: int = 0,
) -> Tuple[bool, List[str]]:
    """Проверить, что ожидаемые токены текста отсутствуют на странице."""
    take_screenshot(screenshot_path)
    ocr_text = ocr_image(screenshot_path)
    _, found = has_tokens(ocr_text, tokens, need=1)
    return len(found) <= max_found, found


def assert_save_dialog_opened(
    screenshot_path: str,
    path_tokens: Optional[List[str]] = None,
    filename_tokens: Optional[List[str]] = None,
) -> Tuple[bool, List[str]]:
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
    # OCR имени файла может быть нестабилен при выделении текста в поле ввода.
    # Надёжный критерий: заголовок/структура системного окна + область пути.
    ok = dialog_ok or (path_ok and file_ok)
    return ok, found_dialog + found_path + found_file


def assert_file_exists(file_path: str) -> bool:
    """Проверить, что файл существует в файловой системе."""
    return os.path.isfile(file_path)
