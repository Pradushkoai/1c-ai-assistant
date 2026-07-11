"""mcp_servers.bsl_ls — BSL Language Server.

Контракты: Lint, Format (2 tools).
Реализация: BslLsServer — HTTP клиент к 1c-ai-bsl-ls контейнеру.
"""

from __future__ import annotations

from .contracts import BSL_LS_TOOLS
from .server import BslLsServer, FormatImplementation, LintImplementation

__all__ = [
    "BSL_LS_TOOLS",
    "BslLsServer",
    "LintImplementation",
    "FormatImplementation",
]
