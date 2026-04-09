"""Базовый (абстрактный) интерфейс Platform Driver Layer.

Определяет контракт, которую обязан реализовать каждый платформенный
адаптер (windows.py, linux.py, macos.py).  Тесты работают только с этим
интерфейсом и не знают о конкретной ОС.
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple


class BaseDriver(ABC):
    """Единый контракт драйвера для взаимодействия с ОС и UI."""

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------

    @abstractmethod
    def activate_window(self, pid: int) -> None:
        """Активировать окно процесса *pid* и передать ему фокус."""
        ...

    # ------------------------------------------------------------------
    # Semantic UI interaction (primary path)
    # ------------------------------------------------------------------

    @abstractmethod
    def click_menu_item(self, pid: int, menu_name: str) -> bool:
        """Кликнуть по пункту меню, найдя его семантически.

        Цепочка fallback:
        1. Accessibility API (UIAutomation)
        2. OCR скриншота + координаты текста
        3. Координатный клик (крайний резерв, логируется)
        4. Computer Vision (если доступен)

        Возвращает True, если клик выполнен успешно.
        """
        ...

    # ------------------------------------------------------------------
    # Input simulation (coordinate fallback)
    # ------------------------------------------------------------------

    @abstractmethod
    def click_rel(self, pid: int, rel_x: float, rel_y: float) -> None:
        """Кликнуть по относительной позиции внутри окна процесса *pid*.

        *rel_x* и *rel_y* — доли от 0.0 до 1.0 (левый-верхний угол →
        правый-нижний).

        ВНИМАНИЕ: Это метод — fallback для крайнего резерва.
        Основной путь — click_menu_item() с семантическим поиском.
        """
        ...

    @abstractmethod
    def send_escape(self, pid: int) -> None:
        """Эмулировать нажатие клавиши Escape в окне процесса *pid*."""
        ...

    def paste_text(self, pid: int, text: str) -> None:
        """Вставить текст в активный редактор через системный буфер обмена."""
        raise NotImplementedError("paste_text не реализован для текущей платформы")

    def align_paragraph_left(self, pid: int) -> None:
        """Выровнять абзац по левому краю (обычно hotkey Ctrl+L)."""
        raise NotImplementedError(
            "align_paragraph_left не реализован для текущей платформы"
        )

    def undo_action(self, pid: int) -> None:
        """Отменить последнее действие (обычно Ctrl+Z)."""
        raise NotImplementedError("undo_action не реализован для текущей платформы")

    def redo_action(self, pid: int) -> None:
        """Повторить отменённое действие (обычно Ctrl+Y)."""
        raise NotImplementedError("redo_action не реализован для текущей платформы")

    def save_document(self, pid: int) -> None:
        """Вызвать сохранение документа (обычно Ctrl+S)."""
        raise NotImplementedError("save_document не реализован для текущей платформы")

    def confirm_dialog(self, pid: int) -> None:
        """Подтвердить активный диалог клавишей Enter."""
        raise NotImplementedError("confirm_dialog не реализован для текущей платформы")

    def close_current_tab(self, pid: int) -> None:
        """Закрыть текущую вкладку редактора (обычно Ctrl+F4)."""
        raise NotImplementedError(
            "close_current_tab не реализован для текущей платформы"
        )

    def click_current_tab_close_button(self, pid: int) -> bool:
        """Кликнуть по UI-кнопке `X` активной вкладки документа.

        Возвращает True, если клик выполнен.
        """
        return False

    # ------------------------------------------------------------------
    # Window geometry (нужен для координатных кликов)
    # ------------------------------------------------------------------

    @abstractmethod
    def get_window_rect(self, pid: int) -> Optional[Tuple[int, int, int, int]]:
        """Вернуть координаты окна ``(left, top, right, bottom)`` или ``None``."""
        ...

    # ------------------------------------------------------------------
    # Modal / warning detection (может быть не реализован на некоторых ОС)
    # ------------------------------------------------------------------

    def detect_warning(self, pid: int, timeout_sec: int = 10) -> bool:
        """Проверить наличие модального предупреждения у процесса *pid*."""
        # По умолчанию — не поддерживается; платформа может переопределить.
        return False

    def dismiss_warning(self, pid: int) -> bool:
        """Закрыть предупреждение (кнопка OK / Enter fallback)."""
        return False

    # ------------------------------------------------------------------
    # Process management (тонкая обёртка; может быть общей)
    # ------------------------------------------------------------------

    @staticmethod
    def kill_editors() -> None:
        """Завершить все процессы editors/editors_helper.

        Статический метод — общая утилита, не требует экземпляра.
        """
        raise NotImplementedError

    @staticmethod
    def launch_editor(editor_path: str, enable_debug: bool = True) -> None:
        """Запустить редактор по указанному пути.

        Args:
            editor_path: путь к редактору.
            enable_debug: запускать ли с debug-флагом (если поддерживается).
        """
        raise NotImplementedError
