"""Пакет Platform Driver Layer.

Единая точка входа — функция ``get_driver()``, которая возвращает
singleton-экземпляр драйвера, соответствующего текущей ОС.
"""

import platform
from functools import lru_cache
from typing import TYPE_CHECKING

from shared.drivers.base import BaseDriver

if TYPE_CHECKING:
    from shared.drivers.windows import WindowsDriver  # noqa: F401
    from shared.drivers.linux import LinuxDriver      # noqa: F401
    from shared.drivers.macos import MacOSDriver      # noqa: F401


def _current_platform_driver() -> BaseDriver:
    """Создать экземпляр драйвера для текущей ОС."""
    system = platform.system()

    if system == "Windows":
        from shared.drivers.windows import WindowsDriver
        return WindowsDriver()

    elif system == "Linux":
        from shared.drivers.linux import LinuxDriver
        return LinuxDriver()

    elif system == "Darwin":
        from shared.drivers.macos import MacOSDriver
        return MacOSDriver()

    else:
        raise RuntimeError(f"Неподдерживаемая платформа: {system}")


@lru_cache(maxsize=1)
def get_driver() -> BaseDriver:
    """Вернуть singleton-драйвер для текущей платформы.

    Кэшируется при первом вызове — дальнейшие вызовы бесплатны.
    """
    return _current_platform_driver()


__all__ = ["get_driver", "BaseDriver"]
