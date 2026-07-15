"""docker/bsl_ls_http_server.py — HTTP сервер для BSL Language Server.

Оборачивает bsl-language-server.jar (Java 17) в HTTP API:
  POST /lint   — анализ BSL-кода (187 диагностик)
  POST /format — форматирование BSL-кода
  GET  /health — health check

BSL LS запускается как subprocess для каждого запроса (stateless).
Результат парсится из JSON файла (--output) или stdout.

CLI-синтаксис BSL LS v0.25.x (см. https://github.com/1c-syntax/bsl-language-reader):
  analyze --src <file-or-dir> --format json --output <result.json>
  format  --src <file-or-dir>  (in-place, модифицирует файлы)

TD-S4.2-04: исправлен CLI-синтаксис (раньше был некорректный `analyze <file>`),
добавлен --output для детерминированного парсинга JSON, добавлены метрики latency.

См. ADR-0015 (3-container deployment) и ADR-0010 (MCP tool contracts).
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Any

from fastapi import FastAPI, HTTPException

# DRY: runner functions shared with SubprocessBslLsBackend (TD-S8-02).
from mcp_servers.bsl_ls.runner import (
    check_bsl_ls as _check_bsl_ls_impl,
)
from mcp_servers.bsl_ls.runner import (
    get_bsl_ls_version as _get_bsl_ls_version_impl,
)
from mcp_servers.bsl_ls.runner import (
    run_bsl_ls as _run_bsl_ls_impl,
)
from pydantic import BaseModel, Field

# ─── Логирование ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}',
)
log = logging.getLogger(__name__)

app = FastAPI(title="BSL LS HTTP Server", version="0.2.0")

BSL_LS_JAR = os.environ.get("BSL_LS_JAR", "/opt/bsl-ls/bsl-language-server.jar")
BSL_LS_TIMEOUT = int(os.environ.get("BSL_LS_TIMEOUT", "60"))
JAVA_OPTS = os.environ.get("JAVA_OPTS", "-Xmx512m")


# ─── Модели запросов/ответов ────────────────────────────────────────────────


class LintRequest(BaseModel):
    """Запрос на анализ BSL-кода."""

    code: str = Field(description="BSL-код для анализа")
    file_path: str = Field(
        default="/tmp/module.bsl",
        description="Виртуальный путь файла (для диагностик)",
    )
    rules: list[str] | None = Field(
        default=None,
        description="Subset правил (BSL LS не поддерживает --rules в CLI, "
        "используется .bsl-language-server.json конфиг). Поле зарезервировано.",
    )
    baseline_path: str | None = Field(
        default=None,
        description="Путь к baseline.json — известные ошибки, которые исключаются",
    )


class LintResponse(BaseModel):
    """Результат анализа BSL-кода."""

    total: int
    by_code: dict[str, int] = Field(description="{'BSL-WS-001': 3, ...}")
    diagnostics: list[dict[str, Any]] = Field(description="[{code, severity, line, column, message}]")
    latency_ms: int = Field(description="Время выполнения BSL LS, миллисекунды")


class FormatRequest(BaseModel):
    """Запрос на форматирование BSL-кода."""

    code: str
    style: str = Field(default="1c", description="1c | bsp (через .bsl-language-server.json)")


class FormatResponse(BaseModel):
    """Результат форматирования."""

    formatted_code: str
    changes_made: bool
    latency_ms: int


class HealthResponse(BaseModel):
    """Health check ответ."""

    status: str
    bsl_ls_available: bool
    bsl_ls_version: str | None = None


# ─── Утилиты (делегируют в bsl_ls.runner, DRY с SubprocessBslLsBackend) ──────


def _check_bsl_ls() -> bool:
    """Проверить, что BSL LS jar доступен."""
    return _check_bsl_ls_impl(BSL_LS_JAR)


def _get_bsl_ls_version() -> str | None:
    """Получить версию BSL LS."""
    return _get_bsl_ls_version_impl(BSL_LS_JAR)


def _run_bsl_ls(
    code: str,
    file_path: str,
    mode: str = "analyze",
    baseline_path: str | None = None,
) -> dict[str, Any]:
    """Запустить BSL LS как subprocess (делегирует в runner)."""
    return _run_bsl_ls_impl(
        code=code,
        file_path=file_path,
        mode=mode,
        baseline_path=baseline_path,
        jar_path=BSL_LS_JAR,
        java_opts=JAVA_OPTS,
        timeout=BSL_LS_TIMEOUT,
    )


# ─── Endpoints ──────────────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check.

    Возвращает:
        bsl_ls_available: True если jar файл существует.
        bsl_ls_version: версия BSL LS (если удалось получить).
    """
    available = _check_bsl_ls()
    version = _get_bsl_ls_version() if available else None

    return HealthResponse(
        status="ok" if available else "degraded",
        bsl_ls_available=available,
        bsl_ls_version=version,
    )


@app.post("/lint", response_model=LintResponse)
async def lint(request: LintRequest) -> LintResponse:
    """Анализ BSL-кода через BSL Language Server.

    187 диагностик. Timeout: 60 секунд (настраивается через BSL_LS_TIMEOUT env).

    Raises:
        HTTPException 500: при критической ошибке BSL LS или timeout.
    """
    start_time = time.monotonic()
    try:
        result = _run_bsl_ls(
            code=request.code,
            file_path=request.file_path,
            mode="analyze",
            baseline_path=request.baseline_path,
        )
    except subprocess.TimeoutExpired as exc:
        log.error("bsl_ls_lint_timeout timeout=%ds", BSL_LS_TIMEOUT)
        raise HTTPException(
            status_code=504,
            detail=f"BSL LS timed out after {BSL_LS_TIMEOUT}s",
        ) from exc
    except RuntimeError as exc:
        log.error("bsl_ls_lint_error err=%s", str(exc)[:200])
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    latency_ms = int((time.monotonic() - start_time) * 1000)

    return LintResponse(
        total=result["total"],
        by_code=result["by_code"],
        diagnostics=result["diagnostics"],
        latency_ms=latency_ms,
    )


@app.post("/format", response_model=FormatResponse)
async def format_code(request: FormatRequest) -> FormatResponse:
    """Форматирование BSL-кода.

    Style (1c/bsp) настраивается через .bsl-language-server.json в рабочей директории
    BSL LS. Если конфиг отсутствует — используется стиль по умолчанию (1c).

    Raises:
        HTTPException 500: при ошибке BSL LS или timeout.
    """
    start_time = time.monotonic()
    try:
        result = _run_bsl_ls(
            code=request.code,
            file_path="/tmp/format.bsl",
            mode="format",
        )
    except subprocess.TimeoutExpired as exc:
        log.error("bsl_ls_format_timeout timeout=%ds", BSL_LS_TIMEOUT)
        raise HTTPException(
            status_code=504,
            detail=f"BSL LS format timed out after {BSL_LS_TIMEOUT}s",
        ) from exc
    except RuntimeError as exc:
        log.error("bsl_ls_format_error err=%s", str(exc)[:200])
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    latency_ms = int((time.monotonic() - start_time) * 1000)

    return FormatResponse(
        formatted_code=result["formatted_code"],
        changes_made=result["changes_made"],
        latency_ms=latency_ms,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("BSL_LS_HTTP_PORT", "8080")),
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )
