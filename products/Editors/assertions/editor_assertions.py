"""Semantic assertions для Editors — продуктовый слой (§16, §17 SCRIPT_RULES).

Assertions — это проверяющие функции, которые:
1. Делают скриншот
2. Выполняют проверку (через OCR или делегируя actions)
3. Возвращают результат (bool / tuple)
"""

from typing import List, Optional, Tuple

from shared.infra.ocr import has_tokens, ocr_image
from shared.infra.screenshots import take_screenshot
from shared.infra.waits import wait_main_proc

from products.Editors.actions.editor_actions import detect_warning_window


def assert_window_exists(
    process_name: str = "editors",
    timeout_sec: int = 20,
) -> Optional[int]:
    """Проверить, что окно редактора появилось (поиск процесса + ожидание).

    Returns:
        pid процесса или None если не найдено.
    """
    return wait_main_proc(process_name, timeout_sec)


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
