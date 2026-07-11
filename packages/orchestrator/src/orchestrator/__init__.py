"""orchestrator — LangGraph pipeline.

Пакеты:
- state: TaskState, Subtask, Iteration, FSMState
- contracts: Result типы (PlanResult, GatherResult, CodeResult, ...)
- routers: детерминированные роутеры (route_after_validate, ...)
- errors: таксономия ошибок (14 классов)
- tool_groups: TOOL_GROUPS registry
- tool_provider: ToolProvider
- retry: with_retry функция
- persistence: PersistenceManager (stub)
- nodes: 10 заглушек узлов
- graph: каркас StateGraph (stub)

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from .contracts import (
    CodeResult,
    CommitResult,
    EscalateResult,
    GatheredCode,
    GatheredKnowledge,
    GatheredMetadata,
    GatherResult,
    Iteration,
    PlanResult,
    ReviewFinding,
    ReviewResult,
    ValidateResult,
    ValidationFinding,
)
from .errors import (
    AgentError,
    ErrorAction,
    EscalationRequestedError,
    IndexStaleError,
    LLMBudgetExceededError,
    LLMError,
    LLMRateLimitError,
    LLMUnavailableError,
    MaxIterationsExceededError,
    PersistenceError,
    PreflightError,
    ReviewRejectedError,
    RoleForbiddenError,
    SchemaViolationError,
    ToolConnectionError,
    ToolError,
    ToolExecutionError,
    ToolTimeoutError,
    ValidationFailedError,
    error_to_escalate_reason,
)
from .graph import build_graph, get_graph_structure
from .routers import (
    route_after_commit,
    route_after_retry,
    route_after_review,
    route_after_validate,
)
from .state import FSMState, Subtask, SubtaskConstraints, TaskState

__all__ = [
    # state
    "FSMState",
    "Subtask",
    "SubtaskConstraints",
    "TaskState",
    # contracts
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
    # routers
    "route_after_validate",
    "route_after_review",
    "route_after_retry",
    "route_after_commit",
    # errors
    "AgentError",
    "ErrorAction",
    "PreflightError",
    "IndexStaleError",
    "SchemaViolationError",
    "ToolError",
    "ToolTimeoutError",
    "ToolConnectionError",
    "ToolExecutionError",
    "RoleForbiddenError",
    "LLMError",
    "LLMUnavailableError",
    "LLMRateLimitError",
    "LLMBudgetExceededError",
    "ValidationFailedError",
    "ReviewRejectedError",
    "MaxIterationsExceededError",
    "EscalationRequestedError",
    "PersistenceError",
    "error_to_escalate_reason",
    # graph
    "build_graph",
    "get_graph_structure",
]
