"""Контракты lifecycle tools Facade'а.

Каждый tool возвращает:
- свой основной результат
- _next_action: {tool, args, why} — что вызывать дальше
- _artifact_id: для передачи между вызовами

См. ADR-0013 (Agent-Facade — 7 lifecycle tools).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _FacadeBase(BaseModel):
    """Базовый класс для Facade contracts."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class NextAction(_FacadeBase):
    """Что вызывать дальше — для LLM внешнего клиента."""

    tool: str = Field(description="Имя следующего lifecycle tool'а")
    args: dict[str, Any] = Field(description="Аргументы для следующего вызова")
    why: str = Field(description="Почему именно это действие")


# ─── Plan ────────────────────────────────────────────────────────────────────


class PlanInput(_FacadeBase):
    """Input для plan."""

    task: str = Field(description="Описание задачи на естественном языке")
    config_name: str
    config_version: str
    platform_version: str


class PlanOutput(_FacadeBase):
    """Output для plan."""

    plan_id: str = Field(description="ID плана — для передачи в gather")
    subtasks: list[dict[str, Any]] = Field(description="Список подзадач")
    decomposition_strategy: str
    rationale: str
    next_action: NextAction
    artifact_id: str = Field(description="= plan_id")


# ─── Gather ──────────────────────────────────────────────────────────────────


class GatherInput(_FacadeBase):
    """Input для gather."""

    plan_id: str
    subtask_id: str


class GatherOutput(_FacadeBase):
    """Output для gather."""

    subtask_id: str
    context_summary: str
    patterns_applied: list[str]
    mcp_calls_made: list[str]
    next_action: NextAction
    artifact_id: str = Field(description="plan_id + subtask_id (для generate)")


# ─── Generate ────────────────────────────────────────────────────────────────


class GenerateInput(_FacadeBase):
    """Input для generate."""

    plan_id: str
    subtask_id: str
    iteration: int = Field(default=1, ge=1)


class GenerateOutput(_FacadeBase):
    """Output для generate."""

    subtask_id: str
    iteration: int
    code: str
    explanation: str
    patterns_applied: list[str]
    next_action: NextAction
    artifact_id: str = Field(description="= subtask_id + iteration (для validate)")


# ─── Validate ────────────────────────────────────────────────────────────────


class ValidateInput(_FacadeBase):
    """Input для validate."""

    artifact_id: str = Field(description="Из GenerateOutput.artifact_id")


class ValidateOutput(_FacadeBase):
    """Output для validate."""

    artifact_id: str
    passed: bool
    findings: list[dict[str, Any]]
    severity_breakdown: dict[str, int]
    failed_checks: list[dict[str, Any]] = Field(description="Для retry")
    next_action: NextAction


# ─── Review ──────────────────────────────────────────────────────────────────


class ReviewInput(_FacadeBase):
    """Input для review."""

    artifact_id: str


class ReviewOutput(_FacadeBase):
    """Output для review."""

    artifact_id: str
    decision: Literal["proceed", "retry", "escalate"]
    findings: list[dict[str, Any]]
    rationale: str
    pr_url: str | None = None
    next_action: NextAction


# ─── Explain ────────────────────────────────────────────────────────────────


class ExplainInput(_FacadeBase):
    """Input для explain — обратный путь: код → объяснение."""

    code: str | None = None
    query: str | None = Field(default=None, description="Текстовый запрос (что объяснить)")
    config_name: str | None = None
    config_version: str | None = None


class ExplainOutput(_FacadeBase):
    """Output для explain."""

    explanation: str
    related_patterns: list[dict[str, Any]]
    related_antipatterns: list[dict[str, Any]]
    similar_modules: list[dict[str, Any]]


# ─── run_cli ─────────────────────────────────────────────────────────────────


class RunCliInput(_FacadeBase):
    """Input для run_cli — proxy к скрытым MCP tools."""

    tool_name: str = Field(description="metadata.get_metadata | codebase.call_graph | ...")
    args: dict[str, Any]
    caller_role: str = Field(
        default="GATHERER",
        description="Для проверки прав через TOOL_GROUPS",
    )


class RunCliOutput(_FacadeBase):
    """Output для run_cli."""

    tool_name: str
    result: dict[str, Any]
    warning: str | None = Field(default=None, description="Если tool не найден/запрещён")


# ─── data_status ────────────────────────────────────────────────────────────


class DataStatusOutput(_FacadeBase):
    """Output для data_status."""

    paths: dict[str, bool]
    configs: list[dict[str, Any]]
    indexes_freshness: dict[str, dict[str, bool]]
    missing_prerequisites: list[str] = Field(description="Что нужно сделать до старта")
