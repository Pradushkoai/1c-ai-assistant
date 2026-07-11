"""commit node — сохранение сгенерированного кода в файл.

В Sprint 2 — сохранение в файл (без git).
Полная версия с git branch + commit + PR — в Sprint 4.

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contracts import CommitResult
from ..logging import get_logger
from ..state import FSMState, TaskState

log = get_logger(__name__)


async def commit_node(state: TaskState) -> dict[str, Any]:
    """Сохранить сгенерированный код в файл.

    Sprint 2: сохранение в runtime/generated/ директорию.
    Sprint 4: git branch + commit + PR через git MCP.

    Args:
        state: текущее состояние pipeline.

    Returns:
        dict с commit_result, fsm_state.
    """
    subtask = state.current_subtask
    assert subtask is not None
    assert state.iterations, "No iterations in state"

    current_iteration = state.iterations[-1]
    code = current_iteration.code

    log.info(
        "commit_start",
        task_id=state.task_id,
        subtask_id=subtask.id,
        iteration=current_iteration.number,
    )

    # Сохраняем код в файл
    output_dir = Path("runtime/generated")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Имя файла: {subtask_id}_{iteration}.bsl
    filename = f"{subtask.id}_{current_iteration.number}.bsl"
    output_file = output_dir / filename
    output_file.write_text(code, encoding="utf-8")

    commit_result = CommitResult(
        subtask_id=subtask.id,
        branch_name=f"feature/{state.task_id[:8]}-{subtask.id[:8]}",
        commit_sha="n/a (Sprint 2: file save)",
        pr_url=None,
        pr_number=None,
        files_changed=[str(output_file)],
        diff_summary=f"Generated {code.count(chr(10)) + 1} lines of BSL code",
    )

    log.info(
        "commit_done",
        task_id=state.task_id,
        subtask_id=subtask.id,
        file=str(output_file),
        lines=code.count("\n") + 1,
    )

    return {
        "commit_result": commit_result.model_dump(mode="json"),
        "fsm_state": FSMState.DONE,
    }
