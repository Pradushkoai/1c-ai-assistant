"""preflight node — проверка готовности данных перед запуском pipeline.

Проверяет:
- PathManager.validate() — директории существуют
- freshness_check() — индексы свежие

См. ADR-0009 (Pipeline contracts) и ADR-0008 (PathManager).
"""

from __future__ import annotations

from typing import Any

from data_layer import PathManager

from ..errors import IndexStaleError, PreflightError
from ..logging import get_logger
from ..state import FSMState, TaskState

log = get_logger(__name__)


async def preflight_node(state: TaskState) -> dict[str, Any]:
    """Проверить, что данные готовы (пути, индексы, freshness).

    Args:
        state: текущее состояние pipeline.

    Returns:
        dict с обновлённым fsm_state.

    Raises:
        PreflightError: если директории отсутствуют.
        IndexStaleError: если индексы устарели.
    """
    log.info("preflight_start", task_id=state.task_id, config=state.config_name)

    pm = PathManager()

    # 1. Проверка директорий
    validation = pm.validate()
    missing = [k for k, v in validation.items() if not v]
    if missing:
        log.error("preflight_failed", missing=missing)
        raise PreflightError(
            f"Missing paths: {missing}. Run: 1c-ai init",
            details={"missing": missing},
        )

    # 2. Проверка свежести индексов
    # Внимание: проверяем только unified_metadata, так как api_reference,
    # call_graph, dependency_graph строятся в других спринтах.
    freshness = pm.freshness_check(state.config_name, state.config_version)
    stale = [k for k, v in freshness.items() if not v and k == "unified_metadata"]
    if stale:
        log.warning("preflight_stale_indexes", stale=stale)
        raise IndexStaleError(
            f"Stale indexes: {stale}. Run: 1c-ai config build --name {state.config_name} --force",
            details={"stale": stale},
        )

    log.info("preflight_passed", task_id=state.task_id)
    return {
        "fsm_state": FSMState.PLANNING,
    }
