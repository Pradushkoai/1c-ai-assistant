"""bsl_ls.backends — 3 стратегии вызова BSL LS (TD-S8-02).

Strategy pattern: BslLsServer делегирует lint/format/health_check в backend.

3 режима (env ``1C_AI_BSL_LS_MODE=auto|subprocess|http|stub``):
- **SubprocessBslLsBackend** — прямой ``java -jar`` subprocess (без HTTP, без Docker).
- **HttpBslLsBackend** — HTTP к Docker/standalone server (текущий behavior, production).
- **StubBslLsBackend** — заглушка (нет Java/jar — warning, 0 diagnostics).

``make_bsl_ls_backend()`` factory по env выбирает backend.

См. ADR-0010, ADR-0015, D-2026-07-13-16.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Protocol, runtime_checkable

import httpx

from .contracts import FormatOutput, LintOutput
from .runner import (
    DEFAULT_JAR_PATH,
    DEFAULT_JAVA_OPTS,
    DEFAULT_TIMEOUT,
    check_bsl_ls,
    get_bsl_ls_version,
    run_bsl_ls,
)

log = logging.getLogger(__name__)


@runtime_checkable
class BslLsBackend(Protocol):
    """Protocol для BSL LS backend стратегий."""

    async def lint(
        self,
        code: str,
        file_path: str = "/tmp/module.bsl",
        rules: list[str] | None = None,
        baseline_path: str | None = None,
    ) -> LintOutput:
        """Запустить BSL LS анализ кода."""
        ...

    async def format(self, code: str, style: str = "1c") -> FormatOutput:
        """Форматировать BSL-код."""
        ...

    async def health_check(self) -> bool:
        """Проверить доступность backend."""
        ...


# ─── SubprocessBslLsBackend (без Docker, прямой java -jar) ──────────────────


class SubprocessBslLsBackend:
    """Прямой ``java -jar`` subprocess — без HTTP, без Docker.

    Для solo-use (я как LLM через CLI). Нужна Java + jar
    (``1c-ai bsl-ls download``).

    Attributes:
        jar_path: путь к bsl-language-server.jar.
        java_opts: JVM options (например, ``-Xmx512m``).
        timeout: timeout в секундах.
    """

    def __init__(
        self,
        jar_path: str | None = None,
        java_opts: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.jar_path = jar_path or os.environ.get("BSL_LS_JAR", DEFAULT_JAR_PATH)
        self.java_opts = java_opts or os.environ.get("JAVA_OPTS", DEFAULT_JAVA_OPTS)
        self.timeout = timeout or int(os.environ.get("BSL_LS_TIMEOUT", str(DEFAULT_TIMEOUT)))

    async def lint(
        self,
        code: str,
        file_path: str = "/tmp/module.bsl",
        rules: list[str] | None = None,
        baseline_path: str | None = None,
    ) -> LintOutput:
        """Запустить BSL LS analyze через subprocess."""
        start_ms = time.monotonic_ns() // 1_000_000

        result = run_bsl_ls(
            code=code,
            file_path=file_path,
            mode="analyze",
            baseline_path=baseline_path,
            jar_path=self.jar_path,
            java_opts=self.java_opts,
            timeout=self.timeout,
        )

        elapsed_ms = int(time.monotonic_ns() // 1_000_000 - start_ms)

        return LintOutput(
            total=result.get("total", 0),
            by_code=result.get("by_code", {}),
            diagnostics=result.get("diagnostics", []),
            latency_ms=elapsed_ms,
        )

    async def format(self, code: str, style: str = "1c") -> FormatOutput:
        """Форматировать BSL-код через subprocess."""
        start_ms = time.monotonic_ns() // 1_000_000

        result = run_bsl_ls(
            code=code,
            file_path="/tmp/format.bsl",
            mode="format",
            jar_path=self.jar_path,
            java_opts=self.java_opts,
            timeout=self.timeout,
        )

        elapsed_ms = int(time.monotonic_ns() // 1_000_000 - start_ms)

        return FormatOutput(
            formatted_code=result.get("formatted_code", code),
            changes_made=result.get("changes_made", False),
            latency_ms=elapsed_ms,
        )

    async def health_check(self) -> bool:
        """Проверить: jar существует + java -jar --version работает."""
        if not check_bsl_ls(self.jar_path):
            return False
        version = get_bsl_ls_version(self.jar_path)
        return version is not None


# ─── HttpBslLsBackend (Docker / standalone HTTP server) ─────────────────────


class HttpBslLsBackend:
    """HTTP клиент к BSL LS серверу (Docker или standalone).

    Для production deployment (Docker container с BSL LS HTTP API).
    Текущий behavior — перенесён из ``BslLsServer`` (TD-S4.2-04).

    Attributes:
        base_url: URL BSL LS HTTP сервера.
        timeout: timeout для HTTP запросов (секунды).
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = base_url or os.environ.get("BSL_LS_HTTP_URL", "http://1c-ai-bsl-ls:8080")
        self.timeout = timeout or int(os.environ.get("BSL_LS_TIMEOUT", "60"))

    async def lint(
        self,
        code: str,
        file_path: str = "/tmp/module.bsl",
        rules: list[str] | None = None,
        baseline_path: str | None = None,
    ) -> LintOutput:
        """Запустить BSL LS анализ через HTTP."""
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

    async def format(self, code: str, style: str = "1c") -> FormatOutput:
        """Форматировать BSL-код через HTTP."""
        request_data = {"code": code, "style": style}

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
        """Проверить HTTP /health endpoint."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    data = response.json()
                    return bool(data.get("bsl_ls_available", False))
        except Exception as exc:
            log.warning("BSL LS HTTP health check failed: %s", exc)
        return False


# ─── StubBslLsBackend (no Java / CI / tests) ────────────────────────────────


class StubBslLsBackend:
    """Заглушка BSL LS — для CI/tests без Java.

    lint возвращает 0 diagnostics с warning в log.
    format возвращает код без изменений.
    health_check возвращает False.
    """

    def __init__(self, reason: str = "no Java/jar available") -> None:
        self.reason = reason
        log.warning("bsl_ls_stub_active reason=%s", reason)

    async def lint(
        self,
        code: str,
        file_path: str = "/tmp/module.bsl",
        rules: list[str] | None = None,
        baseline_path: str | None = None,
    ) -> LintOutput:
        """Возвращает 0 diagnostics (lint пропускается)."""
        return LintOutput(
            total=0,
            by_code={},
            diagnostics=[],
            latency_ms=0,
        )

    async def format(self, code: str, style: str = "1c") -> FormatOutput:
        """Возвращает код без изменений."""
        return FormatOutput(
            formatted_code=code,
            changes_made=False,
            latency_ms=0,
        )

    async def health_check(self) -> bool:
        """Всегда False — stub не может анализировать код."""
        return False


# ─── Factory ────────────────────────────────────────────────────────────────


def make_bsl_ls_backend(mode: str | None = None) -> BslLsBackend:
    """Создать BSL LS backend по env ``1C_AI_BSL_LS_MODE``.

    Args:
        mode: ``auto|subprocess|http|stub``. Если None — читается из env
            ``1C_AI_BSL_LS_MODE`` (default: ``auto``).

    Returns:
        BslLsBackend instance.

    Mode selection:
        - ``auto`` (default): subprocess если jar есть, fallback на HTTP если
          ``BSL_LS_HTTP_URL`` задан, fallback на stub.
        - ``subprocess``: принудительно SubprocessBslLsBackend.
        - ``http``: принудительно HttpBslLsBackend.
        - ``stub``: принудительно StubBslLsBackend.
    """
    if mode is None:
        mode = os.environ.get("1C_AI_BSL_LS_MODE", "auto")

    if mode == "stub":
        return StubBslLsBackend(reason="forced stub mode (1C_AI_BSL_LS_MODE=stub)")

    if mode == "http":
        return HttpBslLsBackend()

    if mode == "subprocess":
        jar_path = os.environ.get("BSL_LS_JAR", DEFAULT_JAR_PATH)
        if not check_bsl_ls(jar_path):
            log.warning(
                "bsl_ls_subprocess_mode_but_jar_missing path=%s — falling back to stub",
                jar_path,
            )
            return StubBslLsBackend(reason=f"jar not found: {jar_path}")
        return SubprocessBslLsBackend(jar_path=jar_path)

    # auto (default)
    if mode == "auto":
        # 1. Try subprocess (jar exists?).
        jar_path = os.environ.get("BSL_LS_JAR", DEFAULT_JAR_PATH)
        if check_bsl_ls(jar_path):
            log.info("bsl_ls_auto_mode: subprocess (jar=%s)", jar_path)
            return SubprocessBslLsBackend(jar_path=jar_path)

        # 2. Try HTTP (BSL_LS_HTTP_URL set?).
        http_url = os.environ.get("BSL_LS_HTTP_URL")
        if http_url:
            log.info("bsl_ls_auto_mode: http (url=%s)", http_url)
            return HttpBslLsBackend(base_url=http_url)

        # 3. Fallback to stub.
        log.warning("bsl_ls_auto_mode: stub (no jar at %s, no BSL_LS_HTTP_URL)", jar_path)
        return StubBslLsBackend(reason="auto mode: no jar, no HTTP URL")

    # Unknown mode — fallback to auto behavior.
    log.warning("bsl_ls_unknown_mode=%s — falling back to auto", mode)
    return make_bsl_ls_backend("auto")
