"""plan node — декомпозиция задачи на подзадачи (mini-supervisor subgraph).

Реализация: Sprint 3.
"""

from __future__ import annotations

from typing import Any

from ..state import TaskState


async def plan_node(state: TaskState) -> dict[str, Any]:
    """Декомпозировать задачу на подзадачи.

    Returns:
        dict с subtasks и plan_result.

    Raises:
        NotImplementedError: в Sprint 1.5 (каркас).
    """
    raise NotImplementedError("plan_node — реализация в Sprint 3")
