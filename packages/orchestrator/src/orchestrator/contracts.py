"""Контракты узлов pipeline.

Каждый узел:
- принимает TaskState (+ опционально config)
- возвращает dict, который LangGraph merge'ит в новый state

Чтобы избежать путаницы, контракты описаны как Pydantic-модели Result.
Узлы возвращают dict, соответствующий Result.model_dump().

См. ADR-0009 (Pipeline contracts — центральный контракт).
"""

from __future__ import annotations

from typing import Any, Literal

from parsers.models import BslModule, ModelConfig, ObjectRef, PlatformMethod
from pydantic import Field

from .state import Iteration, Subtask

# ─── Plan ────────────────────────────────────────────────────────────────────


class PlanResult(ModelConfig):
    """Результат Plan subgraph.

    Plan возвращает декомпозицию задачи на подзадачи.
    """

    subtasks: list[Subtask] = Field(description="Упорядоченный список подзадач")
    decomposition_strategy: Literal["feature", "refactor", "bugfix", "single"] = Field(
        description="Какая стратегия декомпозиции выбрана"
    )
    rationale: str = Field(description="Почему такая декомпозиция (для трассировки)")
    plan_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Доп. метаданные (например, dep_graph_snapshot)",
    )


# ─── Gather ──────────────────────────────────────────────────────────────────


class GatheredMetadata(ModelConfig):
    """Срез метаданных из metadata-server."""

    target_object: dict[str, Any] = Field(description="Метаданные target-объекта")
    related_objects: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Связанные объекты (для контекста)",
    )
    dependency_graph_slice: dict[str, Any] | None = None


class GatheredCode(ModelConfig):
    """Срез похожего кода из codebase-server."""

    similar_modules: list[BslModule] = Field(
        default_factory=list,
        description="Похожие модули (semantic_search)",
    )
    api_reference: list[dict[str, Any]] = Field(
        default_factory=list,
        description="API-справочник по общим модулям, которые можно вызывать",
    )


class GatheredKnowledge(ModelConfig):
    """Срез из kb-server."""

    patterns: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Подходящие паттерны (YAML из knowledge-base/patterns/)",
    )
    antipatterns: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Антипаттерны, релевантные задаче",
    )
    method_availability: dict[str, PlatformMethod] = Field(
        default_factory=dict,
        description="Метод → карточка (для check_method_availability в Coder)",
    )


class GatherResult(ModelConfig):
    """Результат Gather subgraph — собранный контекст для Coder."""

    subtask_id: str
    metadata: GatheredMetadata
    code: GatheredCode
    knowledge: GatheredKnowledge
    context_summary: str = Field(description="Краткое summary контекста — инжектируется в system prompt Coder")
    mcp_calls_made: list[str] = Field(
        default_factory=list,
        description="Какие MCP tools были вызваны (для трассировки)",
    )


# ─── Code ────────────────────────────────────────────────────────────────────


class CodeResult(ModelConfig):
    """Результат Code node — сгенерированный BSL-код."""

    subtask_id: str
    iteration_number: int = Field(ge=1)
    code: str = Field(description="Сгенерированный BSL-код")
    target_module: ObjectRef
    llm_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="model, tokens, latency — для метрик",
    )
    structured_output_valid: bool = Field(
        default=True,
        description="False = LLM нарушила JSON Schema, нужен retry",
    )


# ─── Validate ────────────────────────────────────────────────────────────────


class ValidationFinding(ModelConfig):
    """Одно замечание валидатора."""

    severity: Literal["critical", "warning", "info"]
    code: str = Field(description="BSL-WS-001, QUERY-IN-LOOP, ...")
    message: str
    line: int | None = None
    column: int | None = None
    source: Literal["bsl_ls", "kb_antipatterns", "custom_rules"]
    fix_hint: str | None = None


class ValidateResult(ModelConfig):
    """Результат Validate subgraph — fan-out/fan-in 3 валидаторов."""

    subtask_id: str
    iteration_number: int
    findings: list[ValidationFinding]
    passed: bool = Field(description="True = нет critical findings")
    severity_breakdown: dict[str, int] = Field(description="{'critical': N, 'warning': M, 'info': K}")
    failed_checks: list[dict[str, Any]] = Field(description="Только failed — для retry-промпта Coder")


# ─── Review ──────────────────────────────────────────────────────────────────


class ReviewFinding(ModelConfig):
    """Одно замечание рецензента."""

    severity: Literal["critical", "warning", "info"]
    category: Literal["antipattern", "context_violation", "pattern_mismatch", "style"]
    code: str
    message: str
    recommendation: str = Field(description="Что предложить LLM в retry")


class ReviewResult(ModelConfig):
    """Результат Review subgraph — LLM решает retry/escalate/proceed."""

    subtask_id: str
    iteration_number: int
    findings: list[ReviewFinding]
    decision: Literal["proceed", "retry", "escalate"]
    rationale: str = Field(description="Почему такое решение (для трассировки)")
    critical_findings: int = Field(ge=0)
    passed: bool = Field(description="True = decision == 'proceed'")


# ─── Commit ──────────────────────────────────────────────────────────────────


class CommitResult(ModelConfig):
    """Результат Commit node — git branch + commit + PR."""

    subtask_id: str
    branch_name: str
    commit_sha: str
    pr_url: str | None = None
    pr_number: int | None = None
    files_changed: list[str]
    diff_summary: str = Field(description="Краткая сводка изменений")


# ─── Escalate ────────────────────────────────────────────────────────────────


class EscalateResult(ModelConfig):
    """Результат Escalate node — PR с меткой needs-human-review."""

    subtask_id: str
    reason: Literal[
        "max_iterations_exceeded",
        "critical_findings_count",
        "schema_violation_loop",
        "tool_error",
        "llm_unavailable",
        "budget_exceeded",
        "manual_request",
    ]
    iteration_log: list[dict[str, Any]] = Field(description="История всех итераций")
    pr_url: str | None = None
    suggested_actions: list[str] = Field(
        default_factory=list,
        description="Что человек должен сделать руками",
    )


# Re-export Iteration for convenience (used by nodes)
__all__ = [
    "PlanResult",
    "GatheredMetadata",
    "GatheredCode",
    "GatheredKnowledge",
    "GatherResult",
    "CodeResult",
    "ValidationFinding",
    "ValidateResult",
    "ReviewFinding",
    "ReviewResult",
    "CommitResult",
    "EscalateResult",
    "Iteration",
]
