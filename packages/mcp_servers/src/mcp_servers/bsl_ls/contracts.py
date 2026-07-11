"""bsl_ls-server: BSL Language Server (Java 17).

Источник: 1c-syntax/bsl-language-server (Docker image)
Рантайм: Java 17 subprocess / HTTP API к контейнеру
Stateless: каждый вызов — новый subprocess или HTTP request

См. ADR-0010 (MCP tool contracts) и ADR-0015 (3-container deployment).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ─── Inputs ──────────────────────────────────────────────────────────────────


class LintInput(BaseModel):
    """Input для bsl_ls.lint."""

    code: str = Field(description="BSL-код")
    file_path: str = Field(
        default="/tmp/module.bsl",
        description="Виртуальный путь (для диагностик)",
    )
    rules: list[str] | None = Field(
        default=None,
        description="Subset правил. None = все 187 диагностик.",
    )
    baseline_path: str | None = Field(
        default=None,
        description="Путь к baseline.json — известные ошибки, которые исключаются",
    )


class FormatInput(BaseModel):
    """Input для bsl_ls.format."""

    code: str
    style: Literal["1c", "bsp"] = "1c"


# ─── Outputs ─────────────────────────────────────────────────────────────────


class LintOutput(BaseModel):
    """Output для bsl_ls.lint."""

    total: int
    by_code: dict[str, int] = Field(description="{'BSL-WS-001': 3, 'BSL-NAMESPACE-001': 1}")
    diagnostics: list[dict[str, Any]] = Field(description="[{code, severity, line, column, message}]")


class FormatOutput(BaseModel):
    """Output для bsl_ls.format."""

    formatted_code: str
    changes_made: bool


# ─── Tool contracts ──────────────────────────────────────────────────────────


class Lint:
    """bsl_ls.lint — запуск BSL Language Server (187 диагностик)."""

    name: str = "bsl_ls.lint"
    description: str = (
        "Запуск BSL Language Server (187 диагностик). "
        "ВЫЗЫВАЕТСЯ ВАЛИДАТОРОМ — это главный детерминированный gate. "
        "Timeout: 60 сек. Пример: bsl_ls.lint(code='...')"
    )
    input_schema: dict[str, Any] = LintInput.model_json_schema()
    output_model: type[BaseModel] = LintOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 60  # Java startup + анализ
    idempotent: bool = True
    required_role: str = "VALIDATOR"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("bsl_ls.lint — реализация в Sprint 2")


class Format:
    """bsl_ls.format — форматирование BSL-кода."""

    name: str = "bsl_ls.format"
    description: str = "Форматирование BSL-кода (1C или BSP style)."
    input_schema: dict[str, Any] = FormatInput.model_json_schema()
    output_model: type[BaseModel] = FormatOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 30
    idempotent: bool = True
    required_role: str = "VALIDATOR"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("bsl_ls.format — реализация в Sprint 2")


BSL_LS_TOOLS: list[type[Any]] = [Lint, Format]
