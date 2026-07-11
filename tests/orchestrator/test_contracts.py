"""Тесты для orchestrator.contracts — 10 Result типов узлов."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.contracts import (
    CodeResult,
    CommitResult,
    EscalateResult,
    GatherResult,
    GatheredCode,
    GatheredKnowledge,
    GatheredMetadata,
    PlanResult,
    ReviewFinding,
    ReviewResult,
    ValidationFinding,
    ValidateResult,
)
from parsers.models import ObjectRef


# ─── PlanResult ─────────────────────────────────────────────────────────────


class TestPlanResult:
    @pytest.mark.smoke
    def test_create(self):
        result = PlanResult(
            subtasks=[],
            decomposition_strategy="single",
            rationale="simple task",
        )
        assert result.decomposition_strategy == "single"
        assert result.subtasks == []

    def test_frozen(self):
        result = PlanResult(
            subtasks=[],
            decomposition_strategy="feature",
            rationale="test",
        )
        with pytest.raises(ValidationError):
            result.rationale = "other"  # type: ignore[misc]

    def test_json_schema(self):
        schema = PlanResult.model_json_schema()
        assert "properties" in schema


# ─── GatherResult ───────────────────────────────────────────────────────────


class TestGatherResult:
    def test_create(self):
        result = GatherResult(
            subtask_id="st-001",
            metadata=GatheredMetadata(target_object={"name": "Test"}),
            code=GatheredCode(),
            knowledge=GatheredKnowledge(),
            context_summary="Summary text",
        )
        assert result.subtask_id == "st-001"
        assert result.context_summary == "Summary text"

    def test_with_mcp_calls(self):
        result = GatherResult(
            subtask_id="st-001",
            metadata=GatheredMetadata(target_object={}),
            code=GatheredCode(),
            knowledge=GatheredKnowledge(),
            context_summary="",
            mcp_calls_made=["metadata.get_metadata", "codebase.semantic_search"],
        )
        assert len(result.mcp_calls_made) == 2


# ─── CodeResult ─────────────────────────────────────────────────────────────


class TestCodeResult:
    @pytest.mark.smoke
    def test_create(self):
        result = CodeResult(
            subtask_id="st-001",
            iteration_number=1,
            code="Процедура Т() КонецПроцедуры",
            target_module=ObjectRef.from_string("CommonModule.Тест"),
        )
        assert result.iteration_number == 1
        assert result.structured_output_valid is True

    def test_iteration_must_be_positive(self):
        with pytest.raises(ValidationError):
            CodeResult(
                subtask_id="st-001",
                iteration_number=0,
                code="x",
                target_module=ObjectRef.from_string("Catalog.X"),
            )


# ─── ValidateResult ─────────────────────────────────────────────────────────


class TestValidateResult:
    @pytest.mark.smoke
    def test_create_passed(self):
        result = ValidateResult(
            subtask_id="st-001",
            iteration_number=1,
            findings=[],
            passed=True,
            severity_breakdown={"critical": 0, "warning": 0, "info": 0},
            failed_checks=[],
        )
        assert result.passed is True

    def test_create_failed(self):
        finding = ValidationFinding(
            severity="critical",
            code="BSL-WS-001",
            message="error",
            source="bsl_ls",
        )
        result = ValidateResult(
            subtask_id="st-001",
            iteration_number=1,
            findings=[finding],
            passed=False,
            severity_breakdown={"critical": 1, "warning": 0, "info": 0},
            failed_checks=[{"code": "BSL-WS-001", "line": 5}],
        )
        assert result.passed is False
        assert len(result.findings) == 1


# ─── ReviewResult ───────────────────────────────────────────────────────────


class TestReviewResult:
    @pytest.mark.smoke
    def test_create_proceed(self):
        result = ReviewResult(
            subtask_id="st-001",
            iteration_number=1,
            findings=[],
            decision="proceed",
            rationale="good code",
            critical_findings=0,
            passed=True,
        )
        assert result.decision == "proceed"
        assert result.passed is True

    def test_create_retry(self):
        result = ReviewResult(
            subtask_id="st-001",
            iteration_number=1,
            findings=[],
            decision="retry",
            rationale="needs fixes",
            critical_findings=1,
            passed=False,
        )
        assert result.decision == "retry"
        assert result.passed is False


# ─── CommitResult ───────────────────────────────────────────────────────────


class TestCommitResult:
    @pytest.mark.smoke
    def test_create(self):
        result = CommitResult(
            subtask_id="st-001",
            branch_name="feature/test",
            commit_sha="abc123",
            files_changed=["Module.bsl"],
            diff_summary="1 file changed",
        )
        assert result.pr_url is None
        assert result.commit_sha == "abc123"


# ─── EscalateResult ─────────────────────────────────────────────────────────


class TestEscalateResult:
    @pytest.mark.smoke
    def test_create(self):
        result = EscalateResult(
            subtask_id="st-001",
            reason="max_iterations_exceeded",
            iteration_log=[],
        )
        assert result.reason == "max_iterations_exceeded"
        assert result.pr_url is None

    def test_with_suggested_actions(self):
        result = EscalateResult(
            subtask_id="st-001",
            reason="tool_error",
            iteration_log=[],
            suggested_actions=["Check BSL LS container", "Verify network"],
        )
        assert len(result.suggested_actions) == 2


# ─── JSON Schema export для всех ────────────────────────────────────────────


class TestJsonSchemaExport:
    @pytest.mark.smoke
    @pytest.mark.parametrize(
        "model_class",
        [
            PlanResult,
            GatherResult,
            CodeResult,
            ValidateResult,
            ReviewResult,
            CommitResult,
            EscalateResult,
        ],
    )
    def test_json_schema(self, model_class):
        schema = model_class.model_json_schema()
        assert isinstance(schema, dict)
