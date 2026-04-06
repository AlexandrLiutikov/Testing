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
) -> int:
    """Полный цикл запуска: kill → launch → detect main window.

    Args:
        editor_path: Путь к исполняемому файлу редактора.
        process_name: Имя процесса для поиска.
        wait_timeout_sec: Максимальное время ожидания появления окна.

    Returns:
        PID главного окна редактора.

    Raises:
        RuntimeError: Если окно не появилось в течение timeout.
    """
    driver = get_driver()

    # 1. Kill
    driver.kill_editors()

    # 2. Launch
    driver.launch_editor(editor_path)

    # 3. Detect main window
    pid = wait_main_proc(process_name, wait_timeout_sec)
    if pid is None:
        raise RuntimeError(
            f"Окно редактора («{process_name}») не появилось "
            f"в течение {wait_timeout_sec} секунд"
        )

    # 4. Activate
    driver.activate_window(pid)

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
