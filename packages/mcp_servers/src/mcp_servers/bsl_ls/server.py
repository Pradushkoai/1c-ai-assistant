"""BslLsServer — обёртка над BSL LS backend (TD-S8-02).

BslLsServer — public API для nodes (validate_node). Делегирует lint/format/health_check
в backend стратегию (subprocess/http/stub). Выбор backend — через env
``1C_AI_BSL_LS_MODE=auto|subprocess|http|stub``.

3 режима (D-2026-07-13-16):
- Subprocess (default, без Docker): прямой ``java -jar`` subprocess.
- HTTP (Docker, production): HTTP client к BSL LS container.
- Stub (CI/tests): заглушка, 0 diagnostics.

Tool implementations (LintImplementation/FormatImplementation) — не меняются.

См. ADR-0010 (MCP tool contracts), ADR-0015 (3-container deployment),
D-2026-07-13-16.
"""

from __future__ import annotations

import logging
from typing import Any

from .backends import BslLsBackend, make_bsl_ls_backend
from .contracts import FormatInput, FormatOutput, LintInput, LintOutput

log = logging.getLogger(__name__)


class BslLsServer:
    """Обёртка над BSL LS backend.

    Attributes:
        backend: BslLsBackend стратегия (subprocess/http/stub).
    """

    def __init__(
        self,
        backend: BslLsBackend | None = None,
        # Legacy params (backward compat — создают HttpBslLsBackend если заданы).
        base_url: str | None = None,
        timeout: int | None = None,
    ) -> None:
        """Инициализация BslLsServer.

        Args:
            backend: BslLsBackend стратегия. Если None — ``make_bsl_ls_backend()``
                по env ``1C_AI_BSL_LS_MODE``.
            base_url: (legacy) URL BSL LS HTTP сервера. Если задан — принудительно
                HttpBslLsBackend. Игнорируется если backend задан.
            timeout: (legacy) timeout для HTTP. Игнорируется если backend задан.
        """
        if backend is not None:
            self.backend = backend
        elif base_url is not None or timeout is not None:
            # Legacy: explicit HTTP params → HttpBslLsBackend.
            from .backends import HttpBslLsBackend

            self.backend = HttpBslLsBackend(base_url=base_url, timeout=timeout)
        else:
            # Default: auto-detect by env.
            self.backend = make_bsl_ls_backend()

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
        """
        return await self.backend.lint(
            code=code,
            file_path=file_path,
            rules=rules,
            baseline_path=baseline_path,
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
        """
        return await self.backend.format(code=code, style=style)

    async def health_check(self) -> bool:
        """Проверить доступность BSL LS backend.

        Returns:
            True если backend может анализировать код.
        """
        return await self.backend.health_check()


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
