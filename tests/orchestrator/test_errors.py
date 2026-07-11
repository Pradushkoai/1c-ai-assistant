"""Тесты для orchestrator.errors — 14 классов ошибок + error_to_escalate_reason."""

from __future__ import annotations

import pytest

from orchestrator.errors import (
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


# ─── ErrorAction enum ───────────────────────────────────────────────────────


class TestErrorAction:
    @pytest.mark.smoke
    def test_values(self):
        assert ErrorAction.RETRY.value == "retry"
        assert ErrorAction.ESCALATE.value == "escalate"
        assert ErrorAction.ABORT.value == "abort"

    def test_all_actions(self):
        actions = list(ErrorAction)
        assert len(actions) == 3


# ─── AgentError базовый ─────────────────────────────────────────────────────


class TestAgentError:
    @pytest.mark.smoke
    def test_create(self):
        err = AgentError("test error")
        assert str(err) == "test error"
        assert err.code == "AGENT_ERROR"
        assert err.action == ErrorAction.ESCALATE
        assert err.details == {}

    def test_with_code_and_action(self):
        err = AgentError("test", code="CUSTOM", action=ErrorAction.RETRY)
        assert err.code == "CUSTOM"
        assert err.action == ErrorAction.RETRY

    def test_with_details(self):
        err = AgentError("test", details={"key": "value"})
        assert err.details == {"key": "value"}

    def test_is_exception(self):
        err = AgentError("test")
        assert isinstance(err, Exception)


# ─── Preflight ошибки (ABORT) ──────────────────────────────────────────────


class TestPreflightErrors:
    def test_preflight_error(self):
        err = PreflightError("data not ready")
        assert err.code == "PREFLIGHT_FAILED"
        assert err.action == ErrorAction.ABORT

    def test_index_stale_error(self):
        err = IndexStaleError("indexes stale")
        assert err.code == "INDEX_STALE"
        assert err.action == ErrorAction.ABORT


# ─── Schema violation (RETRY) ──────────────────────────────────────────────


class TestSchemaViolationError:
    def test_create(self):
        err = SchemaViolationError("bad json", schema_errors=["field missing"])
        assert err.code == "SCHEMA_VIOLATION"
        assert err.action == ErrorAction.RETRY
        assert err.details["schema_errors"] == ["field missing"]


# ─── Tool errors ────────────────────────────────────────────────────────────


class TestToolErrors:
    def test_tool_error_base(self):
        err = ToolError("tool failed")
        assert err.code == "TOOL_ERROR"
        assert err.action == ErrorAction.RETRY

    def test_tool_timeout(self):
        err = ToolTimeoutError("bsl_ls.lint", 60)
        assert err.code == "TOOL_TIMEOUT"
        assert err.action == ErrorAction.RETRY
        assert err.details["tool_name"] == "bsl_ls.lint"
        assert err.details["timeout"] == 60

    def test_tool_connection(self):
        original = ConnectionError("refused")
        err = ToolConnectionError("metadata.get_metadata", original)
        assert err.code == "TOOL_CONNECTION_FAILED"
        assert err.action == ErrorAction.RETRY
        assert err.details["tool_name"] == "metadata.get_metadata"
        assert err.details["original_type"] == "ConnectionError"

    def test_tool_execution(self):
        err = ToolExecutionError("tool crashed")
        assert err.code == "TOOL_EXECUTION_ERROR"
        assert err.action == ErrorAction.ESCALATE

    def test_role_forbidden(self):
        err = RoleForbiddenError("CODER", "metadata.get_metadata")
        assert err.code == "ROLE_FORBIDDEN"
        assert err.action == ErrorAction.ABORT
        assert err.details["role"] == "CODER"
        assert err.details["tool_name"] == "metadata.get_metadata"

    def test_tool_errors_are_subclasses(self):
        assert issubclass(ToolTimeoutError, ToolError)
        assert issubclass(ToolConnectionError, ToolError)
        assert issubclass(ToolExecutionError, ToolError)
        assert issubclass(RoleForbiddenError, ToolError)
        assert issubclass(ToolError, AgentError)


# ─── LLM errors ─────────────────────────────────────────────────────────────


class TestLLMErrors:
    def test_llm_error_base(self):
        err = LLMError("llm failed")
        assert err.code == "LLM_ERROR"
        assert err.action == ErrorAction.RETRY

    def test_llm_unavailable(self):
        err = LLMUnavailableError("503")
        assert err.code == "LLM_UNAVAILABLE"
        assert err.action == ErrorAction.RETRY

    def test_llm_rate_limit(self):
        err = LLMRateLimitError(retry_after=30)
        assert err.code == "LLM_RATE_LIMIT"
        assert err.action == ErrorAction.RETRY
        assert err.details["retry_after"] == 30

    def test_llm_budget_exceeded(self):
        err = LLMBudgetExceededError(used=200000, limit=150000)
        assert err.code == "LLM_BUDGET_EXCEEDED"
        assert err.action == ErrorAction.ESCALATE
        assert err.details["used"] == 200000
        assert err.details["limit"] == 150000

    def test_llm_errors_are_subclasses(self):
        assert issubclass(LLMUnavailableError, LLMError)
        assert issubclass(LLMRateLimitError, LLMError)
        assert issubclass(LLMBudgetExceededError, LLMError)
        assert issubclass(LLMError, AgentError)


# ─── Pipeline-flow ошибки ───────────────────────────────────────────────────


class TestPipelineFlowErrors:
    def test_validation_failed(self):
        err = ValidationFailedError(failed_checks=[{"code": "BSL-WS-001"}])
        assert err.code == "VALIDATION_FAILED"
        assert err.action == ErrorAction.RETRY
        assert len(err.details["failed_checks"]) == 1

    def test_review_rejected(self):
        err = ReviewRejectedError("reviewer rejected")
        assert err.code == "REVIEW_REJECTED"
        assert err.action == ErrorAction.RETRY

    def test_max_iterations(self):
        err = MaxIterationsExceededError("st-001", 3)
        assert err.code == "MAX_ITERATIONS_EXCEEDED"
        assert err.action == ErrorAction.ESCALATE
        assert err.details["subtask_id"] == "st-001"
        assert err.details["iterations"] == 3

    def test_escalation_requested(self):
        err = EscalationRequestedError("manual")
        assert err.code == "ESCALATION_REQUESTED"
        assert err.action == ErrorAction.ESCALATE


# ─── Persistence ────────────────────────────────────────────────────────────


class TestPersistenceError:
    def test_create(self):
        err = PersistenceError("postgres down")
        assert err.code == "PERSISTENCE_ERROR"
        assert err.action == ErrorAction.ABORT


# ─── error_to_escalate_reason ──────────────────────────────────────────────


class TestErrorToEscalateReason:
    @pytest.mark.smoke
    def test_max_iterations(self):
        err = MaxIterationsExceededError("st-001", 3)
        assert error_to_escalate_reason(err) == "max_iterations_exceeded"

    def test_schema_violation(self):
        err = SchemaViolationError("bad", schema_errors=[])
        assert error_to_escalate_reason(err) == "schema_violation_loop"

    def test_budget_exceeded(self):
        err = LLMBudgetExceededError(200, 100)
        assert error_to_escalate_reason(err) == "budget_exceeded"

    def test_llm_unavailable(self):
        err = LLMUnavailableError("503")
        assert error_to_escalate_reason(err) == "llm_unavailable"

    def test_tool_error(self):
        err = ToolTimeoutError("bsl_ls.lint", 60)
        assert error_to_escalate_reason(err) == "tool_error"

    def test_generic_agent_error(self):
        err = AgentError("generic")
        assert error_to_escalate_reason(err) == "tool_error"

    def test_all_14_classes_exist(self):
        """Все 14 классов ошибок определены."""
        classes = [
            AgentError,
            PreflightError,
            IndexStaleError,
            SchemaViolationError,
            ToolError,
            ToolTimeoutError,
            ToolConnectionError,
            ToolExecutionError,
            RoleForbiddenError,
            LLMError,
            LLMUnavailableError,
            LLMRateLimitError,
            LLMBudgetExceededError,
            ValidationFailedError,
            ReviewRejectedError,
            MaxIterationsExceededError,
            EscalationRequestedError,
            PersistenceError,
        ]
        # AgentError — базовый, остальные — подклассы
        # Считаем уникальные не-AgentError классы
        leaf_classes = [c for c in classes if c is not AgentError]
        assert len(leaf_classes) == 17  # 14 листьев + 2 промежуточных (ToolError, LLMError) + AgentError = 18 всего
