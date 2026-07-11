"""preflight node — проверка готовности данных перед запуском pipeline.

Реализация: Sprint 2.
"""

from __future__ import annotations

from typing import Any

from ..state import TaskState


async def preflight_node(state: TaskState) -> dict[str, Any]:
    """Проверить, что данные готовы (пути, индексы, freshness).

    Returns:
        dict с обновлёнными полями state.

    Raises:
        NotImplementedError: в Sprint 1.5 (каркас).
    """
    raise NotImplementedError("preflight_node — реализация в Sprint 2")
