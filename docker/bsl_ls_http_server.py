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

import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
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
    diagnostics: list[dict[str, Any]] = Field(
        description="[{code, severity, line, column, message}]"
    )
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


# ─── Утилиты ────────────────────────────────────────────────────────────────


def _check_bsl_ls() -> bool:
    """Проверить, что BSL LS jar доступен."""
    return Path(BSL_LS_JAR).exists()


def _get_bsl_ls_version() -> str | None:
    """Получить версию BSL LS (быстрая операция)."""
    if not _check_bsl_ls():
        return None
    try:
        result = subprocess.run(
            ["java", "-jar", BSL_LS_JAR, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception as exc:
        log.warning("Failed to get BSL LS version: %s", exc)
    return None


def _run_bsl_ls(
    code: str,
    file_path: str,
    mode: str = "analyze",
    baseline_path: str | None = None,
) -> dict[str, Any]:
    """Запустить BSL LS как subprocess.

    Args:
        code: BSL-код.
        file_path: виртуальный путь файла (для метаданных, не используется BSL LS).
        mode: 'analyze' для lint, 'format' для форматирования.
        baseline_path: путь к baseline.json (только для analyze).

    Returns:
        Словарь с результатами:
        - analyze: {total, by_code, diagnostics}
        - format: {formatted_code, changes_made}

    Raises:
        RuntimeError: если BSL LS недоступен.
        subprocess.TimeoutExpired: если BSL LS превысил timeout.
    """
    if not _check_bsl_ls():
        raise RuntimeError(f"BSL LS jar not found: {BSL_LS_JAR}")

    # Записываем код во временный файл
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".bsl", encoding="utf-8", delete=False
    ) as f:
        f.write(code)
        temp_path = f.name

    # Для analyze — отдельный файл с результатами (детерминированный парсинг)
    output_path = None
    if mode == "analyze":
        output_fd, output_path = tempfile.mkstemp(suffix=".json", text=True)
        os.close(output_fd)

    try:
        # Команда запуска BSL LS v0.25.x
        # CLI: java -jar bsl-ls.jar <command> --src <file> [--format json --output <file>]
        cmd: list[str] = [
            "java",
            *JAVA_OPTS.split(),
            "-jar",
            BSL_LS_JAR,
            mode,  # 'analyze' или 'format'
            "--src",
            temp_path,
        ]

        if mode == "analyze":
            cmd.extend(["--format", "json", "--output", output_path])
            if baseline_path:
                cmd.extend(["--baseline", baseline_path])

        log.info(
            "bsl_ls_run_start mode=%s file_size=%d",
            mode,
            len(code),
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=BSL_LS_TIMEOUT,
            check=False,
        )

        log.info(
            "bsl_ls_run_done mode=%s returncode=%d stderr_size=%d",
            mode,
            result.returncode,
            len(result.stderr or ""),
        )

        # BSL LS может вернуть non-zero при наличии диагностик — это нормально
        # для analyze. Для format non-zero = критическая ошибка.
        if mode == "format" and result.returncode != 0:
            raise RuntimeError(
                f"BSL LS format failed (rc={result.returncode}): {result.stderr[:500]}"
            )

        if mode == "analyze":
            # Критические ошибки Java/BSL LS (Exception, OutOfMemoryError)
            if result.stderr and (
                "Exception" in result.stderr
                or "OutOfMemoryError" in result.stderr
                or "java.lang.Error" in result.stderr
            ):
                raise RuntimeError(
                    f"BSL LS critical error: {result.stderr[:500]}"
                )
            return _parse_lint_output(output_path, file_path)
        else:
            # Для format — читаем результат из файла (BSL LS модифицирует in-place)
            formatted_code = Path(temp_path).read_text(encoding="utf-8")
            return {
                "formatted_code": formatted_code,
                "changes_made": formatted_code != code,
            }

    finally:
        Path(temp_path).unlink(missing_ok=True)
        if output_path:
            Path(output_path).unlink(missing_ok=True)


def _parse_lint_output(
    output_path: str | None,
    file_path: str,
) -> dict[str, Any]:
    """Парсить вывод BSL LS из JSON файла (--output).

    BSL LS v0.25.x выводит JSON массив issues в файл, указанный через --output.
    Структура каждого issue:
      {
        "code": "BSL-WS-001",
        "severity": "Error" | "Warning" | "Info" | "Hint",
        "range": {
          "start": {"line": 0, "character": 0},
          "end": {"line": 0, "character": 10}
        },
        "message": "Описание",
        "source": "module.bsl"
      }

    Args:
        output_path: путь к JSON файлу с результатами BSL LS.
        file_path: виртуальный путь файла (для логов).

    Returns:
        {total, by_code, diagnostics}.
    """
    diagnostics: list[dict[str, Any]] = []
    by_code: dict[str, int] = {}

    if output_path is None or not Path(output_path).exists():
        log.warning("bsl_ls_output_missing path=%s", output_path)
        return {"total": 0, "by_code": {}, "diagnostics": []}

    try:
        text = Path(output_path).read_text(encoding="utf-8").strip()
        if not text:
            return {"total": 0, "by_code": {}, "diagnostics": []}

        data = json.loads(text)

        # BSL LS выводит массив issues
        issues: list[dict[str, Any]] = []
        if isinstance(data, list):
            issues = data
        elif isinstance(data, dict):
            issues = data.get("issues", data.get("diagnostics", []))
            if not issues and "code" in data:
                issues = [data]

        for issue in issues:
            code = issue.get("code", "UNKNOWN")
            severity = _map_severity(issue.get("severity", "info"))
            range_data = issue.get("range", issue.get("location", {}))
            start = range_data.get("start", range_data)
            # BSL LS: 0-based → 1-based
            line = start.get("line", 0) + 1
            column = start.get("character", start.get("column", 0)) + 1

            diag = {
                "code": code,
                "severity": severity,
                "line": line,
                "column": column,
                "message": issue.get("message", ""),
                "source": issue.get("source", file_path),
            }
            diagnostics.append(diag)
            by_code[code] = by_code.get(code, 0) + 1

    except json.JSONDecodeError as exc:
        log.warning("bsl_ls_json_decode_error err=%s", exc)
    except Exception as exc:
        log.warning("bsl_ls_parse_error err=%s", exc)

    return {
        "total": len(diagnostics),
        "by_code": by_code,
        "diagnostics": diagnostics,
    }


def _map_severity(severity: str | int) -> str:
    """Маппинг severity из BSL LS в наш формат.

    BSL LS (строковый): Error, Warning, Info, Hint
    BSL LS (числовой, LSP): 1=Error, 2=Warning, 3=Info, 4=Hint
    Наш формат: critical, warning, info
    """
    if isinstance(severity, int):
        mapping = {1: "critical", 2: "warning", 3: "info", 4: "info"}
        return mapping.get(severity, "info")

    severity_lower = str(severity).lower()
    if severity_lower in ("error", "critical"):
        return "critical"
    if severity_lower in ("warning", "warn"):
        return "warning"
    return "info"


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
