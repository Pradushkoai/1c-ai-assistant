"""mcp_servers.shared — общие контракты для всех MCP-серверов.

Экспортирует:
- ToolContract: Protocol для всех MCP tools
- ToolError: базовая ошибка MCP tool
- make_mcp_tool: фабрика для создания mcp.types.Tool из контракта
"""

from __future__ import annotations

from .protocol import ToolContract, ToolError, make_mcp_tool

__all__ = [
    "ToolContract",
    "ToolError",
    "make_mcp_tool",
]
