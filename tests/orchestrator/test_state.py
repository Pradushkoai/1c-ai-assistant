"""Тесты для orchestrator.state — TaskState, Subtask, Iteration, FSMState."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from orchestrator.state import (
    FSMState,
    Iteration,
    Subtask,
    SubtaskConstraints,
    TaskState,
)
from parsers.models import ObjectRef


# ─── FSMState ──────────────────────────────────────────────────────────────


class TestFSMState:
    @pytest.mark.smoke
    def test_all_states_present(self):
        states = list(FSMState)
        assert len(states) == 10
        assert FSMState.INIT in states
        assert FSMState.DONE in states
        assert FSMState.FAILED in states
        assert FSMState.ESCALATED in states

    def test_state_values(self):
        assert FSMState.INIT.value == "init"
        assert FSMState.PLANNING.value == "planning"
        assert FSMState.DONE.value == "done"


# ─── SubtaskConstraints ────────────────────────────────────────────────────


class TestSubtaskConstraints:
    @pytest.mark.smoke
    def test_create_defaults(self):
        c = SubtaskConstraints()
        assert c.dont_list == []
        assert c.must_list == []
        assert c.target_context == "server"

    def test_frozen(self):
        c = SubtaskConstraints(dont_list=["X"])
        with pytest.raises(ValidationError):
            c.dont_list = ["Y"]  # type: ignore[misc]

    def test_extra_forbidden(self):
        with pytest.raises(ValidationError):
            SubtaskConstraints(dont_list=["X"], bad_field="no")  # type: ignore[call-arg]


# ─── Subtask ────────────────────────────────────────────────────────────────


class TestSubtask:
    @pytest.mark.smoke
    def test_create_minimal(self, sample_subtask: Subtask):
        assert sample_subtask.id == "st-001"
        assert sample_subtask.max_iterations == 3
        assert sample_subtask.status == "pending"

    def test_frozen(self, sample_subtask: Subtask):
        with pytest.raises(ValidationError):
            sample_subtask.name = "other"  # type: ignore[misc]

    def test_with_constraints(self, sample_constraints: SubtaskConstraints):
        st_subtask = Subtask(
            id="st-002",
            name="Test",
            target_module=ObjectRef.from_string("Catalog.Товары"),
            description="Test",
            constraints=sample_constraints,
        )
        assert st_subtask.constraints is not None
        assert st_subtask.constraints.dont_list == ["Не использовать Запрос в цикле"]

    def test_max_iterations_bounds(self):
        with pytest.raises(ValidationError):
            Subtask(
                id="x",
                name="x",
                target_module=ObjectRef.from_string("Catalog.X"),
                description="x",
                max_iterations=0,
            )
        with pytest.raises(ValidationError):
            Subtask(
                id="x",
                name="x",
                target_module=ObjectRef.from_string("Catalog.X"),
                description="x",
                max_iterations=10,
            )

    def test_round_trip(self, sample_subtask: Subtask):
        dumped = sample_subtask.model_dump_json()
        restored = Subtask.model_validate_json(dumped)
        assert restored == sample_subtask


# ─── Iteration ──────────────────────────────────────────────────────────────


class TestIteration:
    @pytest.mark.smoke
    def test_create(self):
        it = Iteration(
            number=1,
            code="Процедура Т() КонецПроцедуры",
            llm_response={"model": "gpt-4"},
        )
        assert it.number == 1
        assert it.edit_distance_vs_prev == 0.0
        assert it.test_result is None

    def test_frozen(self):
        it = Iteration(number=1, code="x", llm_response={})
        with pytest.raises(ValidationError):
            it.code = "y"  # type: ignore[misc]

    def test_number_must_be_positive(self):
        with pytest.raises(ValidationError):
            Iteration(number=0, code="x", llm_response={})


# ─── TaskState ──────────────────────────────────────────────────────────────


class TestTaskState:
    @pytest.mark.smoke
    def test_create_minimal(self):
        state = TaskState(
            task_id="t1",
            description="Test",
            config_name="mini",
            config_version="1.0",
            platform_version="8.3.20",
        )
        assert state.fsm_state == FSMState.INIT
        assert state.subtasks == []
        assert state.current_iteration == 0
        assert state.validation_passed is False

    def test_frozen(self):
        state = TaskState(
            task_id="t1",
            description="Test",
            config_name="mini",
            config_version="1.0",
            platform_version="8.3.20",
        )
        with pytest.raises(ValidationError):
            state.fsm_state = FSMState.DONE  # type: ignore[misc]

    def test_model_copy_for_update(self, make_state):
        """model_copy(update={...}) — правильный способ обновить state."""
        state = make_state(fsm_state=FSMState.INIT)
        updated = state.model_copy(update={"fsm_state": FSMState.PLANNING})
        assert updated.fsm_state == FSMState.PLANNING
        assert state.fsm_state == FSMState.INIT  # оригинал не изменился

    def test_current_subtask_property(self, make_state, sample_subtask: Subtask):
        state = make_state(subtasks=[sample_subtask])
        assert state.current_subtask is not None
        assert state.current_subtask.id == "st-001"

    def test_current_subtask_none_when_done(self, make_state):
        state = make_state(current_subtask_idx=99)
        assert state.current_subtask is None

    def test_round_trip(self, make_state):
        state = make_state()
        dumped = state.model_dump_json()
        restored = TaskState.model_validate_json(dumped)
        assert restored.task_id == state.task_id
        assert restored.fsm_state == state.fsm_state

    def test_json_schema_export(self):
        schema = TaskState.model_json_schema()
        assert "properties" in schema
        assert "task_id" in schema["properties"]
        assert "subtasks" in schema["properties"]

    def test_extra_forbidden(self):
        with pytest.raises(ValidationError):
            TaskState(
                task_id="t1",
                description="Test",
                config_name="mini",
                config_version="1.0",
                platform_version="8.3.20",
                bad_field="no",  # type: ignore[call-arg]
            )


# ─── Property-based ─────────────────────────────────────────────────────────


class TestTaskStateProperty:
    @given(
        validation_passed=st.booleans(),
        review_passed=st.booleans(),
        critical_findings=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=30)
    def test_state_frozen_after_creation(
        self,
        validation_passed: bool,
        review_passed: bool,
        critical_findings: int,
    ):
        """TaskState всегда frozen — мутация невозможна."""
        state = TaskState(
            task_id="t1",
            description="Test",
            config_name="mini",
            config_version="1.0",
            platform_version="8.3.20",
            validation_passed=validation_passed,
            review_passed=review_passed,
            critical_findings=critical_findings,
        )
        with pytest.raises(ValidationError):
            state.validation_passed = not validation_passed  # type: ignore[misc]
