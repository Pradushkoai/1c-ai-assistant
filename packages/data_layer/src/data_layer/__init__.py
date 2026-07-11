"""data_layer — PathManager, ConfigRegistry, freshness check.

Контракты: см. docs/architecture/03-paths-protocol.md и ADR-0008.

Экспортируемые классы:
- PathManagerProtocol: Protocol для тестирования с mock
- PathManager: реализация с ${VAR} подстановкой из paths.env
- ConfigRegistry: реестр загруженных конфигураций 1С
- is_fresh, latest_mtime: функции freshness check
"""

from __future__ import annotations

from .config_registry import ConfigRegistry
from .freshness import is_fresh, latest_mtime
from .path_manager import PathManager, PathManagerProtocol

__all__ = [
    "PathManager",
    "PathManagerProtocol",
    "ConfigRegistry",
    "is_fresh",
    "latest_mtime",
]
