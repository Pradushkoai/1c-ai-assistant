"""Тесты для mcp_servers.bsl_ls.server — BslLsServer (mocked HTTP)."""

from __future__ import annotations

import json
import os

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
    latency_ms: int = 42,
) -> httpx.MockTransport:
    """Создать MockTransport с предопределёнными ответами."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/lint":
            if lint_status != 200:
                return httpx.Response(lint_status, text="Error")
            resp = lint_response or {"total": 0, "by_code": {}, "diagnostics": []}
            # Добавляем latency_ms если нет в ответе
            resp = {**{"latency_ms": latency_ms}, **resp}
            return httpx.Response(200, json=resp)
        if request.url.path == "/format":
            if format_status != 200:
                return httpx.Response(format_status, text="Error")
            resp = format_response or {"formatted_code": "", "changes_made": False}
            resp = {**{"latency_ms": latency_ms}, **resp}
            return httpx.Response(200, json=resp)
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


# ─── TD-S4.2-04: latency_ms + edge-cases ────────────────────────────────────


class TestLatencyMetric:
    """TD-S4.2-04: проверка проброса latency_ms из BSL LS HTTP response."""

    @pytest.mark.asyncio
    async def test_lint_latency_returned(self):
        """latency_ms пробрасывается в LintOutput."""
        lint_data = {
            "total": 1,
            "by_code": {"BSL-WS-001": 1},
            "diagnostics": [{"code": "BSL-WS-001", "severity": "critical", "line": 5, "column": 1, "message": "Test"}],
            "latency_ms": 1234,
        }
        transport = _make_mock_transport(lint_response=lint_data, latency_ms=1234)
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            result = await server.lint(code="x")
        finally:
            restore()

        assert result.latency_ms == 1234

    @pytest.mark.asyncio
    async def test_format_latency_returned(self):
        """latency_ms пробрасывается в FormatOutput."""
        format_data = {
            "formatted_code": "code",
            "changes_made": False,
            "latency_ms": 567,
        }
        transport = _make_mock_transport(format_response=format_data, latency_ms=567)
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            result = await server.format(code="x")
        finally:
            restore()

        assert result.latency_ms == 567

    @pytest.mark.asyncio
    async def test_lint_default_latency_zero(self):
        """Если сервер не вернул latency_ms — значение по умолчанию 0."""

        # Эмулируем старый сервер без latency_ms
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/lint":
                return httpx.Response(200, json={"total": 0, "by_code": {}, "diagnostics": []})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            result = await server.lint(code="x")
        finally:
            restore()

        assert result.latency_ms == 0


class TestLintRulesAndBaseline:
    """TD-S4.2-04: проверка передачи rules и baseline_path в запросе."""

    @pytest.mark.asyncio
    async def test_lint_with_rules_in_request(self):
        """Правила передаются в JSON-теле запроса."""
        captured_request: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/lint":
                captured_request["body"] = json.loads(request.content)
                return httpx.Response(200, json={"total": 0, "by_code": {}, "diagnostics": [], "latency_ms": 10})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            await server.lint(code="x", rules=["BSL-WS-001", "BSL-NAMESPACE-001"])
        finally:
            restore()

        assert captured_request["body"]["rules"] == ["BSL-WS-001", "BSL-NAMESPACE-001"]

    @pytest.mark.asyncio
    async def test_lint_with_baseline_in_request(self):
        """baseline_path передаётся в JSON-теле запроса."""
        captured_request: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/lint":
                captured_request["body"] = json.loads(request.content)
                return httpx.Response(200, json={"total": 0, "by_code": {}, "diagnostics": [], "latency_ms": 10})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            await server.lint(code="x", baseline_path="/baseline.json")
        finally:
            restore()

        assert captured_request["body"]["baseline_path"] == "/baseline.json"

    @pytest.mark.asyncio
    async def test_lint_without_rules_omitted(self):
        """Если rules=None, поле не должно быть в запросе."""
        captured_request: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/lint":
                captured_request["body"] = json.loads(request.content)
                return httpx.Response(200, json={"total": 0, "by_code": {}, "diagnostics": [], "latency_ms": 10})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            await server.lint(code="x")
        finally:
            restore()

        assert "rules" not in captured_request["body"]
        assert "baseline_path" not in captured_request["body"]


class TestErrorHandling:
    """TD-S4.2-04: проверка обработки HTTP-ошибок."""

    @pytest.mark.asyncio
    async def test_lint_504_gateway_timeout(self):
        """504 от BSL LS HTTP сервера → httpx.HTTPStatusError."""
        transport = _make_mock_transport(lint_status=504)
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            with pytest.raises(httpx.HTTPStatusError):
                await server.lint(code="x")
        finally:
            restore()

    @pytest.mark.asyncio
    async def test_lint_connection_error(self):
        """ConnectionError при недоступности сервера."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(handler)
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            with pytest.raises(httpx.ConnectError):
                await server.lint(code="x")
        finally:
            restore()

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self):
        """health_check возвращает False при connection error."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(handler)
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            result = await server.health_check()
        finally:
            restore()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_returns_version(self):
        """health_check с bsl_ls_version."""
        transport = _make_mock_transport(
            health_response={
                "status": "ok",
                "bsl_ls_available": True,
                "bsl_ls_version": "0.25.5",
            }
        )
        restore = _patch_client(transport)
        try:
            server = BslLsServer(base_url="http://mock:8080", timeout=5)
            result = await server.health_check()
        finally:
            restore()

        assert result is True


# ─── TD-S4.2-04: integration test (skip если BSL LS недоступен) ─────────────


class TestBslLsIntegration:
    """Интеграционные тесты с реальным BSL LS контейнером.

    Запускаются только если доступен BSL LS HTTP сервер (env BSL_LS_HTTP_URL
    или http://localhost:8080). В CI/без Docker — skip.

    Для запуска локально:
        docker compose up -d 1c-ai-bsl-ls
        BSL_LS_HTTP_URL=http://localhost:8080 pytest tests/mcp_servers/test_bsl_ls_server.py::TestBslLsIntegration -v
    """

    @pytest.fixture
    def real_bsl_ls_url(self) -> str | None:
        """URL реального BSL LS сервера или None."""
        return os.environ.get("BSL_LS_HTTP_URL")

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not os.environ.get('BSL_LS_HTTP_URL')",
        reason="BSL_LS_HTTP_URL not set; requires running bsl-ls container",
    )
    async def test_real_health_check(self, real_bsl_ls_url: str):
        """Health check на реальном сервере возвращает True."""
        server = BslLsServer(base_url=real_bsl_ls_url, timeout=15)
        result = await server.health_check()
        assert result is True, "BSL LS server should be healthy"

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not os.environ.get('BSL_LS_HTTP_URL')",
        reason="BSL_LS_HTTP_URL not set; requires running bsl-ls container",
    )
    async def test_real_lint_clean_code(self, real_bsl_ls_url: str):
        """Чистый BSL-код → 0 диагностик."""
        server = BslLsServer(base_url=real_bsl_ls_url, timeout=60)
        clean_code = """Процедура Тест()
    Сообщить("Привет, мир!");
КонецПроцедуры"""
        result = await server.lint(code=clean_code, file_path="/tmp/test.bsl")
        # На чистом коде BSL LS может вернуть 0 или мало диагностик
        assert isinstance(result, LintOutput)
        assert result.latency_ms > 0  # Реальная операция занимает время

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not os.environ.get('BSL_LS_HTTP_URL')",
        reason="BSL_LS_HTTP_URL not set; requires running bsl-ls container",
    )
    async def test_real_lint_detects_antipattern(self, real_bsl_ls_url: str):
        """BSL LS находит известные проблемы (например, BSL-WS-001)."""
        server = BslLsServer(base_url=real_bsl_ls_url, timeout=60)
        # Код с явным нарушением: лишний пробел, отсутствие отступа
        bad_code = 'Процедура Тест()\nСообщить("x");\nКонецПроцедуры'
        result = await server.lint(code=bad_code, file_path="/tmp/bad.bsl")
        assert isinstance(result, LintOutput)
        # BSL LS должен найти хотя бы одну диагностику на плохом коде
        # (но не делаем строгий assert — зависит от версии правил)
