"""BslLsServer — HTTP клиент к 1c-ai-bsl-ls контейнеру.

Реализует Lint и Format tools через HTTP API:
  POST http://1c-ai-bsl-ls:8080/lint
  POST http://1c-ai-bsl-ls:8080/format

См. ADR-0010 (MCP tool contracts) и ADR-0015 (3-container deployment).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .contracts import FormatInput, FormatOutput, LintInput, LintOutput

log = logging.getLogger(__name__)

DEFAULT_BSL_LS_URL = "http://1c-ai-bsl-ls:8080"


class BslLsServer:
    """HTTP клиент к BSL LS контейнеру.

    Attributes:
        base_url: URL BSL LS HTTP сервера (по умолчанию из env BSL_LS_HTTP_URL).
        timeout: timeout для HTTP запросов (секунды).
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = base_url or os.environ.get("BSL_LS_HTTP_URL", DEFAULT_BSL_LS_URL)
        self.timeout = timeout or int(os.environ.get("BSL_LS_TIMEOUT", "60"))

    async def lint(
        self,
        code: str,
        file_path: str = "/tmp/module.bsl",
        rules: list[str] | None = None,
        baseline_path: str | None = None,
    ) -> LintOutput:
        """Запустить BSL LS анализ кода.

        Args:
            code: BSL-код для анализа.
            file_path: виртуальный путь файла (для диагностик).
            rules: subset правил. None = все 187 диагностик.
            baseline_path: путь к baseline.json.

        Returns:
            LintOutput с total, by_code, diagnostics.

        Raises:
            httpx.HTTPError: при ошибке HTTP.
            RuntimeError: при timeout.
        """
        request_data: dict[str, Any] = {
            "code": code,
            "file_path": file_path,
        }
        if rules is not None:
            request_data["rules"] = rules
        if baseline_path is not None:
            request_data["baseline_path"] = baseline_path

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/lint",
                json=request_data,
            )
            response.raise_for_status()
            data = response.json()

        return LintOutput(
            total=data.get("total", 0),
            by_code=data.get("by_code", {}),
            diagnostics=data.get("diagnostics", []),
            latency_ms=data.get("latency_ms", 0),
        )

    async def format(
        self,
        code: str,
        style: str = "1c",
    ) -> FormatOutput:
        """Форматировать BSL-код.

        Args:
            code: BSL-код.
            style: стиль форматирования ('1c' или 'bsp').

        Returns:
            FormatOutput с formatted_code и changes_made.

        Raises:
            httpx.HTTPError: при ошибке HTTP.
        """
        request_data = {
            "code": code,
            "style": style,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/format",
                json=request_data,
            )
            response.raise_for_status()
            data = response.json()

        return FormatOutput(
            formatted_code=data.get("formatted_code", code),
            changes_made=data.get("changes_made", False),
            latency_ms=data.get("latency_ms", 0),
        )

    async def health_check(self) -> bool:
        """Проверить доступность BSL LS сервера.

        Returns:
            True если сервер отвечает и BSL LS jar доступна.
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    data = response.json()
                    return bool(data.get("bsl_ls_available", False))
        except Exception as exc:
            log.warning("BSL LS health check failed: %s", exc)
        return False


# ─── Tool implementations (для MCP server) ─────────────────────────────────


class LintImplementation:
    """Реализация bsl_ls.lint tool — обёртка над BslLsServer.lint()."""

    def __init__(self, server: BslLsServer | None = None) -> None:
        self._server = server or BslLsServer()

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        """Выполнить lint.

        Args (из LintInput):
            code: BSL-код.
            file_path: виртуальный путь файла.
            rules: subset правил.
            baseline_path: путь к baseline.json.

        Returns:
            dict (соответствует LintOutput).
        """
        input_data = LintInput.model_validate(kwargs)
        result = await self._server.lint(
            code=input_data.code,
            file_path=input_data.file_path,
            rules=input_data.rules,
            baseline_path=input_data.baseline_path,
        )
        return result.model_dump()


class FormatImplementation:
    """Реализация bsl_ls.format tool — обёртка над BslLsServer.format()."""

    def __init__(self, server: BslLsServer | None = None) -> None:
        self._server = server or BslLsServer()

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        """Выполнить format.

        Args (из FormatInput):
            code: BSL-код.
            style: стиль ('1c' или 'bsp').

        Returns:
            dict (соответствует FormatOutput).
        """
        input_data = FormatInput.model_validate(kwargs)
        result = await self._server.format(
            code=input_data.code,
            style=input_data.style,
        )
        return result.model_dump()
