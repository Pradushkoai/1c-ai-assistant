"""mcp_servers.bsl_ls — BSL Language Server.

Контракты: Lint, Format (2 tools).
Реализация: BslLsServer — обёртка над BslLsBackend (subprocess/http/stub).
Runner: standalone-функции для запуска BSL LS (shared с docker/bsl_ls_http_server.py).
"""

from __future__ import annotations

from .backends import (
    BslLsBackend,
    HttpBslLsBackend,
    StubBslLsBackend,
    SubprocessBslLsBackend,
    make_bsl_ls_backend,
)
from .contracts import BSL_LS_TOOLS
from .server import BslLsServer, FormatImplementation, LintImplementation

__all__ = [
    "BSL_LS_TOOLS",
    "BslLsServer",
    "LintImplementation",
    "FormatImplementation",
    # Backends (TD-S8-02)
    "BslLsBackend",
    "SubprocessBslLsBackend",
    "HttpBslLsBackend",
    "StubBslLsBackend",
    "make_bsl_ls_backend",
]
