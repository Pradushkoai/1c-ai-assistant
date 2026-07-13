"""`1c-ai serve` — запуск HTTP REST API server (TD-S7-02).

FastAPI/uvicorn HTTP server на :8000 (default). Endpoints:
- GET  /health — health check (persistence + BSL LS)
- GET  /servers — список MCP серверов
- GET  /tools/{server} — список tools
- POST /facade/{tool} — вызов Facade lifecycle tool
- POST /domain/{server}/{tool} — вызов доменного tool

Stateless: state через FacadeStateStore (survival-restart, TD-S7-01).

См. ADR-0003, ADR-0013, ADR-0015, D-2026-07-13-14.
"""

from __future__ import annotations

import logging

import click


def cmd_serve(host: str, port: int) -> int:
    """Запустить HTTP REST API server.

    Args:
        host: bind host (default 0.0.0.0 — для Docker).
        port: bind port (default 8000).

    Returns:
        0 при успехе, 1 при ошибке.
    """
    import asyncio

    # Логи в stderr (stdout может использоваться для HTTP ответов).
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Создаём handlers с полным DI (agent-слой responsibility).
    try:
        from mcp_servers.http_server import run_http_server

        from .facade_entry import create_facade_handlers

        handlers = create_facade_handlers()
    except Exception as exc:  # noqa: BLE001
        click.echo(f"❌ Cannot create handlers: {exc}", err=True)
        return 1

    click.echo(f"🚀 Starting 1C AI Assistant HTTP server on {host}:{port}", err=True)
    click.echo("   GET  /health", err=True)
    click.echo("   GET  /servers", err=True)
    click.echo("   GET  /tools/{server}", err=True)
    click.echo("   POST /facade/{tool}", err=True)
    click.echo("   POST /domain/{server}/{tool}", err=True)
    click.echo("   Docs: http://localhost:8000/docs", err=True)

    try:
        asyncio.run(run_http_server(host=host, port=port, handlers=handlers))
        return 0
    except KeyboardInterrupt:
        click.echo("\nHTTP server stopped.", err=True)
        return 0
    except Exception as exc:  # noqa: BLE001
        click.echo(f"❌ HTTP server error: {exc}", err=True)
        return 1
