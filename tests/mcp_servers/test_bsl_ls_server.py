"""Тесты для mcp_servers.bsl_ls.server — BslLsServer (mocked HTTP)."""

from __future__ import annotations

import json

import httpx
import pytest

from mcp_servers.bsl_ls.contracts import FormatOutput, LintOutput
from mcp_servers.bsl_ls.server import (
    BslLsServer,
    FormatImplementation,
    LintImplementation,
)


def _make_mock_transport(
    lint_response: dict | None = None,
    format_response: dict | None = None,
    health_response: dict | None = None,
    lint_status: int = 200,
    format_status: int = 200,
) -> httpx.MockTransport:
    """Создать MockTransport с предопределёнными ответами."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lint":
            if lint_status != 200:
                return httpx.Response(lint_status, text="Error")
            return httpx.Response(200, json=lint_response or {"total": 0, "by_code": {}, "diagnostics": []})
        if request.url.path == "/format":
            if format_status != 200:
                return httpx.Response(format_status, text="Error")
            return httpx.Response(200, json=format_response or {"formatted_code": "", "changes_made": False})
        if request.url.path == "/health":
            return httpx.Response(200, json=health_response or {"status": "ok", "bsl_ls_available": True})
        return httpx.Response(404, text="Not found")

    return httpx.MockTransport(handler)


def _patch_client(transport: httpx.MockTransport):
    """Патчит httpx.AsyncClient чтобы использовать MockTransport."""
    import contextlib

    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        original_init(self, *args, **kwargs)

    httpx.AsyncClient.__init__ = patched_init

    def restore():
        httpx.AsyncClient.__init__ = original_init

    return restore


# ─── BslLsServer creation ──────────────────────────────────────────────────


class TestBslLsServerCreation:
    @pytest.mark.smoke
    def test_create_default(self):
        server = BslLsServer()
        assert "8080" in server.base_url
        assert server.timeout == 60

    def test_create_custom(self):
        server = BslLsServer(base_url="http://localhost:9000", timeout=30)
        assert server.base_url == "http://localhost:9000"
        assert server.timeout == 30

    def test_create_from_env(self, monkeypatch):
        monkeypatch.setenv("BSL_LS_HTTP_URL", "http://custom:8080")
        monkeypatch.setenv("BSL_LS_TIMEOUT", "120")
        server = BslLsServer()
        assert server.base_url == "http://custom:8080"
        assert server.timeout == 120


# ─── lint() ─────────────────────────────────────────────────────────────────


class TestLint:
    @pytest.mark.asyncio
    @pytest.mark.smoke
    async def test_lint_returns_output(self):
        lint_data = {
            "total": 2,
            "by_code": {"BSL-WS-001": 1, "BSL-NAMESPACE-001": 1},
            "diagnostics": [
                {"code": "BSL-WS-001", "severity": "critical", "line": 5, "column": 1, "message": "Test"},
                {"code": "BSL-NAMESPACE-001", "severity": "warning", "line": 10, "column": 1, "message": "NS"},
            ],
        }
        transport = _make_mock_transport(lint_response=lint_data)
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            result = await server.lint(code="Процедура Т() КонецПроцедуры")
        finally:
            restore()

        assert isinstance(result, LintOutput)
        assert result.total == 2
        assert len(result.diagnostics) == 2
        assert result.diagnostics[0]["code"] == "BSL-WS-001"

    @pytest.mark.asyncio
    async def test_lint_no_diagnostics(self):
        transport = _make_mock_transport(lint_response={"total": 0, "by_code": {}, "diagnostics": []})
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            result = await server.lint(code="// clean")
        finally:
            restore()

        assert result.total == 0
        assert result.diagnostics == []

    @pytest.mark.asyncio
    async def test_lint_http_error_raises(self):
        transport = _make_mock_transport(lint_status=500)
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            with pytest.raises(httpx.HTTPStatusError):
                await server.lint(code="x")
        finally:
            restore()


# ─── format() ───────────────────────────────────────────────────────────────


class TestFormat:
    @pytest.mark.asyncio
    @pytest.mark.smoke
    async def test_format_returns_output(self):
        format_data = {"formatted_code": "Процедура Т()\nКонецПроцедуры", "changes_made": True}
        transport = _make_mock_transport(format_response=format_data)
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            result = await server.format(code="Процедура Т() КонецПроцедуры")
        finally:
            restore()

        assert isinstance(result, FormatOutput)
        assert result.changes_made is True

    @pytest.mark.asyncio
    async def test_format_no_changes(self):
        format_data = {"formatted_code": "Процедура Т()\nКонецПроцедуры", "changes_made": False}
        transport = _make_mock_transport(format_response=format_data)
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            result = await server.format(code="Процедура Т()\nКонецПроцедуры")
        finally:
            restore()

        assert result.changes_made is False


# ─── health_check() ─────────────────────────────────────────────────────────


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy(self):
        transport = _make_mock_transport(health_response={"status": "ok", "bsl_ls_available": True})
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            result = await server.health_check()
        finally:
            restore()
        assert result is True

    @pytest.mark.asyncio
    async def test_unavailable(self):
        transport = _make_mock_transport(health_response={"status": "degraded", "bsl_ls_available": False})
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            result = await server.health_check()
        finally:
            restore()
        assert result is False


# ─── LintImplementation / FormatImplementation ──────────────────────────────


class TestLintImplementation:
    @pytest.mark.asyncio
    async def test_call_returns_dict(self):
        lint_data = {
            "total": 1,
            "by_code": {"BSL-WS-001": 1},
            "diagnostics": [{"code": "BSL-WS-001", "severity": "critical", "line": 1, "column": 1, "message": "test"}],
        }
        transport = _make_mock_transport(lint_response=lint_data)
        restore = _patch_client(transport)
        try:
            impl = LintImplementation(BslLsServer(base_url="http://mock:8080", timeout=5))
            result = await impl(code="Процедура Т() КонецПроцедуры")
        finally:
            restore()

        assert isinstance(result, dict)
        assert result["total"] == 1
        assert result["by_code"]["BSL-WS-001"] == 1


class TestFormatImplementation:
    @pytest.mark.asyncio
    async def test_call_returns_dict(self):
        format_data = {"formatted_code": "Процедура Т()\nКонецПроцедуры", "changes_made": True}
        transport = _make_mock_transport(format_response=format_data)
        restore = _patch_client(transport)
        try:
            impl = FormatImplementation(BslLsServer(base_url="http://mock:8080", timeout=5))
            result = await impl(code="Процедура Т() КонецПроцедуры")
        finally:
            restore()

        assert isinstance(result, dict)
        assert result["changes_made"] is True
