"""Управление жизненным циклом приложения.

Единый reusable-модуль для всех тест-кейсов:
  - kill ранее запущенных процессов
  - запуск редактора
  - detection главного окна
  - dismiss стартовых окон/диалогов
"""

from typing import Optional

from shared.drivers import get_driver
from shared.infra.waits import wait_main_proc


def app_lifecycle(
    editor_path: str,
    process_name: str = "editors",
    wait_timeout_sec: float = 20,
    return_info: bool = False,
):
    """Полный цикл запуска: kill → launch → detect main window.

    Args:
        editor_path: Путь к исполняемому файлу редактора.
        process_name: Имя процесса для поиска.
        wait_timeout_sec: Максимальное время ожидания появления окна.

    Returns:
        PID главного окна редактора или `(pid, launch_info)` при `return_info=True`.

    Raises:
        RuntimeError: Если окно не появилось в течение timeout.
    """
    driver = get_driver()

    # 1. Kill
    driver.kill_editors()

    launch_info = {
        "fallback_used": False,
        "launch_mode": "debug",
        "fallback_source": None,
        "fallback_reason": "",
        "attempts": [],
    }

    # 2. Launch (debug mode first)
    driver.launch_editor(editor_path, enable_debug=True)
    pid = wait_main_proc(process_name, wait_timeout_sec)
    launch_info["attempts"].append({"mode": "debug", "success": pid is not None})

    # 2b. Fallback: standard launch without debug flag
    if pid is None:
        launch_info["fallback_used"] = True
        launch_info["launch_mode"] = "standard"
        launch_info["fallback_source"] = "LAUNCH_NO_DEBUG"
        launch_info["fallback_reason"] = (
            "Запуск с debug-флагом не дал главное окно в пределах timeout; "
            "выполнен повторный запуск без debug-флага."
        )
        driver.kill_editors()
        driver.launch_editor(editor_path, enable_debug=False)
        pid = wait_main_proc(process_name, wait_timeout_sec)
        launch_info["attempts"].append({"mode": "standard", "success": pid is not None})

    # 3. Detect main window
    if pid is None:
        launch_info["launch_mode"] = "failed"
        raise RuntimeError(
            f"Окно редактора («{process_name}») не появилось "
            f"в течение {wait_timeout_sec} секунд ни в debug-, ни в standard-режиме."
        )

    # 4. Activate
    driver.activate_window(pid)

    if return_info:
        return pid, launch_info
    return pid


def dismiss_start_dialogs(pid: int) -> None:
    """Закрыть все стартовые окна/предупреждения после запуска.

    Последовательность:
      1. Предупреждение о регистрации (UIAutomation + Enter fallback)
      2. Модальные окна подключения дисков (Esc)

    Вызывается ПОСЛЕ app_lifecycle() перед основным сценарием.
    """
    from products.Editors.actions.editor_actions import (
        dismiss_warning,
        dismiss_collab_popup,
    )

    # Пробуем закрыть предупреждение о регистрации
    try:
        dismiss_warning(pid)
    except Exception:
        pass  # Может не быть — это нормально

    # Пробуем закрыть popup совместной работы
    try:
        dismiss_collab_popup(pid)
    except Exception:
        pass  # Может не быть — это нормально
