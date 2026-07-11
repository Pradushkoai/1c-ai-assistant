"""gather node — сбор контекста для подзадачи (mini-supervisor subgraph).

Реализация: Sprint 3.
"""

from __future__ import annotations

from typing import Any

from ..state import TaskState


async def gather_node(state: TaskState) -> dict[str, Any]:
    """Собрать контекст: метаданные, похожий код, паттерны, availability.

    Returns:
        dict с gather_result.

    Raises:
        NotImplementedError: в Sprint 1.5 (каркас).
    """
    raise NotImplementedError("gather_node — реализация в Sprint 3")
