"""macOS-адаптер Platform Driver Layer (заглушка).

Реализация через AXUIElement / cliclick — будет добавлена в следующем этапе.
Все методы бросают NotImplementedError.
"""

from typing import Optional, Tuple

from shared.drivers.base import BaseDriver


class MacOSDriver(BaseDriver):
    """Заглушка macOS-драйвера.

    Планируемые технологии:
    - AXUIElement (atomacos / pyobjc) для доступа к элементам доступности
    - cliclick как fallback для координатных кликов
    """

    def activate_window(self, pid: int) -> None:
        raise NotImplementedError("MacOSDriver.activate_window — ещё не реализован")

    def click_menu_item(self, pid: int, menu_name: str) -> bool:
        raise NotImplementedError("MacOSDriver.click_menu_item — ещё не реализован")

    def click_rel(self, pid: int, rel_x: float, rel_y: float) -> None:
        raise NotImplementedError("MacOSDriver.click_rel — ещё не реализован")

    def send_escape(self, pid: int) -> None:
        raise NotImplementedError("MacOSDriver.send_escape — ещё не реализован")

    def get_window_rect(self, pid: int) -> Optional[Tuple[int, int, int, int]]:
        raise NotImplementedError("MacOSDriver.get_window_rect — ещё не реализован")

    @staticmethod
    def kill_editors() -> None:
        raise NotImplementedError("MacOSDriver.kill_editors — ещё не реализован")

    @staticmethod
    def launch_editor(editor_path: str) -> None:
        raise NotImplementedError("MacOSDriver.launch_editor — ещё не реализован")
