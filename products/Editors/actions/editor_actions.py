"""Semantic actions для Editors — продуктовый слой (§16, §17 SCRIPT_RULES)."""

import time

from shared.drivers import get_driver

# Кнопки создания документов на стартовом экране (относительные координаты)
# Калибровка: 1920x1080, масштаб 100%, полноэкранное окно
DOC_CREATE_BUTTONS = {
    "document":      (0.365, 0.39),
    "spreadsheet":   (0.453, 0.39),
    "presentation":  (0.542, 0.39),
}

# Вкладки панели инструментов внутри редактора документов (относительные координаты)
# R7 Office использует CEF для отрисовки UI — Accessibility API недоступен
# для вкладок панели инструментов, поэтому используется координатный fallback.
# Калибровка: 1920x1080, масштаб 100%, полноэкранное окно.
# rel_y=0.060 — центр строки вкладок ленты (y≈65px из 1080).
# ВАЖНО: rel_y=0.03 попадает в title bar, а не в ленту!
TOOLBAR_TABS = {
    "Файл":                (0.012, 0.060),
    "Главная":             (0.045, 0.060),
    "Вставка":             (0.081, 0.060),
    "Рисование":           (0.124, 0.060),
    "Макет":               (0.166, 0.060),
    "Ссылки":              (0.199, 0.060),
    "Совместная работа":   (0.256, 0.060),
    "Защита":              (0.307, 0.060),
    "Вид":                 (0.333, 0.060),
    "Плагины":             (0.365, 0.060),
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
    activate_window(pid)
    rel_x, rel_y = DOC_CREATE_BUTTONS[doc_type]
    click_rel(pid, rel_x, rel_y)


def click_toolbar_tab(pid: int, tab_name: str):
    """Кликнуть по вкладке на панели инструментов редактора.

    tab_name: одно из значений в TOOLBAR_TABS (например, "Главная", "Вставка").
    """
    if tab_name not in TOOLBAR_TABS:
        raise ValueError(f"Неизвестная вкладка: {tab_name}")
    activate_window(pid)
    rel_x, rel_y = TOOLBAR_TABS[tab_name]
    click_rel(pid, rel_x, rel_y)


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
