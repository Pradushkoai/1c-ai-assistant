"""next_subtask node — переход к следующей подзадаче.

Сбрасывает iterations и constraints_reminder для новой подзадачи.

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from typing import Any

from ..logging import get_logger
from ..state import FSMState, TaskState

log = get_logger(__name__)


async def next_subtask_node(state: TaskState) -> dict[str, Any]:
    """Инкрементировать current_subtask_idx, сбросить iterations.

    Args:
        state: текущее состояние pipeline.

    Returns:
        dict с current_subtask_idx, iterations, constraints_reminder, fsm_state.
    """
    new_idx = state.current_subtask_idx + 1

    log.info(
        "next_subtask",
        task_id=state.task_id,
        old_idx=state.current_subtask_idx,
        new_idx=new_idx,
    )

    return {
        "current_subtask_idx": new_idx,
        "iterations": [],  # сброс для новой подзадачи
        "current_iteration": 0,
        "constraints_reminder": "",  # сброс
        "validation_passed": False,
        "review_passed": False,
        "critical_findings": 0,
        "fsm_state": FSMState.GATHERING,
    }
