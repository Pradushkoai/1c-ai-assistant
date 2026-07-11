"""review node — LLM-рецензент (mini-supervisor subgraph).

Реализация: Sprint 3.
"""

from __future__ import annotations

from typing import Any

from ..state import TaskState


async def review_node(state: TaskState) -> dict[str, Any]:
    """LLM-рецензент: проверить код и решить proceed/retry/escalate.

    Returns:
        dict с review_result, review_passed, critical_findings.

    Raises:
        NotImplementedError: в Sprint 1.5 (каркас).
    """
    raise NotImplementedError("review_node — реализация в Sprint 3")
