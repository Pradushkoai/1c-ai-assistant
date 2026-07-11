"""Taxonomy ошибок pipeline.

Иерархия:
    AgentError (базовый)
    ├── PreflightError           — данные не готовы (ABORT)
    ├── IndexStaleError          — индексы устарели (ABORT)
    ├── SchemaViolationError     — LLM нарушила JSON Schema (RETRY)
    ├── ToolError                — ошибка MCP tool
    │   ├── ToolTimeoutError      (RETRY)
    │   ├── ToolConnectionError   (RETRY)
    │   ├── ToolExecutionError    (ESCALATE)
    │   └── RoleForbiddenError    (ABORT)
    ├── LLMError                 — ошибка LLM-провайдера
    │   ├── LLMUnavailableError   (RETRY)
    │   ├── LLMRateLimitError     (RETRY)
    │   └── LLMBudgetExceededError (ESCALATE)
    ├── ValidationFailedError    — детерминированный gate не прошёл (RETRY)
    ├── ReviewRejectedError      — LLM-рецензент отверг (RETRY)
    ├── MaxIterationsExceededError — 3 итерации failed (ESCALATE)
    ├── EscalationRequestedError — явная эскалация (ESCALATE)
    └── PersistenceError         — PostgresSaver упал (ABORT)

См. ADR-0014 (Error taxonomy + PostgresSaver).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal


class ErrorAction(StrEnum):
    """Что делать с ошибкой."""

    RETRY = "retry"
    ESCALATE = "escalate"
    ABORT = "abort"


class AgentError(Exception):
    """Базовый класс всех ошибок pipeline.

    Attributes:
        code: код ошибки (например, 'TOOL_TIMEOUT').
        action: что делать — retry, escalate, abort.
        details: словарь с дополнительной информацией.
        http_status: HTTP статус для REST API (опционально).
    """

    code: str = "AGENT_ERROR"
    action: ErrorAction = ErrorAction.ESCALATE
    http_status: int | None = None

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        action: ErrorAction | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if code:
            self.code = code
        if action:
            self.action = action
        self.details = details or {}


# ─── Preflight ошибки ────────────────────────────────────────────────────────


class PreflightError(AgentError):
    """Данные не готовы к запуску pipeline."""

    code = "PREFLIGHT_FAILED"
    action = ErrorAction.ABORT


class IndexStaleError(AgentError):
    """Индексы устарели, нужен config build --force."""

    code = "INDEX_STALE"
    action = ErrorAction.ABORT


# ─── Schema violations ───────────────────────────────────────────────────────


class SchemaViolationError(AgentError):
    """LLM нарушила JSON Schema при structured_output.

    Если срабатывает в retry-цикле > 2 раз — escalate.
    """

    code = "SCHEMA_VIOLATION"
    action = ErrorAction.RETRY

    def __init__(self, message: str, *, schema_errors: list[Any], **kwargs: Any) -> None:
        super().__init__(message, details={"schema_errors": schema_errors}, **kwargs)


# ─── Tool errors ─────────────────────────────────────────────────────────────


class ToolError(AgentError):
    """Базовая ошибка MCP tool."""

    code = "TOOL_ERROR"
    action = ErrorAction.RETRY


class ToolTimeoutError(ToolError):
    """Tool превысил timeout."""

    code = "TOOL_TIMEOUT"
    action = ErrorAction.RETRY

    def __init__(self, tool_name: str, timeout: int, **kwargs: Any) -> None:
        super().__init__(
            f"Tool {tool_name} timed out after {timeout}s",
            details={"tool_name": tool_name, "timeout": timeout},
            **kwargs,
        )


class ToolConnectionError(ToolError):
    """MCP-сервер недоступен (network error)."""

    code = "TOOL_CONNECTION_FAILED"
    action = ErrorAction.RETRY

    def __init__(self, tool_name: str, original: Exception, **kwargs: Any) -> None:
        super().__init__(
            f"Cannot connect to {tool_name}: {original}",
            details={"tool_name": tool_name, "original_type": type(original).__name__},
            **kwargs,
        )


class ToolExecutionError(ToolError):
    """Tool выполнен, но вернул ошибку."""

    code = "TOOL_EXECUTION_ERROR"
    action = ErrorAction.ESCALATE


class RoleForbiddenError(ToolError):
    """Роль не имеет прав на вызов этого tool'а.

    Это НЕ retry — это bug в TOOL_GROUPS или в коде узла.
    """

    code = "ROLE_FORBIDDEN"
    action = ErrorAction.ABORT

    def __init__(self, role: str, tool_name: str, **kwargs: Any) -> None:
        super().__init__(
            f"Role {role} cannot call {tool_name}",
            details={"role": role, "tool_name": tool_name},
            **kwargs,
        )


# ─── LLM errors ──────────────────────────────────────────────────────────────


class LLMError(AgentError):
    """Базовая ошибка LLM-провайдера."""

    code = "LLM_ERROR"
    action = ErrorAction.RETRY


class LLMUnavailableError(LLMError):
    """5xx от LLM-провайдера."""

    code = "LLM_UNAVAILABLE"
    action = ErrorAction.RETRY


class LLMRateLimitError(LLMError):
    """429 — превышен rate limit."""

    code = "LLM_RATE_LIMIT"
    action = ErrorAction.RETRY

    def __init__(self, retry_after: int | None = None, **kwargs: Any) -> None:
        super().__init__(
            "Rate limit exceeded",
            details={"retry_after": retry_after},
            **kwargs,
        )


class LLMBudgetExceededError(LLMError):
    """Превышен token budget для задачи."""

    code = "LLM_BUDGET_EXCEEDED"
    action = ErrorAction.ESCALATE

    def __init__(self, used: int, limit: int, **kwargs: Any) -> None:
        super().__init__(
            f"Token budget exceeded: {used}/{limit}",
            details={"used": used, "limit": limit},
            **kwargs,
        )


# ─── Pipeline-flow ошибки ────────────────────────────────────────────────────


class ValidationFailedError(AgentError):
    """Детерминированный gate (BSL LS + антипаттерны) не прошёл.

    Это НЕ критическая ошибка — это сигнал для retry Coder'а.
    """

    code = "VALIDATION_FAILED"
    action = ErrorAction.RETRY

    def __init__(self, failed_checks: list[dict[str, Any]], **kwargs: Any) -> None:
        super().__init__(
            f"Validation failed: {len(failed_checks)} checks",
            details={"failed_checks": failed_checks},
            **kwargs,
        )


class ReviewRejectedError(AgentError):
    """LLM-рецензент отверг код."""

    code = "REVIEW_REJECTED"
    action = ErrorAction.RETRY


class MaxIterationsExceededError(AgentError):
    """Достигнут max_iterations (3) — нужна эскалация."""

    code = "MAX_ITERATIONS_EXCEEDED"
    action = ErrorAction.ESCALATE

    def __init__(self, subtask_id: str, iterations: int, **kwargs: Any) -> None:
        super().__init__(
            f"Subtask {subtask_id}: {iterations} iterations failed",
            details={"subtask_id": subtask_id, "iterations": iterations},
            **kwargs,
        )


class EscalationRequestedError(AgentError):
    """Явный запрос эскалации от Review'ера."""

    code = "ESCALATION_REQUESTED"
    action = ErrorAction.ESCALATE


# ─── Persistence ─────────────────────────────────────────────────────────────


class PersistenceError(AgentError):
    """PostgresSaver не смог сохранить/прочитать state."""

    code = "PERSISTENCE_ERROR"
    action = ErrorAction.ABORT


# ─── Mapping: error → escalate reason ────────────────────────────────────────


def error_to_escalate_reason(
    err: AgentError,
) -> Literal[
    "max_iterations_exceeded",
    "critical_findings_count",
    "schema_violation_loop",
    "tool_error",
    "llm_unavailable",
    "budget_exceeded",
    "manual_request",
]:
    """Преобразовать ошибку в reason для EscalateResult.

    Args:
        err: ошибка AgentError.

    Returns:
        Строка причины эскалации.
    """
    if isinstance(err, MaxIterationsExceededError):
        return "max_iterations_exceeded"
    if isinstance(err, SchemaViolationError):
        return "schema_violation_loop"
    if isinstance(err, LLMBudgetExceededError):
        return "budget_exceeded"
    if isinstance(err, LLMUnavailableError):
        return "llm_unavailable"
    if isinstance(err, ToolError):
        return "tool_error"
    # critical_findings_count — ставится роутером review, не ошибкой
    # manual_request — пользователь сам запросил эскалацию
    return "tool_error"
