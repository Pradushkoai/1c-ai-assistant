"""agent/cli_commands/tool_provider.py — единая точка создания MCP servers (TD-S8-01).

ToolProvider инкапсулирует создание всех server-инстансов для DI в build_graph
и FacadeHandlers. Режим "без MCP" (я как LLM через CLI) — InProcessToolProvider
создаёт Python-объекты напрямую. Режим "с MCP" (future) — McpToolProvider
подключается к MCP servers через stdio/HTTP.

Architecture (D-2026-07-13-17):
- ``ToolProvider`` Protocol: ``get_servers()`` → dict of server instances.
- ``InProcessToolProvider`` (default): создаёт KbServer, MetadataServer, BslLsServer
  (через backend strategy), GitServer, CodebaseServer — direct Python objects.
- Все server-инстансы создаются с graceful fallback (None + warning если init failed).

См. ADR-0003 (MCP-архитектура), ADR-0005 (TOOL_GROUPS), CONCEPTUAL §1.1,
D-2026-07-13-17.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class ServerBundle:
    """Контейнер для всех server-инстансов (создаются один раз, переиспользуются).

    Атрибуты — Any (не конкретные типы), т.к. agent-слой не должен зависеть
    от mcp_servers internals (CONCEPTUAL §1.1: зависимости только вниз).
    """

    kb_server: Any = None
    bsl_ls_server: Any = None
    metadata_server: Any = None
    git_server: Any = None
    codebase_server: Any = None
    llm: Any = None
    repo_path: str | None = None
    # PathManager + ConfigRegistry (для FacadeHandlers.handle_data_status).
    path_manager: Any = None
    config_registry: Any = None


class ToolProvider:
    """Protocol для создания server-инстансов.

    Единственный метод ``create_servers()`` → ``ServerBundle``.
    Реализации: ``InProcessToolProvider`` (default), ``McpToolProvider`` (future).
    """

    def create_servers(self) -> ServerBundle:
        """Создать все server-инстансы для DI в build_graph / FacadeHandlers.

        Returns:
            ServerBundle с серверами (None если init failed — graceful fallback).
        """
        raise NotImplementedError


class InProcessToolProvider(ToolProvider):
    """Создаёт Python-объекты напрямую (режим "без MCP", default).

    Все servers — in-process: KbServer, MetadataServer, BslLsServer (через
    backend strategy TD-S8-02), GitServer. Без MCP stdio/HTTP transport.

    Для production MCP deployment — использовать ``1c-ai mcp serve`` или
    ``1c-ai serve`` (REST API). Внутри они используют тот же InProcessToolProvider.
    """

    def create_servers(self) -> ServerBundle:
        """Создать all servers с graceful fallback."""
        bundle = ServerBundle()

        # ─── KbServer ───────────────────────────────────────────────────────
        bundle.kb_server = self._try_create(
            "kb_server",
            lambda: self._create_kb_server(),
        )

        # ─── BslLsServer (backend strategy, TD-S8-02) ───────────────────────
        bundle.bsl_ls_server = self._try_create(
            "bsl_ls_server",
            lambda: self._create_bsl_ls_server(),
        )

        # ─── MetadataServer ─────────────────────────────────────────────────
        bundle.metadata_server = self._try_create(
            "metadata_server",
            lambda: self._create_metadata_server(),
        )

        # ─── GitServer ──────────────────────────────────────────────────────
        bundle.git_server = self._try_create(
            "git_server",
            lambda: self._create_git_server(),
        )

        # ─── repo_path (env 1C_AI_REPO_PATH) ────────────────────────────────
        bundle.repo_path = os.environ.get("1C_AI_REPO_PATH")

        # ─── LLM ────────────────────────────────────────────────────────────
        bundle.llm = self._try_create(
            "llm",
            lambda: self._create_llm(),
        )

        # ─── PathManager + ConfigRegistry (для data_status) ─────────────────
        bundle.path_manager = self._try_create(
            "path_manager",
            lambda: self._create_path_manager(),
        )
        if bundle.path_manager is not None:
            bundle.config_registry = self._try_create(
                "config_registry",
                lambda: self._create_config_registry(bundle.path_manager),
            )

        return bundle

    # ─── individual server factories ────────────────────────────────────────

    @staticmethod
    def _try_create(name: str, factory: Any) -> Any:
        """Try-create with graceful fallback (None + warning)."""
        try:
            return factory()
        except FileNotFoundError as exc:
            log.warning("tool_provider: %s init failed (file not found): %s", name, exc)
        except Exception as exc:  # noqa: BLE001
            log.warning("tool_provider: %s init failed: %s", name, exc)
        return None

    @staticmethod
    def _create_kb_server() -> Any:
        from mcp_servers.kb.server import KbServer

        return KbServer()

    @staticmethod
    def _create_bsl_ls_server() -> Any:
        from mcp_servers.bsl_ls.server import BslLsServer

        return BslLsServer()  # auto-backend via make_bsl_ls_backend()

    @staticmethod
    def _create_metadata_server() -> Any:
        from mcp_servers.metadata.server import MetadataServer

        return MetadataServer()

    @staticmethod
    def _create_git_server() -> Any:
        from mcp_servers.git.server import GitServer

        return GitServer()

    @staticmethod
    def _create_llm() -> Any:
        from orchestrator.llm import create_llm

        return create_llm()

    @staticmethod
    def _create_path_manager() -> Any:
        from data_layer import PathManager

        return PathManager()

    @staticmethod
    def _create_config_registry(path_manager: Any) -> Any:
        from data_layer import ConfigRegistry

        return ConfigRegistry(path_manager.config_registry_path())


def make_tool_provider() -> ToolProvider:
    """Factory: создать ToolProvider по env (default: InProcessToolProvider).

    Future: env ``1C_AI_TOOL_MODE=mcp`` → McpToolProvider (подключение к
    standalone MCP servers через stdio/HTTP). Пока — InProcessToolProvider only.

    Returns:
        ToolProvider instance.
    """
    mode = os.environ.get("1C_AI_TOOL_MODE", "in-process")
    if mode == "in-process":
        return InProcessToolProvider()
    # Future: mcp mode.
    log.warning("tool_provider: unknown mode=%s, using in-process", mode)
    return InProcessToolProvider()
