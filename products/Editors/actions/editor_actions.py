"""Semantic actions для Editors — продуктовый слой (§16, §17 SCRIPT_RULES)."""

import time

from shared.drivers import get_driver


MENU_POINTS = {
    "home":      (0.07, 0.175),
    "templates": (0.07, 0.245),
    "local":     (0.07, 0.305),
    "collab":    (0.07, 0.385),
    "settings":  (0.07, 0.865),
    "about":     (0.07, 0.925),
}


def click_menu(pid: int, menu_key: str):
    """Активировать окно и кликнуть по пункту левого меню стартового экрана."""
    if menu_key not in MENU_POINTS:
        raise ValueError(f"Неизвестный пункт меню: {menu_key}")
    driver = get_driver()
    driver.activate_window(pid)
    rel_x, rel_y = MENU_POINTS[menu_key]
    driver.click_rel(pid, rel_x, rel_y)
    time.sleep(0.6)  # ожидание перехода (Semantic Actions Layer)


def dismiss_collab_popup(pid: int):
    """Закрыть модальное окно подключения дисков клавишей Esc."""
    driver = get_driver()
    driver.send_escape(pid)


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
