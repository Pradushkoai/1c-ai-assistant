"""tests/agent/test_cli_serve.py — `1c-ai serve` HTTP REST API (TD-S7-02).

Покрытие:
- GET /health → 200 + JSON structure (status, checks).
- GET /servers → 200 + 6 серверов.
- GET /tools/facade → 200 + 8 tools.
- GET /tools/unknown → 404.
- POST /facade/data_status → 200 + JSON result.
- POST /facade/unknown → 404.
- POST /domain/unknown_server/foo → 404.
- POST /domain/facade/foo → 400 (use /facade/ instead).
- CLI registration: `1c-ai serve --help`.

См. ADR-0003, ADR-0013, D-2026-07-13-14.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def http_client() -> TestClient:
    """TestClient для FastAPI app с default FacadeHandlers."""
    from mcp_servers.http_server import create_http_app

    app = create_http_app()
    return TestClient(app)


@pytest.fixture
def http_client_with_handlers() -> TestClient:
    """TestClient с mock FacadeHandlers (для POST /facade/{tool} tests)."""
    from mcp_servers.facade.handlers import FacadeHandlers
    from mcp_servers.http_server import create_http_app

    handlers = MagicMock(spec=FacadeHandlers)
    # data_status — async, возвращает dict.
    handlers.handle_data_status = AsyncMock(
        return_value={
            "paths": {"data_dir": True},
            "configs": [],
            "indexes_freshness": {},
            "missing_prerequisites": [],
        }
    )
    handlers._state_store = MagicMock()
    handlers._state_store.is_persistent = False

    app = create_http_app(handlers=handlers)
    return TestClient(app)


# ─── GET /health ─────────────────────────────────────────────────────────────


class TestHealth:
    def test_health_returns_200(self, http_client: TestClient) -> None:
        response = http_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert "persistence" in data["checks"]
        assert "bsl_ls" in data["checks"]

    def test_health_in_memory_persistence(self, http_client: TestClient) -> None:
        """Default handlers (no DATABASE_URL) → persistence skipped or in-memory."""
        response = http_client.get("/health")
        data = response.json()
        # In-memory fallback → persistence.status == "skipped" или in-memory.
        assert data["checks"]["persistence"]["status"] in ("skipped", "ok")

    def test_health_bsl_ls_skipped_without_env(
        self, http_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BSL_LS_HTTP_URL", raising=False)
        response = http_client.get("/health")
        data = response.json()
        assert data["checks"]["bsl_ls"]["status"] == "skipped"


# ─── GET /servers ────────────────────────────────────────────────────────────


class TestServers:
    def test_list_servers(self, http_client: TestClient) -> None:
        response = http_client.get("/servers")
        assert response.status_code == 200
        data = response.json()
        assert "servers" in data
        assert data["total"] == 6
        server_names = [s["name"] for s in data["servers"]]
        assert "facade" in server_names
        assert "metadata" in server_names
        assert "codebase" in server_names
        assert "kb" in server_names
        assert "bsl_ls" in server_names
        assert "git" in server_names

    def test_servers_have_tools_count(self, http_client: TestClient) -> None:
        response = http_client.get("/servers")
        data = response.json()
        for server in data["servers"]:
            assert "tools_count" in server
            assert server["tools_count"] > 0
        # Facade has 8 tools.
        facade = next(s for s in data["servers"] if s["name"] == "facade")
        assert facade["tools_count"] == 8


# ─── GET /tools/{server_name} ────────────────────────────────────────────────


class TestTools:
    def test_list_facade_tools(self, http_client: TestClient) -> None:
        response = http_client.get("/tools/facade")
        assert response.status_code == 200
        data = response.json()
        assert data["server"] == "facade"
        assert data["count"] == 8
        tool_names = [t["name"] for t in data["tools"]]
        assert "plan" in tool_names
        assert "data_status" in tool_names

    def test_list_metadata_tools(self, http_client: TestClient) -> None:
        response = http_client.get("/tools/metadata")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 4
        tool_names = [t["name"] for t in data["tools"]]
        assert "metadata.get_metadata" in tool_names

    def test_unknown_server_404(self, http_client: TestClient) -> None:
        response = http_client.get("/tools/unknown")
        assert response.status_code == 404
        assert "Unknown server" in response.json()["detail"]


# ─── POST /facade/{tool} ─────────────────────────────────────────────────────


class TestFacadeTools:
    def test_data_status(self, http_client_with_handlers: TestClient) -> None:
        response = http_client_with_handlers.post(
            "/facade/data_status", json={"args": {}}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tool"] == "data_status"
        assert "result" in data
        assert "paths" in data["result"]

    def test_unknown_facade_tool_404(self, http_client: TestClient) -> None:
        response = http_client.post("/facade/unknown_tool", json={"args": {}})
        assert response.status_code == 404
        assert "Unknown facade tool" in response.json()["detail"]

    def test_facade_tool_error_400(
        self, http_client_with_handlers: TestClient
    ) -> None:
        """FacadeNotConfiguredError → 400."""
        from mcp_servers.http_server import create_http_app
        from mcp_servers.facade.handlers import FacadeHandlers

        # Default FacadeHandlers (no DI) — handle_plan поднимет FacadeNotConfiguredError.
        app = create_http_app(FacadeHandlers())
        client = TestClient(app)
        response = client.post(
            "/facade/plan",
            json={
                "args": {
                    "task": "test",
                    "config_name": "ut11",
                    "config_version": "4.5.3",
                    "platform_version": "8.3.20",
                }
            },
        )
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"].lower()


# ─── POST /domain/{server_name}/{tool} ───────────────────────────────────────


class TestDomainTools:
    def test_domain_facade_rejected(self, http_client: TestClient) -> None:
        """POST /domain/facade/foo → 400 (use /facade/{tool})."""
        response = http_client.post("/domain/facade/foo", json={"args": {}})
        assert response.status_code == 400
        assert "Use /facade/" in response.json()["detail"]

    def test_domain_unknown_server_404(self, http_client: TestClient) -> None:
        response = http_client.post(
            "/domain/unknown_server/foo", json={"args": {}}
        )
        assert response.status_code == 404
        assert "Unknown server" in response.json()["detail"]


# ─── Root ────────────────────────────────────────────────────────────────────


class TestRoot:
    def test_root(self, http_client: TestClient) -> None:
        response = http_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "1C AI Assistant"
        assert "endpoints" in data
        assert "GET /health" in data["endpoints"]


# ─── CLI registration ────────────────────────────────────────────────────────


class TestServeCliRegistration:
    """`1c-ai serve` зарегистрирован в CLI."""

    def test_serve_command_exists(self) -> None:
        from agent.cli import main

        assert "serve" in main.commands

    def test_serve_help(self) -> None:
        from click.testing import CliRunner

        from agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "serve" in result.output

    def test_serve_command_help(self) -> None:
        from click.testing import CliRunner

        from agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output
        assert "8000" in result.output  # default port


# ─── cmd_serve unit tests ────────────────────────────────────────────────────


class TestCmdServe:
    """Прямые тесты cmd_serve."""

    def test_serve_starts_http_server(self) -> None:
        """cmd_serve запускает HTTP server (mock run_http_server)."""
        from agent.cli_commands.serve import cmd_serve

        with patch("mcp_servers.http_server.run_http_server") as mock_run:
            import asyncio

            async def _mock_run(host: str, port: int, handlers: object) -> None:
                return None

            mock_run.side_effect = _mock_run
            # Mock create_facade_handlers чтобы не тащить реальный DI.
            with patch("agent.cli_commands.facade_entry.create_facade_handlers") as mock_handlers:
                mock_handlers.return_value = MagicMock()
                exit_code = cmd_serve(host="127.0.0.1", port=9000)
        assert exit_code == 0

    def test_serve_handlers_creation_failure_exit_1(self) -> None:
        """create_facade_handlers упал → exit 1."""
        from agent.cli_commands.serve import cmd_serve

        with patch(
            "agent.cli_commands.facade_entry.create_facade_handlers",
            side_effect=RuntimeError("DI failed"),
        ):
            exit_code = cmd_serve(host="0.0.0.0", port=8000)
        assert exit_code == 1
