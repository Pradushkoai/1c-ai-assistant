"""Детерминированные роутеры — НЕ LLM.

Эти функции — единственное, что решает "куда идти дальше".
LLM в Review может "рекомендовать", но финальное решение — здесь.

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from typing import Literal

from .state import TaskState


def route_after_validate(state: TaskState) -> Literal["review", "retry"]:
    """После Validate: пройти в Review, либо назад в Code (retry).

    Args:
        state: текущее состояние pipeline.

    Returns:
        'review' если validation_passed=True, иначе 'retry'.
    """
    return "review" if state.validation_passed else "retry"


def route_after_review(state: TaskState) -> Literal["commit", "retry", "escalate"]:
    """После Review: commit, retry, или escalate.

    Логика:
    - review_passed=True → commit
    - critical_findings >= 3 → escalate
    - current_iteration >= max_iterations → escalate
    - иначе → retry

    Args:
        state: текущее состояние pipeline.

    Returns:
        'commit' | 'retry' | 'escalate'
    """
    subtask = state.current_subtask
    if subtask is None:
        return "escalate"

    if state.review_passed:
        return "commit"

    if state.critical_findings >= 3:
        return "escalate"

    if state.current_iteration >= subtask.max_iterations:
        return "escalate"

    return "retry"


def route_after_retry(state: TaskState) -> Literal["code", "escalate"]:
    """После retry-узла: снова в Code, или escalate.

    Защита от бесконечных циклов.

    Args:
        state: текущее состояние pipeline.

    Returns:
        'code' если итерации остались, иначе 'escalate'.
    """
    subtask = state.current_subtask
    if subtask is None:
        return "escalate"

    if state.current_iteration >= subtask.max_iterations:
        return "escalate"

    return "code"


def route_after_commit(state: TaskState) -> Literal["next_subtask", "end"]:
    """После Commit: следующая подзадача или завершение.

    Args:
        state: текущее состояние pipeline.

    Returns:
        'next_subtask' если есть ещё подзадачи, иначе 'end'.
    """
    if state.current_subtask_idx + 1 < len(state.subtasks):
        return "next_subtask"
    return "end"
