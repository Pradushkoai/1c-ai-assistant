"""plan node — декомпозиция задачи на подзадачи.

В Sprint 2 — упрощённая версия: создаёт одну подзадачу из описания задачи.
Полная версия с LLM supervisor — в Sprint 3.

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from parsers.models import ObjectRef

from ..logging import get_logger
from ..state import FSMState, Subtask, TaskState

log = get_logger(__name__)


async def plan_node(state: TaskState) -> dict[str, Any]:
    """Декомпозировать задачу на подзадачи.

    Sprint 2: создаёт одну подзадачу из описания задачи.
    Sprint 3: LLM supervisor для декомпозиции.

    Args:
        state: текущее состояние pipeline.

    Returns:
        dict с subtasks, plan_result, fsm_state.
    """
    log.info("plan_start", task_id=state.task_id, description=state.description[:100])

    # Sprint 2: одна подзадача
    subtask = Subtask(
        id=str(uuid4()),
        name="ГенерацияКода",
        target_module=ObjectRef(type="CommonModule", name="СгенерированныйМодуль"),
        description=state.description,
        acceptance_criteria=[
            "Код компилируется без ошибок BSL LS",
            "Код соответствует стандартам 1С",
        ],
        max_iterations=3,
    )

    plan_result = {
        "subtasks": [subtask.model_dump(mode="json")],
        "decomposition_strategy": "single",
        "rationale": "Sprint 2: single subtask (no LLM planner yet)",
    }

    log.info(
        "plan_done",
        task_id=state.task_id,
        subtask_count=1,
        strategy="single",
    )

    return {
        "subtasks": [subtask],
        "plan_result": plan_result,
        "fsm_state": FSMState.GATHERING,
    }
