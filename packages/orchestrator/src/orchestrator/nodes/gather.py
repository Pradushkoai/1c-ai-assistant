"""gather node — сбор контекста для подзадачи.

В Sprint 2 — упрощённая версия: возвращает пустой контекст.
Полная версия с MCP-вызовами — в Sprint 3.

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from typing import Any

from ..contracts import GatheredCode, GatheredKnowledge, GatheredMetadata, GatherResult
from ..logging import get_logger
from ..state import FSMState, TaskState

log = get_logger(__name__)


async def gather_node(state: TaskState) -> dict[str, Any]:
    """Собрать контекст: метаданные, похожий код, паттерны, availability.

    Sprint 2: пустой контекст (metadata/codebase/kb MCP — в Sprint 3-4).
    Sprint 3: параллельный fan-out к MCP-серверам.

    Args:
        state: текущее состояние pipeline.

    Returns:
        dict с gather_result, fsm_state.
    """
    subtask = state.current_subtask
    assert subtask is not None

    log.info("gather_start", task_id=state.task_id, subtask_id=subtask.id)

    # Sprint 2: пустой контекст
    gather_result = GatherResult(
        subtask_id=subtask.id,
        metadata=GatheredMetadata(target_object={}),
        code=GatheredCode(),
        knowledge=GatheredKnowledge(),
        context_summary="Контекст не собран (Sprint 2). Действуй по стандартам 1С.",
        mcp_calls_made=[],
    )

    log.info(
        "gather_done",
        task_id=state.task_id,
        subtask_id=subtask.id,
        mcp_calls=0,
    )

    return {
        "gather_result": gather_result.model_dump(mode="json"),
        "fsm_state": FSMState.CODING,
    }
