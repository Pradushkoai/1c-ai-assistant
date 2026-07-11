"""Конструирование _next_action для каждого lifecycle tool'а.

См. ADR-0013 (Agent-Facade — 7 lifecycle tools).
"""

from __future__ import annotations

from .contracts import NextAction


def after_plan(plan_id: str, first_subtask_id: str | None) -> NextAction:
    """next_action после plan — gather."""
    if first_subtask_id:
        return NextAction(
            tool="gather",
            args={"plan_id": plan_id, "subtask_id": first_subtask_id},
            why="Собрать контекст для первой подзадачи из плана",
        )
    return NextAction(
        tool="data_status",
        args={},
        why="Plan пустой — проверьте данные",
    )


def after_gather(plan_id: str, subtask_id: str) -> NextAction:
    """next_action после gather — generate."""
    return NextAction(
        tool="generate",
        args={"plan_id": plan_id, "subtask_id": subtask_id, "iteration": 1},
        why="Контекст собран — можно генерировать код",
    )


def after_generate(plan_id: str, subtask_id: str, iteration: int) -> NextAction:
    """next_action после generate — validate."""
    artifact_id = f"{subtask_id}#{iteration}"
    return NextAction(
        tool="validate",
        args={"artifact_id": artifact_id},
        why="Код сгенерирован — проверить через BSL LS + антипаттерны",
    )


def after_validate(plan_id: str, subtask_id: str, iteration: int, passed: bool) -> NextAction:
    """next_action после validate — review или generate (retry)."""
    if passed:
        artifact_id = f"{subtask_id}#{iteration}"
        return NextAction(
            tool="review",
            args={"artifact_id": artifact_id},
            why="Код прошёл детерминированную валидацию — ревью LLM",
        )
    return NextAction(
        tool="generate",
        args={
            "plan_id": plan_id,
            "subtask_id": subtask_id,
            "iteration": iteration + 1,
        },
        why="Валидация не прошла — retry с конкретными failed_checks в фидбеке",
    )


def after_review(
    plan_id: str,
    subtask_id: str,
    iteration: int,
    decision: str,
    next_subtask_id: str | None = None,
) -> NextAction:
    """next_action после review — commit/generate/data_status."""
    if decision == "proceed":
        if next_subtask_id:
            return NextAction(
                tool="gather",
                args={"plan_id": plan_id, "subtask_id": next_subtask_id},
                why="Подзадача прошла ревью — следующая подзадача",
            )
        return NextAction(
            tool="data_status",
            args={},
            why="Все подзадачи выполнены — можно проверять итог и коммитить",
        )
    if decision == "retry":
        return NextAction(
            tool="generate",
            args={
                "plan_id": plan_id,
                "subtask_id": subtask_id,
                "iteration": iteration + 1,
            },
            why="Рецензент нашёл замечания — retry",
        )
    return NextAction(
        tool="data_status",
        args={},
        why="Эскалация к человеку — пайплайн остановлен",
    )
