"""MCP server entry point для Agent-Facade — заглушка.

В Sprint 1.5 (каркас) — stub. Реализация в Sprint 4.

См. ADR-0013 (Agent-Facade — 7 lifecycle tools).
"""

from __future__ import annotations

from typing import Any


def create_facade_server() -> Any:
    """Создать MCP server для Facade.

    Returns:
        mcp.server.Server instance.

    Raises:
        NotImplementedError: в Sprint 1.5 (каркас).
    """
    raise NotImplementedError("create_facade_server — реализация в Sprint 4")


async def run_facade_server() -> None:
    """Точка входа MCP server (stdio).

    Raises:
        NotImplementedError: в Sprint 1.5 (каркас).
    """
    raise NotImplementedError("run_facade_server — реализация в Sprint 4")


def run_sync() -> None:
    """Синхронная точка входа для [project.scripts] в pyproject.toml.

    Raises:
        NotImplementedError: в Sprint 1.5 (каркас).
    """
    raise NotImplementedError("run_sync — реализация в Sprint 4")
