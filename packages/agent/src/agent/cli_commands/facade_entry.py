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

    # ─── kb_server (опц.) ───────────────────────────────────────────────────
    kb_server = _try_create_kb_server()

    # ─── bsl_ls_server (опц.) ───────────────────────────────────────────────
    bsl_ls_server = _try_create_bsl_ls_server()

    # ─── metadata_server (опц., Stage 4 TD-S6-01) ───────────────────────────
    metadata_server = _try_create_metadata_server()

    # ─── git_server + repo_path (опц., Stage 4 TD-S6-02) ────────────────────
    git_server = _try_create_git_server()
    repo_path = _get_repo_path()

    # ─── llm (опц.) ─────────────────────────────────────────────────────────
    llm = _try_create_llm()

    # ─── path_manager + config_registry (для data_status) ───────────────────
    path_manager = _try_create_path_manager()
    config_registry = _try_create_config_registry(path_manager)

    return FacadeHandlers(
        state_factory=state_factory,
        node_plan=plan_node,
        node_gather=gather_node,
        node_code=code_node,
        node_validate=validate_node,
        node_review=review_node,
        node_commit=commit_node,
        kb_server=kb_server,
        bsl_ls_server=bsl_ls_server,
        llm=llm,
        path_manager=path_manager,
        config_registry=config_registry,
        metadata_server=metadata_server,
        git_server=git_server,
        repo_path=repo_path,
    )


def _try_create_kb_server() -> Any:
    """Создать KbServer, если доступно."""
    try:
        from mcp_servers.kb.server import KbServer

        return KbServer()
    except Exception as exc:  # noqa: BLE001
        log.warning("facade_entry: kb_server init failed: %s", exc)
        return None


def _try_create_bsl_ls_server() -> Any:
    """Создать BslLsServer, если доступно."""
    try:
        from mcp_servers.bsl_ls.server import BslLsServer

        return BslLsServer()
    except Exception as exc:  # noqa: BLE001
        log.warning("facade_entry: bsl_ls_server init failed: %s", exc)
        return None


def _try_create_metadata_server() -> Any:
    """Создать MetadataServer, если доступно (Stage 4 TD-S6-01)."""
    try:
        from mcp_servers.metadata.server import MetadataServer

        return MetadataServer()
    except FileNotFoundError as exc:
        log.warning("facade_entry: metadata_server init failed (paths.env?): %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("facade_entry: metadata_server init failed: %s", exc)
        return None


def _try_create_git_server() -> Any:
    """Создать GitServer, если доступно (Stage 4 TD-S6-02)."""
    try:
        from mcp_servers.git.server import GitServer

        return GitServer()
    except Exception as exc:  # noqa: BLE001
        log.warning("facade_entry: git_server init failed: %s", exc)
        return None


def _get_repo_path() -> str | None:
    """Путь к git-репозиторию для коммитов (env 1C_AI_REPO_PATH)."""
    import os

    return os.environ.get("1C_AI_REPO_PATH")


def _try_create_llm() -> Any:
    """Создать LLM, если доступно."""
    try:
        from orchestrator.llm import create_llm

        return create_llm()
    except Exception as exc:  # noqa: BLE001
        log.warning("facade_entry: llm init failed: %s", exc)
        return None


def _try_create_path_manager() -> Any:
    """Создать PathManager, если paths.env существует."""
    try:
        from data_layer import PathManager

        return PathManager()
    except FileNotFoundError as exc:
        log.warning("facade_entry: path_manager init failed (paths.env?): %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("facade_entry: path_manager init failed: %s", exc)
        return None


def _try_create_config_registry(path_manager: Any) -> Any:
    """Создать ConfigRegistry, если path_manager задан."""
    if path_manager is None:
        return None
    try:
        from data_layer import ConfigRegistry

        return ConfigRegistry(path_manager.config_registry_path())
    except Exception as exc:  # noqa: BLE001
        log.warning("facade_entry: config_registry init failed: %s", exc)
        return None
