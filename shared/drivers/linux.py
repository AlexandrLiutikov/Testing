"""Linux-адаптер Platform Driver Layer (заглушка).

Реализация через AT-SPI / xdotool — будет добавлена в следующем этапе.
Все методы бросают NotImplementedError.
"""

from typing import Optional, Tuple

from shared.drivers.base import BaseDriver


class LinuxDriver(BaseDriver):
    """Заглушка Linux-драйвера.

    Планируемые технологии:
    - AT-SPI (pyatspi) для доступа к элементам доступности
    - xdotool как fallback для координатных кликов
    """

    def activate_window(self, pid: int) -> None:
        raise NotImplementedError("LinuxDriver.activate_window — ещё не реализован")

    def click_rel(self, pid: int, rel_x: float, rel_y: float) -> None:
        raise NotImplementedError("LinuxDriver.click_rel — ещё не реализован")

    def send_escape(self, pid: int) -> None:
        raise NotImplementedError("LinuxDriver.send_escape — ещё не реализован")

    def get_window_rect(self, pid: int) -> Optional[Tuple[int, int, int, int]]:
        raise NotImplementedError("LinuxDriver.get_window_rect — ещё не реализован")

    @staticmethod
    def kill_editors() -> None:
        raise NotImplementedError("LinuxDriver.kill_editors — ещё не реализован")

    @staticmethod
    def launch_editor(editor_path: str) -> None:
        raise NotImplementedError("LinuxDriver.launch_editor — ещё не реализован")
