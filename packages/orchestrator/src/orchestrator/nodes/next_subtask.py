"""next_subtask node — переход к следующей подзадаче.

Реализация: Sprint 3.
"""

from __future__ import annotations

from typing import Any

from ..state import TaskState


async def next_subtask_node(state: TaskState) -> dict[str, Any]:
    """Инкрементировать current_subtask_idx, сбросить iterations.

    Returns:
        dict с обновлённым current_subtask_idx и пустым iterations.

    Raises:
        NotImplementedError: в Sprint 1.5 (каркас).
    """
    raise NotImplementedError("next_subtask_node — реализация в Sprint 3")
