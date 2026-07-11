"""validate node — детерминированный gate (parallel subgraph).

Реализация: Sprint 2.
"""

from __future__ import annotations

from typing import Any

from ..state import TaskState


async def validate_node(state: TaskState) -> dict[str, Any]:
    """Запустить 3 валидатора параллельно: bsl_ls.lint + kb.check_antipatterns + kb.check_method_availability.

    Returns:
        dict с validate_result, validation_passed, failed_checks.

    Raises:
        NotImplementedError: в Sprint 1.5 (каркас).
    """
    raise NotImplementedError("validate_node — реализация в Sprint 2")
