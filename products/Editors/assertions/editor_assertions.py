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
