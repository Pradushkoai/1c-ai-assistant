"""MCP server entry point для Agent-Facade (TD-S5-02, ADR-0013).

Экспонирует 8 lifecycle tools через MCP stdio:
  plan, gather, generate, validate, review, explain, run_cli, data_status.

Сервер тонкий: каждый tool делегирует в ``FacadeHandlers.<handle_*>``.
Handlers инкапсулируют логику (DI через конструктор).

См. ADR-0013 (Agent-Facade), ADR-0010 (MCP tool contracts), ADR-0003 (MCP-архитектура).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from .handlers import FacadeHandlers
from .tool_definitions import FACADE_TOOLS

log = logging.getLogger(__name__)

# Mapping tool_name → handler method name.
_TOOL_TO_HANDLER: dict[str, str] = {
    "plan": "handle_plan",
    "gather": "handle_gather",
    "generate": "handle_generate",
    "validate": "handle_validate",
    "review": "handle_review",
    "explain": "handle_explain",
    "run_cli": "handle_run_cli",
    "data_status": "handle_data_status",
}


def create_facade_server(handlers: FacadeHandlers | None = None) -> Any:
    """Создать MCP server для Facade.

    Args:
        handlers: FacadeHandlers инстанс (с DI). Если None — создаётся
            default (все зависимости None, только data_status/explain работают
            деградированно).

    Returns:
        ``mcp.server.Server`` с зарегистрированными 8 tools.
    """
    from mcp.server import Server
    from mcp.types import TextContent, Tool

    server: Server = Server("1c-ai-facade")
    handlers = handlers or FacadeHandlers()

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        """Вернуть список 8 tools (из FACADE_TOOLS definitions)."""
        return [
            Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["input_schema"],
            )
            for t in FACADE_TOOLS
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> list[Any]:
        """Диспетч tool по name → handler method."""
        if name not in _TOOL_TO_HANDLER:
            return [
                TextContent(
                    type="text",
                    text=f"Unknown tool: {name!r}. Available: {list(_TOOL_TO_HANDLER)}",
                )
            ]

        handler_method = getattr(handlers, _TOOL_TO_HANDLER[name])
        try:
            result = await handler_method(arguments or {})
            import json

            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
        except Exception as exc:  # noqa: BLE001
            log.warning("facade_tool_failed: tool=%s err=%s", name, exc)
            import json

            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"error": str(exc), "tool": name, "type": type(exc).__name__},
                        ensure_ascii=False,
                    ),
                )
            ]

    return server


async def run_facade_server(handlers: FacadeHandlers | None = None) -> None:
    """Точка входа MCP server (stdio).

    Args:
        handlers: FacadeHandlers инстанс. Если None — default (см. create_facade_server).
    """
    import mcp.server.stdio as stdio

    server = create_facade_server(handlers)
    init_options = server.create_initialization_options()
    async with stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)


def run_sync() -> None:
    """Синхронная точка входа для ``[project.scripts]`` в pyproject.toml."""
    # Конфигурируем logging для stdio server.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,  # stdout занят MCP протоколом.
    )
    # Создаём handlers с DI из env (default: все None).
    # В production здесь будут создаваться kb_server, bsl_ls_server, llm,
    # path_manager, config_registry из env/конфига.
    handlers = FacadeHandlers()
    asyncio.run(run_facade_server(handlers))
