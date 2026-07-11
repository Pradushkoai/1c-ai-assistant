"""mcp_servers.kb — база знаний + platform methods.

Контракты: GetPattern, GetAntipattern, SearchKb, CheckMethodAvailability,
CheckAntipatterns (5 tools).
Реализация: KbServer через KBCollection (YAML loader + regex detector).
"""

from __future__ import annotations

from .contracts import KB_TOOLS
from .loader import KBCollection
from .server import KbServer

__all__ = [
    "KB_TOOLS",
    "KBCollection",
    "KbServer",
]
