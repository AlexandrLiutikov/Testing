"""Semantic actions для Editors — продуктовый слой (§16, §17 SCRIPT_RULES)."""

import time

from shared.drivers import get_driver

# Кнопки создания документов на стартовом экране (относительные координаты).
# Калибровка получена через OCR bbox подписей на стартовом экране 1280x1024:
# подписи «Документ»/«Таблица»/«Презентация» лежат на rel_y≈0.4863, шаг по
# rel_x≈0.128. Иконка расположена над подписью; кликаем по подписи — это
# попадает в активную область кнопки и работает на разных разрешениях.
DOC_CREATE_BUTTONS = {
    "document":      (0.3531, 0.4863),
    "spreadsheet":   (0.4813, 0.4854),
    "presentation":  (0.6094, 0.4854),
}

# Вкладки панели инструментов внутри редактора документов (относительные координаты)
# R7 Office использует CEF для отрисовки UI — Accessibility API недоступен
# для вкладок панели инструментов, поэтому используется координатный fallback.
# Калибровка получена через OCR bbox на эталонном скриншоте 1920x1080,
# полноэкранное окно. rel_y≈0.0806 — центр строки вкладок ленты, ниже title bar.
# ВАЖНО: rel_y<0.07 попадает в title bar/toolbar (иконки сохранения), а не в ленту!
TOOLBAR_TABS = {
    "Файл":                (0.0250, 0.0806),
    "Главная":             (0.0625, 0.0806),
    "Вставка":             (0.1052, 0.0806),
    "Рисование":           (0.1526, 0.0806),
    "Макет":               (0.1964, 0.0806),
    "Ссылки":              (0.2339, 0.0806),
    "Совместная работа":   (0.2802, 0.0806),
    "Защита":              (0.3589, 0.0806),
    "Вид":                 (0.3932, 0.0806),
    "Плагины":             (0.4286, 0.0806),
}


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


def create_document(pid: int, doc_type: str = "document"):
    """Кликнуть по кнопке создания документа на стартовом экране.

    doc_type: "document" | "spreadsheet" | "presentation"
    """
    if doc_type not in DOC_CREATE_BUTTONS:
        raise ValueError(f"Неизвестный тип документа: {doc_type}")
    driver = get_driver()
    driver.activate_window(pid)
    rel_x, rel_y = DOC_CREATE_BUTTONS[doc_type]
    driver.click_rel(pid, rel_x, rel_y)


def click_toolbar_tab(pid: int, tab_name: str, positions: dict = None):
    """Кликнуть по вкладке на панели инструментов редактора.

    Args:
        pid: процесс редактора
        tab_name: имя вкладки (например, "Главная", "Вставка")
        positions: опциональный dict {tab_name: (rel_x, rel_y)} с
            откалиброванными координатами для текущего разрешения.
            Если не передан — используется TOOLBAR_TABS (хардкод 1920x1080).
    """
    coords = (positions or {}).get(tab_name) or TOOLBAR_TABS.get(tab_name)
    if not coords:
        raise ValueError(f"Неизвестная вкладка: {tab_name}")
    driver = get_driver()
    driver.activate_window(pid)
    rel_x, rel_y = coords
    driver.click_rel(pid, rel_x, rel_y)


def calibrate_toolbar_tabs(screenshot_path: str) -> dict:
    """Откалибровать координаты вкладок ленты через OCR на свежем скриншоте.

    Хардкод координат не работает на разных разрешениях/масштабах.
    Эта функция находит каждую вкладку на скриншоте через find_token_bbox
    и возвращает dict {tab_name: (rel_x, rel_y)} в долях окна.

    Скриншот должен быть полноэкранный, окно редактора — fullscreen,
    видна лента вкладок (документ создан, backstage закрыт).

    Returns:
        dict откалиброванных координат. Вкладки, которые OCR не нашёл,
        в результат не попадают — для них останется fallback на TOOLBAR_TABS.
    """
    from PIL import Image
    from shared.infra.ocr import find_token_bbox

    img = Image.open(screenshot_path)
    W, H = img.size

    # Имена для поиска: для «Совместная работа» ищем по первому слову,
    # т.к. многословные токены OCR ловит хуже.
    tab_query = {
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

    result = {}
    for tab_name, query in tab_query.items():
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
