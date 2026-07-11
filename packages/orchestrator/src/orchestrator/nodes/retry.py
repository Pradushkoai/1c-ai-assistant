"""retry node — инкремент итерации, добавление constraints_reminder.

Реализация: Sprint 2.
"""

from __future__ import annotations

from typing import Any

from ..state import TaskState


async def retry_node(state: TaskState) -> dict[str, Any]:
    """Подготовить state для retry: инкремент итерации, constraints_reminder.

    Returns:
        dict с обновлённым current_iteration и constraints_reminder.

    Raises:
        NotImplementedError: в Sprint 1.5 (каркас).
    """
    raise NotImplementedError("retry_node — реализация в Sprint 2")
