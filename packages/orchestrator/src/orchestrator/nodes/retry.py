"""retry node — инкремент итерации, добавление constraints_reminder.

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from typing import Any

from ..logging import get_logger
from ..state import FSMState, TaskState

log = get_logger(__name__)


async def retry_node(state: TaskState) -> dict[str, Any]:
    """Подготовить state для retry: инкремент итерации, constraints_reminder.

    Извлекает failed_checks из validate_result и формирует constraints_reminder
    для следующего промпта Coder'а.

    Args:
        state: текущее состояние pipeline.

    Returns:
        dict с constraints_reminder, fsm_state.
    """
    subtask = state.current_subtask
    assert subtask is not None

    log.info(
        "retry_start",
        task_id=state.task_id,
        subtask_id=subtask.id,
        iteration=state.current_iteration,
    )

    # Формируем constraints_reminder из failed_checks
    constraints_reminder = ""
    if state.validate_result:
        validate_data = state.validate_result
        failed_checks = validate_data.get("failed_checks", [])
        if failed_checks:
            lines: list[str] = ["Исправь следующие ошибки:"]
            for check in failed_checks:
                severity = check.get("severity", "info")
                code = check.get("code", "UNKNOWN")
                line_num = check.get("line", "?")
                message = check.get("message", "")
                lines.append(f"- [{severity}] {code} (строка {line_num}): {message}")
            constraints_reminder = "\n".join(lines)

    log.info(
        "retry_done",
        task_id=state.task_id,
        subtask_id=subtask.id,
        constraints_reminder_length=len(constraints_reminder),
    )

    return {
        "constraints_reminder": constraints_reminder,
        "fsm_state": FSMState.CODING,
    }
