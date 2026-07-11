"""Тесты для orchestrator.routers — детерминированные роутеры."""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from orchestrator.routers import (
    route_after_commit,
    route_after_retry,
    route_after_review,
    route_after_validate,
)
from orchestrator.state import FSMState, Subtask, TaskState
from parsers.models import ObjectRef


def _make_state(
    validation_passed: bool = False,
    review_passed: bool = False,
    critical_findings: int = 0,
    current_iteration: int = 0,
    max_iterations: int = 3,
    subtask_count: int = 1,
    current_subtask_idx: int = 0,
) -> TaskState:
    subtasks = [
        Subtask(
            id=f"st-{i:03d}",
            name=f"Subtask{i}",
            target_module=ObjectRef.from_string("CommonModule.Тест"),
            description=f"Subtask {i}",
            max_iterations=max_iterations,
        )
        for i in range(subtask_count)
    ]
    return TaskState(
        task_id="t1",
        description="Test",
        config_name="mini",
        config_version="1.0",
        platform_version="8.3.20",
        subtasks=subtasks,
        current_subtask_idx=current_subtask_idx,
        current_iteration=current_iteration,
        validation_passed=validation_passed,
        review_passed=review_passed,
        critical_findings=critical_findings,
    )


# ─── route_after_validate ───────────────────────────────────────────────────


class TestRouteAfterValidate:
    @pytest.mark.smoke
    def test_passed_goes_to_review(self):
        state = _make_state(validation_passed=True)
        assert route_after_validate(state) == "review"

    @pytest.mark.smoke
    def test_failed_goes_to_retry(self):
        state = _make_state(validation_passed=False)
        assert route_after_validate(state) == "retry"

    @given(passed=st.booleans())
    @settings(max_examples=30)
    def test_returns_valid_literal(self, passed: bool):
        state = _make_state(validation_passed=passed)
        result = route_after_validate(state)
        assert result in ("review", "retry")
        assert result == ("review" if passed else "retry")


# ─── route_after_review ─────────────────────────────────────────────────────


class TestRouteAfterReview:
    @pytest.mark.smoke
    def test_passed_goes_to_commit(self):
        state = _make_state(review_passed=True)
        assert route_after_review(state) == "commit"

    def test_critical_findings_3_escalates(self):
        state = _make_state(review_passed=False, critical_findings=3)
        assert route_after_review(state) == "escalate"

    def test_critical_findings_5_escalates(self):
        state = _make_state(review_passed=False, critical_findings=5)
        assert route_after_review(state) == "escalate"

    def test_max_iterations_reached_escalates(self):
        state = _make_state(
            review_passed=False,
            critical_findings=1,
            current_iteration=3,
            max_iterations=3,
        )
        assert route_after_review(state) == "escalate"

    def test_under_limits_goes_to_retry(self):
        state = _make_state(
            review_passed=False,
            critical_findings=1,
            current_iteration=1,
            max_iterations=3,
        )
        assert route_after_review(state) == "retry"

    def test_no_subtask_escalates(self):
        state = _make_state(subtask_count=1, current_subtask_idx=99)
        assert route_after_review(state) == "escalate"

    @given(
        review_passed=st.booleans(),
        critical_findings=st.integers(min_value=0, max_value=10),
        current_iteration=st.integers(min_value=0, max_value=5),
        max_iterations=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_returns_valid_literal(
        self,
        review_passed: bool,
        critical_findings: int,
        current_iteration: int,
        max_iterations: int,
    ):
        state = _make_state(
            review_passed=review_passed,
            critical_findings=critical_findings,
            current_iteration=current_iteration,
            max_iterations=max_iterations,
        )
        result = route_after_review(state)
        assert result in ("commit", "retry", "escalate")


# ─── route_after_retry ──────────────────────────────────────────────────────


class TestRouteAfterRetry:
    @pytest.mark.smoke
    def test_under_limit_goes_to_code(self):
        state = _make_state(current_iteration=1, max_iterations=3)
        assert route_after_retry(state) == "code"

    def test_at_limit_escalates(self):
        state = _make_state(current_iteration=3, max_iterations=3)
        assert route_after_retry(state) == "escalate"

    def test_over_limit_escalates(self):
        state = _make_state(current_iteration=5, max_iterations=3)
        assert route_after_retry(state) == "escalate"

    def test_no_subtask_escalates(self):
        state = _make_state(current_subtask_idx=99)
        assert route_after_retry(state) == "escalate"


# ─── route_after_commit ─────────────────────────────────────────────────────


class TestRouteAfterCommit:
    @pytest.mark.smoke
    def test_has_more_subtasks(self):
        state = _make_state(subtask_count=3, current_subtask_idx=0)
        assert route_after_commit(state) == "next_subtask"

    def test_last_subtask_ends(self):
        state = _make_state(subtask_count=1, current_subtask_idx=0)
        assert route_after_commit(state) == "end"

    def test_second_of_three(self):
        state = _make_state(subtask_count=3, current_subtask_idx=1)
        assert route_after_commit(state) == "next_subtask"

    @given(
        subtask_count=st.integers(min_value=1, max_value=10),
        current_idx=st.integers(min_value=0, max_value=9),
    )
    @settings(max_examples=30)
    def test_returns_valid_literal(self, subtask_count: int, current_idx: int):
        state = _make_state(
            subtask_count=subtask_count,
            current_subtask_idx=min(current_idx, subtask_count - 1),
        )
        result = route_after_commit(state)
        assert result in ("next_subtask", "end")
