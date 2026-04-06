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
    # Input simulation
    # ------------------------------------------------------------------

    @abstractmethod
    def click_rel(self, pid: int, rel_x: float, rel_y: float) -> None:
        """Кликнуть по относительной позиции внутри окна процесса *pid*.

        *rel_x* и *rel_y* — доли от 0.0 до 1.0 (левый-верхний угол →
        правый-нижний).
        """
        ...

    @abstractmethod
    def send_escape(self, pid: int) -> None:
        """Эмулировать нажатие клавиши Escape в окне процесса *pid*."""
        ...

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
    def launch_editor(editor_path: str) -> None:
        """Запустить редактор по указанному пути."""
        raise NotImplementedError
