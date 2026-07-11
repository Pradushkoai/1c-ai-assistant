"""escalate node — PR с меткой needs-human-review.

В Sprint 2 — логирование + сохранение кода в файл.
Полная версия с git PR — в Sprint 4.

См. ADR-0004 (Hierarchical orchestration) и ADR-0014 (Error taxonomy).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contracts import EscalateResult
from ..logging import get_logger
from ..state import FSMState, TaskState

log = get_logger(__name__)


async def escalate_node(state: TaskState) -> dict[str, Any]:
    """Создать эскалацию: сохранить код, записать лог.

    Sprint 2: сохранение кода в файл + логирование.
    Sprint 4: git branch + commit + PR с меткой needs-human-review.

    Args:
        state: текущее состояние pipeline.

    Returns:
        dict с fsm_state=ESCALATED, escalate_result.
    """
    subtask = state.current_subtask

    log.warning(
        "escalate_start",
        task_id=state.task_id,
        subtask_id=subtask.id if subtask else None,
        iteration=state.current_iteration,
    )

    # Определяем причину эскалации
    if state.current_iteration >= 3:
        reason = "max_iterations_exceeded"
    elif state.critical_findings >= 3:
        reason = "critical_findings_count"
    else:
        reason = "tool_error"

    # История итераций
    iteration_log: list[dict[str, Any]] = [
        {
            "number": it.number,
            "code_lines": it.code.count("\n") + 1,
            "failed_checks": len(it.failed_checks),
            "edit_distance": it.edit_distance_vs_prev,
        }
        for it in state.iterations
    ]

    # Сохраняем код последней итерации в файл
    if state.iterations and subtask:
        output_dir = Path("runtime/escalations")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{state.task_id}_{subtask.id}_iteration_{state.current_iteration}.bsl"
        output_file.write_text(state.iterations[-1].code, encoding="utf-8")

        log.info("escalate_code_saved", file=str(output_file))

    # Рекомендации
    suggested_actions: list[str] = []
    if reason == "max_iterations_exceeded":
        suggested_actions.append("Проверьте последние итерации — если edit distance <5%, модель топчется")
        suggested_actions.append("Возможно, нужно упростить подзадачу в Plan")
    elif reason == "critical_findings_count":
        suggested_actions.append("Проверьте findings в Review — возможно, паттерн в KB неполный")
    else:
        suggested_actions.append("Проверьте логи и state")
        suggested_actions.append("Проверьте, что все MCP-серверы запущены")

    escalate_result = EscalateResult(
        subtask_id=subtask.id if subtask else "unknown",
        reason=reason,  # type: ignore[arg-type]
        iteration_log=iteration_log,
        pr_url=None,
        suggested_actions=suggested_actions,
    )

    log.warning(
        "escalate_done",
        task_id=state.task_id,
        reason=reason,
        iterations=len(state.iterations),
    )

    return {
        "fsm_state": FSMState.ESCALATED,
        "escalate_result": escalate_result.model_dump(mode="json"),
    }
