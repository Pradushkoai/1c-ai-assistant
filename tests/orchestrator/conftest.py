"""tests/orchestrator/conftest.py — fixtures для тестов orchestrator."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.state import (
    FSMState,
    Subtask,
    SubtaskConstraints,
    TaskState,
)
from parsers.models import ObjectRef


@pytest.fixture
def sample_subtask() -> Subtask:
    """Типовая подзадача для тестов."""
    return Subtask(
        id="st-001",
        name="ОбработкаПроведения",
        target_module=ObjectRef.from_string("Document.Продажа"),
        description="Добавить обработку проведения",
        acceptance_criteria=["Код компилируется", "Движения записываются"],
        max_iterations=3,
    )


@pytest.fixture
def sample_constraints() -> SubtaskConstraints:
    """Типовые ограничения подзадачи."""
    return SubtaskConstraints(
        dont_list=["Не использовать Запрос в цикле"],
        must_list=["Обернуть в транзакцию"],
        available_modules=["ОбщегоНазначения"],
        target_context="server",
    )


@pytest.fixture
def make_state():
    """Фабрика для создания TaskState с заданными параметрами."""

    def _make(
        validation_passed: bool = False,
        review_passed: bool = False,
        critical_findings: int = 0,
        current_iteration: int = 0,
        max_iterations: int = 3,
        subtasks: list[Subtask] | None = None,
        current_subtask_idx: int = 0,
        fsm_state: FSMState = FSMState.INIT,
    ) -> TaskState:
        if subtasks is None:
            subtasks = [
                Subtask(
                    id="st-001",
                    name="Test",
                    target_module=ObjectRef.from_string("CommonModule.Тест"),
                    description="Test subtask",
                    max_iterations=max_iterations,
                )
            ]
        return TaskState(
            task_id="task-001",
            description="Test task",
            config_name="mini",
            config_version="1.0",
            platform_version="8.3.20",
            subtasks=subtasks,
            current_subtask_idx=current_subtask_idx,
            current_iteration=current_iteration,
            fsm_state=fsm_state,
            validation_passed=validation_passed,
            review_passed=review_passed,
            critical_findings=critical_findings,
        )

    return _make
