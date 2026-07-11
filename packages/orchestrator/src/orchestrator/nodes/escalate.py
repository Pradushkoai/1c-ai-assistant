"""escalate node — PR с меткой needs-human-review.

Реализация: Sprint 2.
"""

from __future__ import annotations

from typing import Any

from ..state import TaskState


async def escalate_node(state: TaskState) -> dict[str, Any]:
    """Создать PR с меткой needs-human-review и историей итераций.

    Returns:
        dict с fsm_state=ESCALATED и escalate_result.

    Raises:
        NotImplementedError: в Sprint 1.5 (каркас).
    """
    raise NotImplementedError("escalate_node — реализация в Sprint 2")
