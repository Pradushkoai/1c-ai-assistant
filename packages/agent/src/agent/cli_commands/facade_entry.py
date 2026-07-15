"""agent/cli_commands/facade_entry.py — сборка FacadeHandlers с DI (TD-S5-02).

Agent-слой собирает FacadeHandlers с реальными зависимостями:
- state_factory → TaskState (orchestrator.state)
- node_* → orchestrator.nodes.* (plan/gather/code/validate/review/commit)
- kb_server, bsl_ls_server, llm, path_manager, config_registry

Это единственное место, где mcp_servers.facade встречается с orchestrator
(CONCEPTUAL.md §1.1: agent может импортировать откуда угодно).

См. ADR-0013 (Agent-Facade), D-2026-07-13-07.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp_servers.facade import FacadeHandlers

log = logging.getLogger(__name__)


def create_facade_handlers() -> FacadeHandlers:
    """Создать FacadeHandlers с DI из orchestrator + data_layer + mcp_servers.

    Все зависимости создаются лениво (в try/except) — если что-то недоступно
    (например, BSL LS контейнер не запущен), handler деградирует с warning.

    Returns:
        FacadeHandlers с заполненными node_* / state_factory / servers.
    """
    # ─── state_factory → TaskState ──────────────────────────────────────────
    from orchestrator.state import FSMState, TaskState

    def state_factory(
        task_id: str,
        description: str,
        config_name: str,
        config_version: str,
        platform_version: str,
        fsm_state: str = "planning",
    ) -> TaskState:
        return TaskState(
            task_id=task_id,
            description=description,
            config_name=config_name,
            config_version=config_version,
            platform_version=platform_version,
            fsm_state=FSMState(fsm_state),
        )

    # ─── node callables (DI из orchestrator.nodes) ──────────────────────────
    from orchestrator.nodes import (
        code_node,
        commit_node,
        gather_node,
        plan_node,
        review_node,
        validate_node,
    )

    # ─── Stage 6 (TD-S8-01): ToolProvider — единая точка создания servers ──
    from .tool_provider import make_tool_provider

    provider = make_tool_provider()
    servers = provider.create_servers()

    # ─── state_store (Stage 5 TD-S7-01, survival-restart) ───────────────────
    # PersistenceManager + FacadeStateStore. Если DATABASE_URL задан — PostgresSaver
    # (state переживает restart). Иначе — in-memory fallback.
    state_store = _try_create_state_store()

    return FacadeHandlers(
        state_factory=state_factory,
        node_plan=plan_node,
        node_gather=gather_node,
        node_code=code_node,
        node_validate=validate_node,
        node_review=review_node,
        node_commit=commit_node,
        state_store=state_store,
        kb_server=servers.kb_server,
        bsl_ls_server=servers.bsl_ls_server,
        llm=servers.llm,
        path_manager=servers.path_manager,
        config_registry=servers.config_registry,
        metadata_server=servers.metadata_server,
        git_server=servers.git_server,
        repo_path=servers.repo_path,
    )


def _try_create_state_store() -> Any:
    """Создать FacadeStateStore с PersistenceManager (Stage 5 TD-S7-01).

    PersistenceManager — async context manager. Для MCP stdio server (долгоживущий
    процесс) открываем connection один раз через asyncio.run() и держим открытым.
    Если DATABASE_URL не задан — FacadeStateStore с in-memory fallback.

    Returns:
        FacadeStateStore (persistent если DATABASE_URL задан, иначе in-memory).
    """
    import os

    # Если DATABASE_URL не задан — in-memory fallback (state не переживает restart).
    if not os.environ.get("DATABASE_URL"):
        log.info("facade_entry: no DATABASE_URL, using in-memory FacadeStateStore")
        from mcp_servers.facade import FacadeStateStore

        try:
            from orchestrator.state import TaskState

            return FacadeStateStore(state_class=TaskState)
        except ImportError:
            return FacadeStateStore()

    try:
        from mcp_servers.facade import FacadeStateStore
        from orchestrator.state import TaskState

        # Открываем PersistenceManager (async) через asyncio.run.
        # Connection держится открытым на lifecycle процесса.
        pm = _open_persistence_manager_sync()
        checkpointer = pm.get_checkpointer()
        log.info("facade_entry: FacadeStateStore with PostgresSaver (persistent)")
        return FacadeStateStore(
            checkpointer=checkpointer,
            is_postgres=True,
            state_class=TaskState,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("facade_entry: state_store init failed, using in-memory: %s", exc)
        from mcp_servers.facade import FacadeStateStore

        # In-memory fallback — тоже с state_class=TaskState (если доступен).
        try:
            from orchestrator.state import TaskState

            return FacadeStateStore(state_class=TaskState)
        except ImportError:
            return FacadeStateStore()


def _open_persistence_manager_sync() -> Any:
    """Открыть PersistenceManager синхронно (через asyncio.run) и удерживать.

    Для MCP stdio server — один долгоживущий процесс, connection открывается
    один раз. Для CLI команд (generate) — PersistenceManager открывается в
    asyncio.run(_run_pipeline) отдельно (там свой lifecycle).

    Returns:
        PersistenceManager (войденный, с активным connection).
    """
    import asyncio

    from orchestrator.persistence import PersistenceManager

    async def _open() -> Any:
        pm = PersistenceManager.from_env()
        await pm.__aenter__()
        return pm

    return asyncio.run(_open())
