"""mcp_servers — 5 доменных MCP-серверов + Facade.

Пакеты:
- shared: общие контракты (ToolContract Protocol, ToolError)
- metadata: метаданные 1С (4 tools)
- codebase: BSL-код (4 tools)
- kb: база знаний (5 tools)
- bsl_ls: BSL Language Server (2 tools)
- git: git operations (4 tools)
- facade: 7 lifecycle tools + data_status

Итого: 19 доменных tools + 8 facade tools.

См. ADR-0003 (MCP: Facade + 5 доменных серверов).
"""

from __future__ import annotations

from .shared import ToolContract, ToolError, make_mcp_tool

__all__ = [
    "ToolContract",
    "ToolError",
    "make_mcp_tool",
]
