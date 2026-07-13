"""HTTP server для 1C AI Assistant (TD-S7-02, REST API).

FastAPI app с endpoints:
- ``GET /health`` — health check (persistence + BSL LS). Для Docker/k8s probe.
- ``GET /servers`` — список доступных MCP серверов.
- ``GET /tools/{server_name}`` — список tools для сервера.
- ``POST /facade/{tool}`` — вызов Facade lifecycle tool.
- ``POST /domain/{server_name}/{tool}`` — вызов доменного tool.

Stateless: state через FacadeStateStore (TD-S7-01, survival-restart).

См. ADR-0003 (MCP-архитектура), ADR-0013 (Agent-Facade), ADR-0015 (deployment),
D-2026-07-13-14.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .facade.handlers import FacadeHandlers
from .server_factory import (
    AVAILABLE_SERVERS,
    SERVER_NAMES,
    _build_tool_dispatcher,
    _create_server_instance,
    _get_tool_definitions,
)

log = logging.getLogger(__name__)


# ─── Request/Response models ────────────────────────────────────────────────


class ToolRequest(BaseModel):
    """Request body для POST /facade/{tool} и /domain/{server}/{tool}."""

    args: dict[str, Any] = {}


class HealthResponse(BaseModel):
    """Response для GET /health."""

    status: str
    checks: dict[str, Any]


# ─── App factory ─────────────────────────────────────────────────────────────


def create_http_app(handlers: FacadeHandlers | None = None) -> FastAPI:
    """Создать FastAPI app для REST API.

    Args:
        handlers: FacadeHandlers инстанс (с DI). Если None — создаётся default.

    Returns:
        FastAPI app с зарегистрированными endpoints.
    """
    app = FastAPI(
        title="1C AI Assistant",
        description="REST API для Facade + доменных MCP серверов",
        version="0.5.0",
    )
    handlers = handlers or FacadeHandlers()

    # ─── GET /health ─────────────────────────────────────────────────────────
    @app.get("/health", response_model=HealthResponse)
    async def health() -> dict[str, Any]:
        """Health check — persistence + BSL LS ping (для Docker/k8s probe)."""
        import os

        checks: dict[str, Any] = {}
        all_ok = True

        # Persistence check (если state_store с checkpointer).
        try:
            state_store = getattr(handlers, "_state_store", None)
            if state_store is not None and state_store.is_persistent:
                # Пробный load (несуществующий plan_id → None, без побочных эффектов).
                await state_store.load_state("__healthcheck__")
                checks["persistence"] = {
                    "status": "ok",
                    "type": "postgres" if state_store.is_postgres else "memory",
                }
            else:
                checks["persistence"] = {"status": "skipped", "reason": "in-memory"}
        except Exception as exc:  # noqa: BLE001
            all_ok = False
            checks["persistence"] = {"status": "failed", "error": str(exc)}

        # BSL LS ping (если URL задан).
        bsl_ls_url = os.environ.get("BSL_LS_HTTP_URL")
        if bsl_ls_url:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.get(f"{bsl_ls_url}/health")
                    if response.status_code == 200:
                        data = response.json()
                        checks["bsl_ls"] = {
                            "status": "ok",
                            "bsl_ls_available": bool(data.get("bsl_ls_available", False)),
                        }
                    else:
                        all_ok = False
                        checks["bsl_ls"] = {
                            "status": "failed",
                            "http_status": response.status_code,
                        }
            except Exception as exc:  # noqa: BLE001
                all_ok = False
                checks["bsl_ls"] = {"status": "failed", "error": str(exc)}
        else:
            checks["bsl_ls"] = {"status": "skipped", "reason": "BSL_LS_HTTP_URL not set"}

        return {"status": "ok" if all_ok else "failed", "checks": checks}

    # ─── GET /servers ────────────────────────────────────────────────────────
    @app.get("/servers")
    async def list_servers() -> dict[str, Any]:
        """Список доступных MCP серверов."""
        return {
            "servers": [
                {"name": name, "tools_count": count}
                for name, count in AVAILABLE_SERVERS.items()
            ],
            "total": len(SERVER_NAMES),
        }

    # ─── GET /tools/{server_name} ────────────────────────────────────────────
    @app.get("/tools/{server_name}")
    async def list_tools(server_name: str) -> dict[str, Any]:
        """Список tools для сервера."""
        if server_name not in SERVER_NAMES:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown server: {server_name!r}. Available: {sorted(SERVER_NAMES)}",
            )
        tool_defs = _get_tool_definitions(server_name)
        return {
            "server": server_name,
            "tools": tool_defs,
            "count": len(tool_defs),
        }

    # ─── POST /facade/{tool} ─────────────────────────────────────────────────
    @app.post("/facade/{tool}")
    async def call_facade_tool(tool: str, request: ToolRequest) -> dict[str, Any]:
        """Вызов Facade lifecycle tool (plan/gather/generate/validate/review/explain/run_cli/data_status)."""
        from .facade.handlers import FacadeNotConfiguredError

        # Mapping tool_name → handler method (как в facade/server.py).
        tool_to_handler = {
            "plan": "handle_plan",
            "gather": "handle_gather",
            "generate": "handle_generate",
            "validate": "handle_validate",
            "review": "handle_review",
            "explain": "handle_explain",
            "run_cli": "handle_run_cli",
            "data_status": "handle_data_status",
        }

        if tool not in tool_to_handler:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown facade tool: {tool!r}. Available: {list(tool_to_handler)}",
            )

        handler_method = getattr(handlers, tool_to_handler[tool])
        try:
            result = await handler_method(request.args)
            return {"tool": tool, "result": result}
        except FacadeNotConfiguredError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            log.warning("http facade tool failed: tool=%s err=%s", tool, exc)
            raise HTTPException(
                status_code=500,
                detail=f"{type(exc).__name__}: {exc}",
            ) from exc

    # ─── POST /domain/{server_name}/{tool} ───────────────────────────────────
    @app.post("/domain/{server_name}/{tool}")
    async def call_domain_tool(
        server_name: str, tool: str, request: ToolRequest
    ) -> dict[str, Any]:
        """Вызов доменного tool (metadata/codebase/kb/bsl_ls/git)."""
        if server_name not in SERVER_NAMES:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown server: {server_name!r}. Available: {sorted(SERVER_NAMES)}",
            )
        if server_name == "facade":
            raise HTTPException(
                status_code=400,
                detail="Use /facade/{tool} for facade tools, not /domain/facade/{tool}",
            )

        # Создаём server instance + dispatcher (кешировать для performance — future TD).
        try:
            server_instance = _create_server_instance(server_name)
            dispatchers = _build_tool_dispatcher(server_name, server_instance)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail=f"Cannot create {server_name} server: {exc}",
            ) from exc

        full_tool_name = f"{server_name}.{tool}"
        if full_tool_name not in dispatchers:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown tool: {full_tool_name!r}. Available: {list(dispatchers)}",
            )

        try:
            result = await dispatchers[full_tool_name](**request.args)
            return {"tool": full_tool_name, "result": result}
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            log.warning("http domain tool failed: server=%s tool=%s err=%s", server_name, tool, exc)
            raise HTTPException(
                status_code=500,
                detail=f"{type(exc).__name__}: {exc}",
            ) from exc

    # ─── Root ────────────────────────────────────────────────────────────────
    @app.get("/")
    async def root() -> dict[str, Any]:
        """Root — basic info."""
        return {
            "name": "1C AI Assistant",
            "version": "0.5.0",
            "endpoints": [
                "GET /health",
                "GET /servers",
                "GET /tools/{server_name}",
                "POST /facade/{tool}",
                "POST /domain/{server_name}/{tool}",
            ],
            "docs": "/docs",
        }

    return app


async def run_http_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    handlers: FacadeHandlers | None = None,
) -> None:
    """Запустить HTTP server (uvicorn).

    Args:
        host: bind host (default 0.0.0.0 — для Docker).
        port: bind port (default 8000).
        handlers: FacadeHandlers инстанс. Если None — default.
    """
    import uvicorn

    app = create_http_app(handlers)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
