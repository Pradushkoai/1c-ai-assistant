"""server_factory — единая factory для создания MCP stdio-серверов (TD-S6-03).

6 серверов (ADR-0003):
- facade: 8 lifecycle tools (plan/gather/generate/validate/review/explain/run_cli/data_status)
- metadata: 4 tools (get_metadata/get_form_structure/get_api_reference/get_dependency_graph)
- codebase: 4 tools (semantic_search/get_module/get_similar/call_graph)
- kb: 7 tools (get_pattern/get_antipattern/search_kb/check_method_availability/
  check_antipatterns/get_standard/check_standards)
- bsl_ls: 2 tools (lint/format)
- git: 4 tools (create_branch/commit/open_pr/diff)

Режим C (CONCEPTUAL §1.2): power-user (Cursor) подключается напрямую к доменному
MCP через `1c-ai mcp serve --server {name}`.

См. ADR-0003 (MCP-архитектура), ADR-0010 (MCP tool contracts), D-2026-07-13-12.
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

# ─── Server registry ─────────────────────────────────────────────────────────

SERVER_NAMES: frozenset[str] = frozenset({"facade", "metadata", "codebase", "kb", "bsl_ls", "git"})


def _get_tools_for_server(name: str) -> list[type[Any]]:
    """Вернуть список tool-contract классов для сервера."""
    if name == "facade":
        # Facade tools — это dict definitions (не classes). Возвращаем пустой список,
        # т.к. create_facade_server использует FACADE_TOOLS напрямую.
        from mcp_servers.facade import FACADE_TOOLS

        return FACADE_TOOLS  # type: ignore[return-value]
    if name == "metadata":
        from mcp_servers.metadata import METADATA_TOOLS

        return METADATA_TOOLS
    if name == "codebase":
        from mcp_servers.codebase.contracts import CODEBASE_TOOLS

        return CODEBASE_TOOLS
    if name == "kb":
        from mcp_servers.kb.contracts import KB_TOOLS

        return KB_TOOLS
    if name == "bsl_ls":
        from mcp_servers.bsl_ls.contracts import BSL_LS_TOOLS

        return BSL_LS_TOOLS
    if name == "git":
        from mcp_servers.git import GIT_TOOLS

        return GIT_TOOLS
    raise ValueError(f"Unknown server name: {name!r}. Available: {sorted(SERVER_NAMES)}")


def _get_tool_count(name: str) -> int:
    """Количество tools для сервера."""
    tools = _get_tools_for_server(name)
    return len(tools)


# Доступные серверы для --list.
AVAILABLE_SERVERS: dict[str, int] = {name: _get_tool_count(name) for name in sorted(SERVER_NAMES)}


# ─── Tool dispatch mapping ───────────────────────────────────────────────────


def _build_tool_dispatcher(server_name: str, server_instance: Any) -> dict[str, Any]:
    """Построить mapping tool_name → callable для доменного сервера.

    Args:
        server_name: имя сервера (metadata/codebase/kb/bsl_ls/git).
        server_instance: инстанс сервера (MetadataServer/CodebaseServer/...).

    Returns:
        dict {tool_name: async callable(**kwargs) -> dict}.
    """
    dispatchers: dict[str, Any] = {}

    if server_name == "metadata":
        from mcp_servers.metadata import (
            GetApiReferenceImplementation,
            GetDependencyGraphImplementation,
            GetFormStructureImplementation,
            GetMetadataImplementation,
        )

        dispatchers = {
            "metadata.get_metadata": GetMetadataImplementation(server_instance),
            "metadata.get_form_structure": GetFormStructureImplementation(server_instance),
            "metadata.get_api_reference": GetApiReferenceImplementation(server_instance),
            "metadata.get_dependency_graph": GetDependencyGraphImplementation(server_instance),
        }
    elif server_name == "codebase":
        from mcp_servers.codebase.server import (
            CallGraphImplementation,
            GetModuleImplementation,
            GetSimilarImplementation,
            SemanticSearchImplementation,
        )

        dispatchers = {
            "codebase.semantic_search": SemanticSearchImplementation(server_instance),
            "codebase.get_module": GetModuleImplementation(server_instance),
            "codebase.get_similar": GetSimilarImplementation(server_instance),
            "codebase.call_graph": CallGraphImplementation(server_instance),
        }
    elif server_name == "kb":
        # KbServer методы напрямую (нет *Implementation classes).
        dispatchers = {
            "kb.get_pattern": _wrap_kb_method(server_instance, "get_pattern"),
            "kb.get_antipattern": _wrap_kb_method(server_instance, "get_antipattern"),
            "kb.search_kb": _wrap_kb_method(server_instance, "search_kb"),
            "kb.check_method_availability": _wrap_kb_method(server_instance, "check_method_availability"),
            "kb.check_antipatterns": _wrap_kb_method(server_instance, "check_antipatterns"),
            "kb.get_standard": _wrap_kb_method(server_instance, "get_standard"),
            "kb.check_standards": _wrap_kb_method(server_instance, "check_standards"),
        }
    elif server_name == "bsl_ls":
        from mcp_servers.bsl_ls.server import FormatImplementation, LintImplementation

        dispatchers = {
            "bsl_ls.lint": LintImplementation(server_instance),
            "bsl_ls.format": FormatImplementation(server_instance),
        }
    elif server_name == "git":
        from mcp_servers.git import (
            CommitImplementation,
            CreateBranchImplementation,
            DiffImplementation,
            OpenPrImplementation,
        )

        dispatchers = {
            "git.create_branch": CreateBranchImplementation(server_instance),
            "git.commit": CommitImplementation(server_instance),
            "git.open_pr": OpenPrImplementation(server_instance),
            "git.diff": DiffImplementation(server_instance),
        }

    return dispatchers


def _wrap_kb_method(kb_server: Any, method_name: str) -> Any:
    """Обёрнуть KbServer метод в callable(**kwargs) -> dict (как Implementation)."""

    async def _call(**kwargs: Any) -> dict[str, Any]:
        fn = getattr(kb_server, method_name)
        out = await fn(**kwargs)
        return out.model_dump(mode="json") if hasattr(out, "model_dump") else dict(out)

    return _call


# ─── Server creation ─────────────────────────────────────────────────────────


def _create_server_instance(name: str) -> Any:
    """Создать инстанс доменного сервера (с default DI)."""
    if name == "metadata":
        from mcp_servers.metadata import MetadataServer

        return MetadataServer()
    if name == "codebase":
        from mcp_servers.codebase.server import CodebaseServer

        return CodebaseServer()
    if name == "kb":
        from mcp_servers.kb.server import KbServer

        return KbServer()
    if name == "bsl_ls":
        from mcp_servers.bsl_ls.server import BslLsServer

        return BslLsServer()
    if name == "git":
        from mcp_servers.git import GitServer

        return GitServer()
    raise ValueError(f"Unknown server name: {name!r}")


def _get_tool_definitions(name: str) -> list[dict[str, Any]]:
    """Вернуть list of {name, description, input_schema} для server.list_tools()."""
    if name == "facade":
        from mcp_servers.facade import FACADE_TOOLS

        return FACADE_TOOLS  # уже list[dict]
    # Для доменных: строим из *_TOOLS классов-контрактов.
    tools = _get_tools_for_server(name)
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in tools
    ]


def create_domain_server(server_name: str, **kwargs: Any) -> Any:
    """Создать MCP server для доменного сервера или Facade.

    Args:
        server_name: facade|metadata|codebase|kb|bsl_ls|git.
        **kwargs: для facade — handlers (FacadeHandlers); для доменных — игнорируется
            (создаётся default инстанс через _create_server_instance).

    Returns:
        ``mcp.server.Server`` с зарегистрированными tools.

    Raises:
        ValueError: если server_name неизвестен.
    """
    if server_name not in SERVER_NAMES:
        raise ValueError(f"Unknown server name: {server_name!r}. Available: {sorted(SERVER_NAMES)}")

    # Facade — делегируем в create_facade_server (уже реализован в TD-S5-02).
    if server_name == "facade":
        from mcp_servers.facade import FacadeHandlers, create_facade_server

        handlers = kwargs.get("handlers")
        if handlers is None:
            # Без DI — default FacadeHandlers (только data_status/explain работают
            # деградированно). Production DI — ответственность agent-слоя
            # (caller передаёт handlers=... через kwargs).
            log.warning(
                "server_factory: facade handlers not provided, using default (degraded). Pass handlers=... for full DI."
            )
            handlers = FacadeHandlers()
        return create_facade_server(handlers)

    # Доменные серверы.
    from mcp.server import Server
    from mcp.types import TextContent, Tool

    server_instance = _create_server_instance(server_name)
    dispatchers = _build_tool_dispatcher(server_name, server_instance)
    tool_defs = _get_tool_definitions(server_name)

    server: Server = Server(f"1c-ai-{server_name}")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=td["name"],
                description=td["description"],
                inputSchema=td["input_schema"],
            )
            for td in tool_defs
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> list[Any]:
        if name not in dispatchers:
            return [
                TextContent(
                    type="text",
                    text=f"Unknown tool: {name!r}. Available: {list(dispatchers)}",
                )
            ]
        try:
            result = await dispatchers[name](**(arguments or {}))
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
        except Exception as exc:  # noqa: BLE001
            log.warning("server_factory tool failed: server=%s tool=%s err=%s", server_name, name, exc)
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


async def run_domain_server(server_name: str, **kwargs: Any) -> None:
    """Запустить MCP stdio-сервер.

    Args:
        server_name: facade|metadata|codebase|kb|bsl_ls|git.
        **kwargs: передаются в create_domain_server.
    """
    import mcp.server.stdio as stdio

    server = create_domain_server(server_name, **kwargs)
    init_options = server.create_initialization_options()
    async with stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)


def list_servers() -> str:
    """Вернуть человекочитаемый список доступных серверов для --list."""
    lines = ["Available MCP servers:"]
    for name in sorted(SERVER_NAMES):
        count = AVAILABLE_SERVERS[name]
        lines.append(f"  {name:12s}  {count} tools")
    return "\n".join(lines)
