"""bsl_ls.runner — standalone-функции для запуска BSL LS (TD-S8-02).

Перенесены из ``docker/bsl_ls_http_server.py`` для DRY: и subprocess backend
(in-process), и HTTP server (Docker) используют одни и те же функции.

Функции принимают ``jar_path``, ``java_opts``, ``timeout`` как параметры —
не зависят от глобальных env vars (caller управляет конфигом).

См. ADR-0010, ADR-0015, D-2026-07-13-16.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Default paths (могут быть переопределены через env или параметры).
DEFAULT_JAR_PATH = os.environ.get("BSL_LS_JAR", "vendor/bsl-ls/bsl-language-server.jar")
DEFAULT_JAVA_OPTS = os.environ.get("JAVA_OPTS", "-Xmx512m")
DEFAULT_TIMEOUT = int(os.environ.get("BSL_LS_TIMEOUT", "60"))


def check_bsl_ls(jar_path: str = DEFAULT_JAR_PATH) -> bool:
    """Проверить, что BSL LS jar доступен.

    Args:
        jar_path: путь к bsl-language-server.jar.

    Returns:
        True если файл существует.
    """
    return Path(jar_path).exists()


def get_bsl_ls_version(
    jar_path: str = DEFAULT_JAR_PATH,
    timeout: int = 10,
) -> str | None:
    """Получить версию BSL LS (быстрая операция).

    Args:
        jar_path: путь к jar.
        timeout: timeout в секундах.

    Returns:
        Строка версии или None если jar недоступен / ошибка.
    """
    if not check_bsl_ls(jar_path):
        return None
    try:
        result = subprocess.run(
            ["java", "-jar", jar_path, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception as exc:
        log.warning("Failed to get BSL LS version: %s", exc)
    return None


def run_bsl_ls(
    code: str,
    file_path: str,
    mode: str = "analyze",
    baseline_path: str | None = None,
    jar_path: str = DEFAULT_JAR_PATH,
    java_opts: str = DEFAULT_JAVA_OPTS,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Запустить BSL LS как subprocess.

    Args:
        code: BSL-код.
        file_path: виртуальный путь файла (для метаданных, не используется BSL LS).
        mode: ``'analyze'`` для lint, ``'format'`` для форматирования.
        baseline_path: путь к baseline.json (только для analyze).
        jar_path: путь к bsl-language-server.jar.
        java_opts: JVM options (например, ``-Xmx512m``).
        timeout: timeout в секундах.

    Returns:
        Словарь с результатами:
        - analyze: ``{total, by_code, diagnostics}``
        - format: ``{formatted_code, changes_made}``

    Raises:
        RuntimeError: если BSL LS недоступен.
        subprocess.TimeoutExpired: если BSL LS превысил timeout.
    """
    if not check_bsl_ls(jar_path):
        raise RuntimeError(f"BSL LS jar not found: {jar_path}")

    # Записываем код во временный файл.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".bsl", encoding="utf-8", delete=False) as f:
        f.write(code)
        temp_path = f.name

    # Для analyze — temp директория для output (BSL LS v1.0.x пишет bsl-json.json в -o dir).
    output_dir: str | None = None
    if mode == "analyze":
        output_dir = tempfile.mkdtemp(prefix="bsl_ls_output_")

    try:
        # BSL LS v1.0.x CLI syntax:
        # analyze: java -jar bsl-ls.jar analyze -s <srcDir> -r json -o <outputDir>
        # format:  java -jar bsl-ls.jar format -s <srcDir>
        cmd: list[str] = [
            "java",
            *java_opts.split(),
            "-jar",
            jar_path,
            mode,  # 'analyze' или 'format'
            "-s",  # --srcDir (short form)
            temp_path,
        ]

        if mode == "analyze":
            assert output_dir is not None
            cmd.extend(["-r", "json", "-o", output_dir])

        log.info("bsl_ls_run_start mode=%s file_size=%d", mode, len(code))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
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
            raise RuntimeError(f"BSL LS format failed (rc={result.returncode}): {result.stderr[:500]}")

        if mode == "analyze":
            # Критические ошибки Java/BSL LS (Exception, OutOfMemoryError).
            if result.stderr and (
                "Exception" in result.stderr
                or "OutOfMemoryError" in result.stderr
                or "java.lang.Error" in result.stderr
            ):
                raise RuntimeError(f"BSL LS critical error: {result.stderr[:500]}")
            # BSL LS v1.0.x writes bsl-json.json to output dir.
            assert output_dir is not None
            json_path = Path(output_dir) / "bsl-json.json"
            return parse_lint_output(str(json_path) if json_path.exists() else None, file_path)
        else:
            # Для format — читаем результат из файла (BSL LS модифицирует in-place).
            formatted_code = Path(temp_path).read_text(encoding="utf-8")
            return {
                "formatted_code": formatted_code,
                "changes_made": formatted_code != code,
            }

    finally:
        Path(temp_path).unlink(missing_ok=True)
        if output_dir:
            import shutil

            shutil.rmtree(output_dir, ignore_errors=True)


def parse_lint_output(
    output_path: str | None,
    file_path: str,
) -> dict[str, Any]:
    """Парсить вывод BSL LS из JSON файла.

    BSL LS v1.0.x выводит JSON в файл ``bsl-json.json`` в директории, указанной
    через ``-o``. Структура::

        {
          "date": "...",
          "fileinfos": [
            {
              "path": "file:///...",
              "diagnostics": [
                {
                  "code": "DeprecatedMessage",
                  "severity": "Information",
                  "range": {"start": {"line": 5, "character": 4}, "end": {...}},
                  "message": "Не следует использовать...",
                  "source": "test.bsl"
                }
              ],
              "metrics": {...}
            }
          ],
          "sourceDir": "..."
        }

    Args:
        output_path: путь к JSON файлу с результатами BSL LS.
        file_path: виртуальный путь файла (для логов).

    Returns:
        ``{total, by_code, diagnostics}``.
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

        # BSL LS v1.0.x: {fileinfos: [{diagnostics: [...]}]}
        issues: list[dict[str, Any]] = []
        if isinstance(data, dict):
            fileinfos = data.get("fileinfos", [])
            for fi in fileinfos:
                if isinstance(fi, dict):
                    fi_diags = fi.get("diagnostics", [])
                    if isinstance(fi_diags, list):
                        issues.extend(fi_diags)
        elif isinstance(data, list):
            # Legacy v0.25.x: array of issues.
            issues = data

        for issue in issues:
            code = issue.get("code", "UNKNOWN")
            severity = map_severity(issue.get("severity", "info"))
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


def map_severity(severity: str | int) -> str:
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
