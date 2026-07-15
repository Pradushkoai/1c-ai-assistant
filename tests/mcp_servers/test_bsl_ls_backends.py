"""tests/mcp_servers/test_bsl_ls_backends.py — BSL LS backends (TD-S8-02).

Покрытие:
- StubBslLsBackend: 0 diagnostics, format no-op, health False.
- SubprocessBslLsBackend: mock run_bsl_ls, lint/format/health_check.
- HttpBslLsBackend: mock httpx, lint/format/health_check.
- make_bsl_ls_backend: factory по env (auto/subprocess/http/stub).
- runner: parse_lint_output, map_severity.

См. ADR-0010, D-2026-07-13-16.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_servers.bsl_ls.backends import (
    HttpBslLsBackend,
    StubBslLsBackend,
    SubprocessBslLsBackend,
    make_bsl_ls_backend,
)
from mcp_servers.bsl_ls.runner import (
    check_bsl_ls,
    map_severity,
    parse_lint_output,
)
from mcp_servers.bsl_ls.contracts import LintOutput, FormatOutput


# ─── StubBslLsBackend ───────────────────────────────────────────────────────


class TestStubBackend:
    @pytest.mark.asyncio
    async def test_lint_returns_zero_diagnostics(self) -> None:
        backend = StubBslLsBackend(reason="test")
        result = await backend.lint(code="Функция Тест() КонецФункции")
        assert result.total == 0
        assert result.diagnostics == []
        assert result.by_code == {}

    @pytest.mark.asyncio
    async def test_format_returns_code_unchanged(self) -> None:
        backend = StubBslLsBackend(reason="test")
        code = "Функция Тест()\n    Возврат;\nКонецФункции"
        result = await backend.format(code=code)
        assert result.formatted_code == code
        assert result.changes_made is False

    @pytest.mark.asyncio
    async def test_health_check_false(self) -> None:
        backend = StubBslLsBackend(reason="test")
        assert await backend.health_check() is False


# ─── SubprocessBslLsBackend ─────────────────────────────────────────────────


class TestSubprocessBackend:
    @pytest.mark.asyncio
    async def test_lint_with_mocked_runner(self, tmp_path: Path) -> None:
        """SubprocessBslLsBackend.lint делегирует в run_bsl_ls."""
        # Create a fake jar so check_bsl_ls returns True.
        jar = tmp_path / "bsl-ls.jar"
        jar.write_bytes(b"fake jar")
        backend = SubprocessBslLsBackend(jar_path=str(jar))

        # Mock run_bsl_ls to return diagnostics.
        mock_result = {
            "total": 2,
            "by_code": {"BSL-WS-001": 2},
            "diagnostics": [{"code": "BSL-WS-001", "severity": "warning", "line": 1, "column": 1, "message": "test"}],
        }
        with patch("mcp_servers.bsl_ls.backends.run_bsl_ls", return_value=mock_result):
            result = await backend.lint(code="test code", file_path="/tmp/test.bsl")

        assert result.total == 2
        assert result.by_code == {"BSL-WS-001": 2}
        assert len(result.diagnostics) == 1
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_format_with_mocked_runner(self, tmp_path: Path) -> None:
        jar = tmp_path / "bsl-ls.jar"
        jar.write_bytes(b"fake jar")
        backend = SubprocessBslLsBackend(jar_path=str(jar))

        mock_result = {
            "formatted_code": "Formatted code",
            "changes_made": True,
        }
        with patch("mcp_servers.bsl_ls.backends.run_bsl_ls", return_value=mock_result):
            result = await backend.format(code="unformatted")

        assert result.formatted_code == "Formatted code"
        assert result.changes_made is True

    @pytest.mark.asyncio
    async def test_health_check_jar_not_found(self) -> None:
        backend = SubprocessBslLsBackend(jar_path="/nonexistent/jar.jar")
        assert await backend.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_jar_exists(self, tmp_path: Path) -> None:
        jar = tmp_path / "bsl-ls.jar"
        jar.write_bytes(b"fake jar")
        backend = SubprocessBslLsBackend(jar_path=str(jar))

        # Mock get_bsl_ls_version to return a version string.
        with patch("mcp_servers.bsl_ls.backends.get_bsl_ls_version", return_value="0.25.5"):
            assert await backend.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_jar_exists_but_version_fails(self, tmp_path: Path) -> None:
        jar = tmp_path / "bsl-ls.jar"
        jar.write_bytes(b"fake jar")
        backend = SubprocessBslLsBackend(jar_path=str(jar))

        with patch("mcp_servers.bsl_ls.backends.get_bsl_ls_version", return_value=None):
            assert await backend.health_check() is False


# ─── HttpBslLsBackend ───────────────────────────────────────────────────────


class TestHttpBackend:
    @pytest.mark.asyncio
    async def test_lint_with_mock_httpx(self) -> None:
        backend = HttpBslLsBackend(base_url="http://mock:8080")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total": 1,
            "by_code": {"BSL-WS-001": 1},
            "diagnostics": [{"code": "BSL-WS-001", "severity": "warning", "line": 1, "column": 1, "message": "test"}],
            "latency_ms": 42,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("mcp_servers.bsl_ls.backends.httpx.AsyncClient", return_value=mock_client):
            result = await backend.lint(code="test")

        assert result.total == 1
        assert result.latency_ms == 42

    @pytest.mark.asyncio
    async def test_format_with_mock_httpx(self) -> None:
        backend = HttpBslLsBackend(base_url="http://mock:8080")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "formatted_code": "formatted",
            "changes_made": True,
            "latency_ms": 10,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("mcp_servers.bsl_ls.backends.httpx.AsyncClient", return_value=mock_client):
            result = await backend.format(code="unformatted")

        assert result.formatted_code == "formatted"
        assert result.changes_made is True

    @pytest.mark.asyncio
    async def test_health_check_ok(self) -> None:
        backend = HttpBslLsBackend(base_url="http://mock:8080")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"bsl_ls_available": True}

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_servers.bsl_ls.backends.httpx.AsyncClient", return_value=mock_client):
            assert await backend.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_failed(self) -> None:
        backend = HttpBslLsBackend(base_url="http://mock:8080")
        with patch("mcp_servers.bsl_ls.backends.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(side_effect=ConnectionError("refused"))
            mock_client_cls.return_value = mock_client
            assert await backend.health_check() is False


# ─── make_bsl_ls_backend (factory) ──────────────────────────────────────────


class TestMakeBackend:
    def test_stub_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("1C_AI_BSL_LS_MODE", "stub")
        backend = make_bsl_ls_backend()
        assert isinstance(backend, StubBslLsBackend)

    def test_http_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("1C_AI_BSL_LS_MODE", "http")
        monkeypatch.setenv("BSL_LS_HTTP_URL", "http://test:8080")
        backend = make_bsl_ls_backend()
        assert isinstance(backend, HttpBslLsBackend)
        assert backend.base_url == "http://test:8080"

    def test_subprocess_mode_jar_exists(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        jar = tmp_path / "bsl-ls.jar"
        jar.write_bytes(b"fake")
        monkeypatch.setenv("1C_AI_BSL_LS_MODE", "subprocess")
        monkeypatch.setenv("BSL_LS_JAR", str(jar))
        backend = make_bsl_ls_backend()
        assert isinstance(backend, SubprocessBslLsBackend)
        assert backend.jar_path == str(jar)

    def test_subprocess_mode_jar_missing_falls_back_to_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("1C_AI_BSL_LS_MODE", "subprocess")
        monkeypatch.setenv("BSL_LS_JAR", "/nonexistent/jar.jar")
        backend = make_bsl_ls_backend()
        assert isinstance(backend, StubBslLsBackend)

    def test_auto_mode_jar_exists(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        jar = tmp_path / "bsl-ls.jar"
        jar.write_bytes(b"fake")
        monkeypatch.setenv("1C_AI_BSL_LS_MODE", "auto")
        monkeypatch.setenv("BSL_LS_JAR", str(jar))
        monkeypatch.delenv("BSL_LS_HTTP_URL", raising=False)
        backend = make_bsl_ls_backend()
        assert isinstance(backend, SubprocessBslLsBackend)

    def test_auto_mode_no_jar_http_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("1C_AI_BSL_LS_MODE", "auto")
        monkeypatch.setenv("BSL_LS_JAR", "/nonexistent/jar.jar")
        monkeypatch.setenv("BSL_LS_HTTP_URL", "http://docker:8080")
        backend = make_bsl_ls_backend()
        assert isinstance(backend, HttpBslLsBackend)

    def test_auto_mode_no_jar_no_http_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("1C_AI_BSL_LS_MODE", "auto")
        monkeypatch.setenv("BSL_LS_JAR", "/nonexistent/jar.jar")
        monkeypatch.delenv("BSL_LS_HTTP_URL", raising=False)
        backend = make_bsl_ls_backend()
        assert isinstance(backend, StubBslLsBackend)

    def test_unknown_mode_falls_back_to_auto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("1C_AI_BSL_LS_MODE", "unknown_mode")
        monkeypatch.setenv("BSL_LS_JAR", "/nonexistent/jar.jar")
        monkeypatch.delenv("BSL_LS_HTTP_URL", raising=False)
        backend = make_bsl_ls_backend()
        assert isinstance(backend, StubBslLsBackend)


# ─── runner: parse_lint_output + map_severity ────────────────────────────────


class TestRunner:
    def test_parse_lint_output_empty(self) -> None:
        result = parse_lint_output(None, "/tmp/test.bsl")
        assert result["total"] == 0
        assert result["diagnostics"] == []

    def test_parse_lint_output_file_not_found(self) -> None:
        result = parse_lint_output("/nonexistent/file.json", "/tmp/test.bsl")
        assert result["total"] == 0

    def test_parse_lint_output_valid_json(self, tmp_path: Path) -> None:
        issues = [
            {
                "code": "BSL-WS-001",
                "severity": "Error",
                "range": {"start": {"line": 5, "character": 10}},
                "message": "Test error",
                "source": "test.bsl",
            },
            {
                "code": "BSL-WS-002",
                "severity": "Warning",
                "range": {"start": {"line": 0, "character": 0}},
                "message": "Test warning",
                "source": "test.bsl",
            },
        ]
        output_file = tmp_path / "result.json"
        output_file.write_text(json.dumps(issues), encoding="utf-8")

        result = parse_lint_output(str(output_file), "test.bsl")
        assert result["total"] == 2
        assert result["by_code"] == {"BSL-WS-001": 1, "BSL-WS-002": 1}
        # Line is 0-based → 1-based.
        assert result["diagnostics"][0]["line"] == 6
        assert result["diagnostics"][0]["column"] == 11
        assert result["diagnostics"][0]["severity"] == "critical"
        assert result["diagnostics"][1]["severity"] == "warning"

    def test_map_severity_string(self) -> None:
        assert map_severity("Error") == "critical"
        assert map_severity("Warning") == "warning"
        assert map_severity("Info") == "info"
        assert map_severity("Hint") == "info"

    def test_map_severity_int(self) -> None:
        assert map_severity(1) == "critical"
        assert map_severity(2) == "warning"
        assert map_severity(3) == "info"
        assert map_severity(4) == "info"

    def test_check_bsl_ls_exists(self, tmp_path: Path) -> None:
        jar = tmp_path / "test.jar"
        jar.write_bytes(b"fake")
        assert check_bsl_ls(str(jar)) is True

    def test_check_bsl_ls_not_exists(self) -> None:
        assert check_bsl_ls("/nonexistent/jar.jar") is False


# ─── CLI registration ───────────────────────────────────────────────────────


class TestBslLsCliRegistration:
    def test_bsl_ls_group_exists(self) -> None:
        from agent.cli import main

        assert "bsl-ls" in main.commands

    def test_download_subcommand_exists(self) -> None:
        from agent.cli import main

        bsl_ls_group = main.commands["bsl-ls"]
        assert "download" in bsl_ls_group.commands

    def test_status_subcommand_exists(self) -> None:
        from agent.cli import main

        bsl_ls_group = main.commands["bsl-ls"]
        assert "status" in bsl_ls_group.commands

    def test_main_help_shows_bsl_ls(self) -> None:
        from click.testing import CliRunner

        from agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "bsl-ls" in result.output

    def test_bsl_ls_status_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`1c-ai bsl-ls status` выполняется (stub mode)."""
        from click.testing import CliRunner

        from agent.cli import main

        monkeypatch.setenv("1C_AI_BSL_LS_MODE", "stub")
        runner = CliRunner()
        result = runner.invoke(main, ["bsl-ls", "status"])
        assert result.exit_code == 1  # stub → not ready → exit 1
        assert "BSL Language Server" in result.output
        assert "Mode:" in result.output
        assert "Backend:" in result.output
