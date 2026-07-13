"""`1c-ai mcp serve` — запуск MCP stdio-сервера (TD-S6-03).

6 серверов (ADR-0003):
  facade     — 8 lifecycle tools (для Cursor: plan→gather→generate→validate→review)
  metadata   — 4 tools (метаданные 1С: get_metadata/get_form_structure/...)
  codebase   — 4 tools (BSL-код: semantic_search/get_module/get_similar/call_graph)
  kb         — 7 tools (база знаний: patterns/antipatterns/standards)
  bsl_ls     — 2 tools (BSL Language Server: lint/format)
  git        — 4 tools (git operations: create_branch/commit/open_pr/diff)

Режим C (CONCEPTUAL §1.2): power-user (Cursor) подключается напрямую к доменному
MCP через `1c-ai mcp serve --server {name}`.

См. ADR-0003 (MCP-архитектура), D-2026-07-13-12.
"""

from __future__ import annotations

import sys

import click


def cmd_mcp_serve(server: str, list_only: bool) -> int:
    """Запустить MCP stdio-сервер.

    Args:
        server: имя сервера (facade|metadata|codebase|kb|bsl_ls|git).
        list_only: если True — показать список серверов и выйти.

    Returns:
        0 при успехе, 1 при ошибке.
    """
    if list_only:
        from mcp_servers import list_servers

        click.echo(list_servers())
        return 0

    from mcp_servers import SERVER_NAMES, run_domain_server

    if server not in SERVER_NAMES:
        click.echo(
            f"❌ Unknown server: {server!r}. Available: {sorted(SERVER_NAMES)}",
            err=True,
        )
        click.echo("Use `1c-ai mcp serve --list` to see available servers.", err=True)
        return 1

    import asyncio
    import logging

    # stdout занят MCP протоколом — логи в stderr.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    # Для facade — создаём handlers с полным DI (agent-слой responsibility).
    kwargs: dict[str, object] = {}
    if server == "facade":
        try:
            from .facade_entry import create_facade_handlers

            kwargs["handlers"] = create_facade_handlers()
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning(
                "mcp_serve: facade_entry failed, using default handlers: %s", exc
            )

    try:
        asyncio.run(run_domain_server(server, **kwargs))
        return 0
    except KeyboardInterrupt:
        click.echo("\nMCP server stopped.", err=True)
        return 0
    except Exception as exc:  # noqa: BLE001
        click.echo(f"❌ MCP server error: {exc}", err=True)
        return 1
