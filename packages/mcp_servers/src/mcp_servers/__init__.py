"""mcp_servers — 5 доменных MCP-серверов + Facade.

Пакеты:
- shared: общие контракты (ToolContract Protocol, ToolError)
- metadata: метаданные 1С (4 tools)
- codebase: BSL-код (4 tools)
- kb: база знаний (7 tools)
- bsl_ls: BSL Language Server (2 tools)
- git: git operations (4 tools)
- facade: 8 lifecycle tools (plan/gather/generate/validate/review/explain/run_cli/data_status)
- server_factory: единая factory для создания MCP stdio-серверов (TD-S6-03)

Итого: 21 доменных tools + 8 facade tools = 29 tools.

См. ADR-0003 (MCP: Facade + 5 доменных серверов).
"""

from __future__ import annotations

from .server_factory import (
    AVAILABLE_SERVERS,
    SERVER_NAMES,
    create_domain_server,
    list_servers,
    run_domain_server,
)
from .shared import ToolContract, ToolError, make_mcp_tool

__all__ = [
    "ToolContract",
    "ToolError",
    "make_mcp_tool",
    # server_factory (TD-S6-03)
    "SERVER_NAMES",
    "AVAILABLE_SERVERS",
    "create_domain_server",
    "run_domain_server",
    "list_servers",
]
