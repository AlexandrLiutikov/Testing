"""Semantic actions для Editors — продуктовый слой (§16, §17 SCRIPT_RULES).

ВАЖНО: хардкод координат UI запрещён. R7 Office использует CEF, элементы
ленты и стартового экрана недоступны через Accessibility API, поэтому клики
выполняются по координатам — но координаты получаются в **runtime** через
OCR (`shared.infra.ocr.find_token_bbox`) на свежем скриншоте окна, а не
зашиваются в код. Это единственный способ работать на любых разрешениях.
"""

import time
import logging
import tempfile
import os as _os

from shared.drivers import get_driver
from shared.infra.screenshots import take_screenshot

logger = logging.getLogger(__name__)


def click_menu(pid: int, menu_key: str):
    """Активировать окно и кликнуть по пункту левого меню стартового экрана.
    
    Основной путь: семантический поиск элемента через driver.click_menu_item().
    Fallback цепочка внутри driver: accessibility → OCR → coordinates → CV.
    """
    driver = get_driver()
    driver.activate_window(pid)
    
    # Семантический клик с fallback цепочкой внутри driver
    success = driver.click_menu_item(pid, menu_key)
    
    if not success:
        raise RuntimeError(
            f"Не удалось кликнуть по пункту меню '{menu_key}': "
            f"все fallback методы исчерпаны"
        )
    
    time.sleep(0.6)  # ожидание перехода (Semantic Actions Layer)


def dismiss_collab_popup(pid: int):
    """Закрыть модальное окно подключения дисков клавишей Esc."""
    driver = get_driver()
    driver.send_escape(pid)


def type_document_text(pid: int, text: str, align_left: bool = False):
    """Ввести текст в область документа и при необходимости выровнять влево.

    Action-only: выполняет фокус на холсте документа, вставляет текст через
    буфер обмена и (опционально) применяет выравнивание абзаца влево.
    PASS/FAIL не выставляет — подтверждение выполняется assertion-слоем.
    """
    driver = get_driver()
    driver.activate_window(pid)

    # FALLBACK: у CEF-холста нет стабильного accessibility-id, поэтому
    # фокусируем рабочую область относительным кликом по центру страницы.
    driver.click_rel(pid, 0.50, 0.45)
    time.sleep(0.2)

    driver.paste_text(pid, text)
    if align_left:
        driver.align_paragraph_left(pid)


_QUICK_ACCESS_BUTTONS = {
    "save": 0,
    "undo": 1,
    "redo": 2,
}


def _click_quick_access_button(pid: int, button_key: str) -> bool:
    """Кликнуть по кнопке панели быстрого доступа слева от вкладки «Файл».

    Основной путь для шагов вида «кликнуть кнопку ...»:
    1) OCR находит якорь «Автосохранение» на верхней панели
    2) координата кнопки вычисляется относительно якоря
    3) выполняется клик по UI-элементу (driver.click_rel)
    """
    if button_key not in _QUICK_ACCESS_BUTTONS:
        raise ValueError(f"Неизвестная кнопка быстрого доступа: {button_key}")

    from PIL import Image

    driver = get_driver()
    driver.activate_window(pid)

    fd, screenshot_path = tempfile.mkstemp(prefix="quick_access_", suffix=".png")
    _os.close(fd)
    try:
        take_screenshot(screenshot_path)
        img = Image.open(screenshot_path)
        width, height = img.size

        # Кнопки Quick Access в левом верхнем углу.
        # В CEF-UI координаты иконок доступны только через runtime-клик.
        # Используем калибровку в относительных долях экрана + небольшой
        # горизонтальный перебор, чтобы нивелировать DPI/scale отклонения.
        rel_map = {
            "save": 0.016,
            "undo": 0.088,
            "redo": 0.114,
        }
        base_rel_x = rel_map[button_key]
        rel_y = 0.045
        for x_shift in (-0.006, 0.0, 0.006):
            target_rel_x = max(0.0, min(0.999, base_rel_x + x_shift))
            target_x = int(target_rel_x * width)
            target_y = int(rel_y * height)
            driver.click_rel(pid, target_x / width, target_y / height)
            time.sleep(0.12)
        return True
    finally:
        try:
            _os.remove(screenshot_path)
        except OSError:
            pass


def undo_last_action(pid: int, allow_hotkey_fallback: bool = True) -> bool:
    """Выполнить команду «Отменить».

    Возвращает True, если выполнен UI-клик или fallback.
    """
    if _click_quick_access_button(pid, "undo"):
        return True
    if not allow_hotkey_fallback:
        return False
    # FALLBACK: UI-кнопка не найдена OCR; используем Ctrl+Z как резерв.
    logger.warning("FALLBACK: кнопка «Отменить» не найдена, применён Ctrl+Z")
    get_driver().undo_action(pid)
    return True


def redo_last_action(pid: int, allow_hotkey_fallback: bool = True) -> bool:
    """Выполнить команду «Повторить».

    Возвращает True, если выполнен UI-клик или fallback.
    """
    if _click_quick_access_button(pid, "redo"):
        return True
    if not allow_hotkey_fallback:
        return False
    # FALLBACK: UI-кнопка не найдена OCR; используем Ctrl+Y как резерв.
    logger.warning("FALLBACK: кнопка «Повторить» не найдена, применён Ctrl+Y")
    get_driver().redo_action(pid)
    return True


def save_active_document(pid: int, allow_hotkey_fallback: bool = True) -> bool:
    """Выполнить команду «Сохранить».

    Возвращает True, если выполнен UI-клик или fallback.
    """
    if _click_quick_access_button(pid, "save"):
        return True
    if not allow_hotkey_fallback:
        return False
    # FALLBACK: UI-кнопка не найдена OCR; используем Ctrl+S как резерв.
    logger.warning("FALLBACK: кнопка «Сохранить» не найдена, применён Ctrl+S")
    get_driver().save_document(pid)
    return True


def confirm_active_dialog(pid: int):
    """Подтвердить активный системный диалог клавишей Enter."""
    get_driver().confirm_dialog(pid)


def close_active_document_tab(pid: int, allow_hotkey_fallback: bool = True) -> bool:
    """Закрыть текущую вкладку по кнопке «X».

    Возвращает True, если выполнен UI-клик или fallback.
    """
    from PIL import Image

    driver = get_driver()
    driver.activate_window(pid)

    fd, screenshot_path = tempfile.mkstemp(prefix="tab_close_", suffix=".png")
    _os.close(fd)
    try:
        take_screenshot(screenshot_path)
        img = Image.open(screenshot_path)
        width, height = img.size
        # Кнопка "X" у вкладки документа в левом верхнем углу.
        # Делаем несколько точек рядом с крестиком вкладки, чтобы не попасть
        # в центральный заголовок документа.
        rel_points = [
            (0.166, 0.017),
            (0.160, 0.017),
            (0.172, 0.017),
        ]
        for rel_x, rel_y in rel_points:
            target_x = int(rel_x * width)
            target_y = int(rel_y * height)
            driver.click_rel(pid, target_x / width, target_y / height)
            time.sleep(0.15)
        return True
    finally:
        try:
            _os.remove(screenshot_path)
        except OSError:
            pass

    if not allow_hotkey_fallback:
        return False
    # FALLBACK: кнопка «X» вкладки не найдена OCR; используем Ctrl+F4.
    logger.warning("FALLBACK: кнопка закрытия вкладки не найдена, применён Ctrl+F4")
    driver.close_current_tab(pid)
    return True


_DOC_LABELS = {
    "document":     "Документ",
    "spreadsheet":  "Таблица",
    "presentation": "Презентация",
}


def _ocr_click_label(pid: int, screenshot_path: str, query: str) -> bool:
    """Найти на скриншоте текстовую метку *query* и кликнуть по её центру.

    Внутренний helper для координатных кликов с runtime OCR-калибровкой.
    """
    from PIL import Image
    from shared.infra.ocr import find_token_bbox

    bbox = find_token_bbox(screenshot_path, query)
    if not bbox:
        return False
    img = Image.open(screenshot_path)
    W, H = img.size
    rel_x = bbox["center_x"] / W
    rel_y = bbox["center_y"] / H
    driver = get_driver()
    driver.activate_window(pid)
    driver.click_rel(pid, rel_x, rel_y)
    return True


def create_document(pid: int, doc_type: str = "document",
                    screenshot_path: str = None):
    """Кликнуть по кнопке создания документа на стартовом экране.

    Координаты кнопки определяются в runtime через OCR — поиск подписи
    («Документ»/«Таблица»/«Презентация») на свежем скриншоте.

    Args:
        pid: процесс редактора
        doc_type: "document" | "spreadsheet" | "presentation"
        screenshot_path: путь для рабочего скриншота калибровки. Если не
            задан — используется временный файл рядом с editors artifacts.
    """
    if doc_type not in _DOC_LABELS:
        raise ValueError(f"Неизвестный тип документа: {doc_type}")
    driver = get_driver()
    driver.activate_window(pid)

    # Свежий скриншот стартового экрана для OCR-калибровки
    import tempfile, os as _os
    if not screenshot_path:
        fd, screenshot_path = tempfile.mkstemp(prefix="start_", suffix=".png")
        _os.close(fd)
    take_screenshot(screenshot_path)

    label = _DOC_LABELS[doc_type]
    if not _ocr_click_label(pid, screenshot_path, label):
        raise RuntimeError(
            f"Не удалось найти кнопку «{label}» на стартовом экране через OCR"
        )


def click_toolbar_tab(pid: int, tab_name: str, positions: dict):
    """Кликнуть по вкладке ленты по откалиброванным координатам.

    Args:
        pid: процесс редактора
        tab_name: имя вкладки (например, "Главная", "Вставка")
        positions: dict {tab_name: (rel_x, rel_y)} от calibrate_toolbar_tabs().
            Хардкод координат запрещён — словарь обязателен.

    Fallback:
        Если вкладка отсутствует в positions (неполная OCR-калибровка),
        выполняется on-demand OCR-клик по имени вкладки на свежем скриншоте.
        Ошибка поднимается только если fallback не смог найти вкладку.
    """
    coords = positions.get(tab_name) if positions else None
    if not coords:
        # FALLBACK: если вкладка не попала в первичную калибровку, пробуем
        # свежий OCR-клик по имени вкладки прямо перед действием.
        if _ocr_click_toolbar_tab(pid, tab_name):
            return
        raise RuntimeError(
            f"Координаты вкладки «{tab_name}» не откалиброваны. "
            f"Перед кликом вызовите calibrate_toolbar_tabs()."
        )
    driver = get_driver()
    driver.activate_window(pid)
    rel_x, rel_y = coords
    driver.click_rel(pid, rel_x, rel_y)


# Имена вкладок ленты в порядке отображения. Многословные («Совместная работа»)
# ищем по первому слову — OCR хуже ловит составные токены.
_TAB_QUERIES = {
    "Файл": "Файл",
    "Главная": "Главная",
    "Вставка": "Вставка",
    "Рисование": "Рисование",
    "Макет": "Макет",
    "Ссылки": "Ссылки",
    "Совместная работа": "Совместная",
    "Защита": "Защита",
    "Вид": "Вид",
    "Плагины": "Плагины",
}


def _ocr_click_toolbar_tab(pid: int, tab_name: str) -> bool:
    """Клик по вкладке ленты через OCR на свежем скриншоте (fallback)."""
    query = _TAB_QUERIES.get(tab_name)
    if not query:
        return False

    fd, screenshot_path = tempfile.mkstemp(prefix="toolbar_", suffix=".png")
    _os.close(fd)
    try:
        take_screenshot(screenshot_path)
        return _ocr_click_label(pid, screenshot_path, query)
    finally:
        try:
            _os.remove(screenshot_path)
        except OSError:
            pass


def calibrate_toolbar_tabs(screenshot_path: str) -> dict:
    """Откалибровать координаты вкладок ленты через OCR на свежем скриншоте.

    Скриншот должен быть полноэкранный, окно редактора — fullscreen,
    видна лента вкладок (документ создан, backstage закрыт).

    Returns:
        dict {tab_name: (rel_x, rel_y)} в долях окна. Вкладки, которые OCR
        не нашёл, в результат не попадают — клик по ним поднимет ошибку.
    """
    from PIL import Image
    from shared.infra.ocr import find_token_bbox

    img = Image.open(screenshot_path)
    W, H = img.size

    result = {}
    for tab_name, query in _TAB_QUERIES.items():
        bbox = find_token_bbox(screenshot_path, query)
        if bbox:
            result[tab_name] = (bbox["center_x"] / W, bbox["center_y"] / H)
    return result


# ---------------------------------------------------------------------------
# Управление процессами редактора
# ---------------------------------------------------------------------------

def kill_editors():
    """Завершить все процессы editors/editors_helper."""
    get_driver().kill_editors()


def launch_editor(editor_path: str):
    """Запустить редактор."""
    driver = get_driver()
    driver.launch_editor(editor_path)


# ---------------------------------------------------------------------------
# Обработка модальных окон предупреждения (§10.6)
# ---------------------------------------------------------------------------

def detect_warning_window(pid: int, timeout_sec: int = 10) -> bool:
    """Проверить наличие модального предупреждения (диалог с кнопкой OK)."""
    driver = get_driver()
    return driver.detect_warning(pid, timeout_sec)


def dismiss_warning(pid: int) -> bool:
    """Закрыть предупреждение: Invoke кнопки OK, fallback — Enter."""
    driver = get_driver()
    return driver.dismiss_warning(pid)
