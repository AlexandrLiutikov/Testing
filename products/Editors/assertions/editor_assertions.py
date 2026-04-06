"""Semantic assertions для Editors — продуктовый слой (§16, §17 SCRIPT_RULES)."""

from typing import List, Tuple

from shared.infra.ocr import has_tokens, ocr_image
from shared.infra.screenshots import take_screenshot


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
