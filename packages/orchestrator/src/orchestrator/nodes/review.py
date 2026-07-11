"""review node — LLM-рецензент (mini-supervisor subgraph).

В Sprint 2 — упрощённая версия: auto-proceed если validation passed.
Полная версия с LLM review — в Sprint 3.

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from typing import Any

from ..contracts import ReviewResult
from ..logging import get_logger
from ..state import FSMState, TaskState

log = get_logger(__name__)


async def review_node(state: TaskState) -> dict[str, Any]:
    """LLM-рецензент: проверить код и решить proceed/retry/escalate.

    Sprint 2: auto-proceed если validation_passed=True, иначе retry.
    Sprint 3: LLM review с антипаттернами и паттернами.

    Args:
        state: текущее состояние pipeline.

    Returns:
        dict с review_result, review_passed, critical_findings, fsm_state.
    """
    subtask = state.current_subtask
    assert subtask is not None
    assert state.iterations, "No iterations in state"

    current_iteration = state.iterations[-1]

    log.info(
        "review_start",
        task_id=state.task_id,
        subtask_id=subtask.id,
        iteration=current_iteration.number,
    )

    # Sprint 2: auto-proceed если validation passed
    if state.validation_passed:
        decision: str = "proceed"
        rationale = "Sprint 2: auto-proceed (validation passed, no LLM review)"
        review_passed = True
        critical_findings = 0
    else:
        # Validation failed — retry
        decision = "retry"
        rationale = "Sprint 2: auto-retry (validation failed)"
        review_passed = False
        critical_findings = 1

    review_result = ReviewResult(
        subtask_id=subtask.id,
        iteration_number=current_iteration.number,
        findings=[],
        decision=decision,  # type: ignore[arg-type]
        rationale=rationale,
        critical_findings=critical_findings,
        passed=review_passed,
    )

    log.info(
        "review_done",
        task_id=state.task_id,
        subtask_id=subtask.id,
        iteration=current_iteration.number,
        decision=decision,
    )

    return {
        "review_result": review_result.model_dump(mode="json"),
        "review_passed": review_passed,
        "critical_findings": critical_findings,
        "fsm_state": FSMState.COMMITTING if review_passed else FSMState.CODING,
    }
