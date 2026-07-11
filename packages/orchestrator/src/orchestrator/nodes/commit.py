"""commit node — git branch + commit + PR (simple node).

Реализация: Sprint 4.
"""

from __future__ import annotations

from typing import Any

from ..state import TaskState


async def commit_node(state: TaskState) -> dict[str, Any]:
    """Создать git branch, закоммитить код, открыть PR.

    Returns:
        dict с commit_result.

    Raises:
        NotImplementedError: в Sprint 1.5 (каркас).
    """
    raise NotImplementedError("commit_node — реализация в Sprint 4")
