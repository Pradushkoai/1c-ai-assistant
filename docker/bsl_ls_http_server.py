"""docker/bsl_ls_http_server.py — HTTP сервер для BSL Language Server.

Оборачивает bsl-language-server.jar (Java 17) в HTTP API:
  POST /lint   — анализ BSL-кода (187 диагностик)
  POST /format — форматирование BSL-кода
  GET  /health — health check

BSL LS запускается как subprocess для каждого запроса (stateless).
Результат парсится из JSON stdout.

См. ADR-0015 (3-container deployment) и ADR-0010 (MCP tool contracts).
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="BSL LS HTTP Server", version="0.1.0")

BSL_LS_JAR = os.environ.get("BSL_LS_JAR", "/opt/bsl-ls/bsl-language-server.jar")
BSL_LS_TIMEOUT = int(os.environ.get("BSL_LS_TIMEOUT", "60"))
JAVA_OPTS = os.environ.get("JAVA_OPTS", "-Xmx512m")


class LintRequest(BaseModel):
    """Запрос на анализ BSL-кода."""

    code: str = Field(description="BSL-код для анализа")
    file_path: str = Field(default="/tmp/module.bsl", description="Виртуальный путь файла")
    rules: list[str] | None = Field(default=None, description="Subset правил. None = все.")
    baseline_path: str | None = Field(default=None, description="Путь к baseline.json")


class LintResponse(BaseModel):
    """Результат анализа BSL-кода."""

    total: int
    by_code: dict[str, int] = Field(description="{'BSL-WS-001': 3, ...}")
    diagnostics: list[dict[str, Any]] = Field(description="[{code, severity, line, column, message}]")


class FormatRequest(BaseModel):
    """Запрос на форматирование BSL-кода."""

    code: str
    style: str = Field(default="1c", description="1c | bsp")


class FormatResponse(BaseModel):
    """Результат форматирования."""

    formatted_code: str
    changes_made: bool


class HealthResponse(BaseModel):
    """Health check ответ."""

    status: str
    bsl_ls_available: bool
    bsl_ls_version: str | None = None


def _check_bsl_ls() -> bool:
    """Проверить, что BSL LS jar доступен."""
    return Path(BSL_LS_JAR).exists()


def _run_bsl_ls(
    code: str,
    file_path: str,
    mode: str = "analyze",
    rules: list[str] | None = None,
    baseline_path: str | None = None,
) -> dict[str, Any]:
    """Запустить BSL LS как subprocess.

    Args:
        code: BSL-код.
        file_path: виртуальный путь файла.
        mode: 'analyze' для lint, 'format' для форматирования.
        rules: subset правил (только для analyze).
        baseline_path: путь к baseline.json (только для analyze).

    Returns:
        Словарь с результатами (для analyze) или отформатированным кодом (для format).

    Raises:
        RuntimeError: если BSL LS недоступен или превысил timeout.
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

    try:
        # Команда запуска BSL LS
        cmd: list[str] = [
            "java",
            *JAVA_OPTS.split(),
            "-jar",
            BSL_LS_JAR,
            mode,
            temp_path,
            "--format",
            "json",
        ]

        # Добавляем правила, если указаны
        if rules and mode == "analyze":
            for rule in rules:
                cmd.extend(["--diagnostics", rule])

        # Добавляем baseline, если указан
        if baseline_path and mode == "analyze":
            cmd.extend(["--baseline", baseline_path])

        # Запускаем subprocess
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=BSL_LS_TIMEOUT,
            check=False,
        )

        if result.returncode != 0 and mode == "analyze":
            # BSL LS может вернуть non-zero при наличии диагностик — это нормально
            # Парсим stderr для критических ошибок
            if "Error" in result.stderr and "Exception" in result.stderr:
                raise RuntimeError(
                    f"BSL LS error: {result.stderr[:500]}"
                )

        if mode == "analyze":
            return _parse_lint_output(result.stdout, result.stderr, file_path)
        else:
            # Для format — читаем результат из stdout или из файла
            formatted_code = Path(temp_path).read_text(encoding="utf-8")
            return {
                "formatted_code": formatted_code,
                "changes_made": formatted_code != code,
            }

    finally:
        Path(temp_path).unlink(missing_ok=True)


def _parse_lint_output(
    stdout: str,
    stderr: str,
    file_path: str,
) -> dict[str, Any]:
    """Парсить вывод BSL LS (JSON) → диагностики.

    BSL LS выводит JSON в stdout при --format json.
    Структура: [{code, severity, range:{start:{line, character}, end:{line, character}}, message}, ...]

    Args:
        stdout: stdout от BSL LS.
        stderr: stderr от BSL LS.
        file_path: путь файла (для diagnostics).

    Returns:
        {total, by_code, diagnostics}.
    """
    diagnostics: list[dict[str, Any]] = []
    by_code: dict[str, int] = {}

    # Пытаемся распарсить JSON из stdout
    try:
        # BSL LS может выводить массив или объект с массивом
        text = stdout.strip()
        if not text:
            # Если stdout пустой — возможно stderr содержит JSON
            text = stderr.strip()

        if text:
            data = json.loads(text)
            # Нормализуем — может быть массив или dict с "issues"
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
                line = start.get("line", 0) + 1  # BSL LS: 0-based → 1-based
                column = start.get("character", start.get("column", 0))

                diag = {
                    "code": code,
                    "severity": severity,
                    "line": line,
                    "column": column,
                    "message": issue.get("message", ""),
                }
                diagnostics.append(diag)
                by_code[code] = by_code.get(code, 0) + 1

    except json.JSONDecodeError:
        # Если JSON не распарсился — возвращаем пустой результат
        # (BSL LS может выводить логи в stdout)
        pass

    return {
        "total": len(diagnostics),
        "by_code": by_code,
        "diagnostics": diagnostics,
    }


def _map_severity(severity: str | int) -> str:
    """Маппинг severity из BSL LS в наш формат.

    BSL LS: 1=Error, 2=Warning, 3=Info, 4=Hint
    Наш формат: critical, warning, info
    """
    if isinstance(severity, int):
        mapping = {1: "critical", 2: "warning", 3: "info", 4: "info"}
        return mapping.get(severity, "info")

    severity_lower = severity.lower()
    if severity_lower in ("error", "critical"):
        return "critical"
    if severity_lower in ("warning", "warn"):
        return "warning"
    return "info"


# ─── Endpoints ──────────────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check."""
    available = _check_bsl_ls()
    version = None
    if available:
        # Пытаемся получить версию (быстрая операция)
        try:
            result = subprocess.run(
                ["java", "-jar", BSL_LS_JAR, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
        except Exception:
            pass

    return HealthResponse(
        status="ok" if available else "degraded",
        bsl_ls_available=available,
        bsl_ls_version=version,
    )


@app.post("/lint", response_model=LintResponse)
async def lint(request: LintRequest) -> LintResponse:
    """Анализ BSL-кода через BSL Language Server.

    187 диагностик. Timeout: 60 секунд.
    """
    start_time = time.monotonic()
    try:
        result = _run_bsl_ls(
            code=request.code,
            file_path=request.file_path,
            mode="analyze",
            rules=request.rules,
            baseline_path=request.baseline_path,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"BSL LS timed out after {BSL_LS_TIMEOUT}s"
        ) from exc
    except RuntimeError:
        raise

    elapsed = time.monotonic() - start_time
    # Добавляем latency в ответ (для метрик)
    return LintResponse(
        total=result["total"],
        by_code=result["by_code"],
        diagnostics=result["diagnostics"],
    )


@app.post("/format", response_model=FormatResponse)
async def format_code(request: FormatRequest) -> FormatResponse:
    """Форматирование BSL-кода."""
    try:
        result = _run_bsl_ls(
            code=request.code,
            file_path="/tmp/format.bsl",
            mode="format",
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"BSL LS format timed out after {BSL_LS_TIMEOUT}s"
        ) from exc

    return FormatResponse(
        formatted_code=result["formatted_code"],
        changes_made=result["changes_made"],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("BSL_LS_HTTP_PORT", "8080")),
    )
