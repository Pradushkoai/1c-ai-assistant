"""PersistenceManager — управление checkpoint'ами для LangGraph.

В Sprint 1.5 (каркас) — stub с MemorySaver.
В Sprint 4 — PostgresSaver для production.

См. ADR-0014 (Error taxonomy + PostgresSaver).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from .errors import PersistenceError

# Type alias для checkpointer — LangGraph BaseCheckpointSaver (generic)
# Используем Any для избежания type-arg ошибок в mypy
CheckpointerType = Any

log = logging.getLogger(__name__)


class PersistenceManager:
    """Управление checkpoint store для LangGraph.

    В Sprint 1.5 — возвращает MemorySaver (in-memory, без persistence).
    В Sprint 4 — будет поддерживать PostgresSaver через DSN.

    Usage:
        async with PersistenceManager() as pm:
            checkpointer = pm.get_checkpointer()
            # graph = build_graph(checkpointer=checkpointer)
    """

    def __init__(self, dsn: str | None = None) -> None:
        """Инициализация.

        Args:
            dsn: PostgreSQL DSN для PostgresSaver. Если None — MemorySaver.
        """
        self.dsn = dsn
        self._checkpointer: CheckpointerType = None

    async def __aenter__(self) -> PersistenceManager:
        """Вход в context manager — инициализация checkpointer."""
        if self.dsn:
            # Sprint 4: PostgresSaver
            try:
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

                self._checkpointer = AsyncPostgresSaver.from_conn_string(self.dsn)
                # setup() создаёт таблицы — будет реализовано в Sprint 4
                log.info("PostgresSaver initialized (DSN: %s)", _mask_dsn(self.dsn))
            except ImportError:
                log.warning("langgraph-checkpoint-postgres not installed, using MemorySaver")
                self._checkpointer = self._create_memory_saver()
            except Exception as exc:
                raise PersistenceError(
                    f"Cannot connect to Postgres: {exc}",
                    details={"dsn": _mask_dsn(self.dsn)},
                ) from exc
        else:
            self._checkpointer = self._create_memory_saver()
            log.info("MemorySaver initialized (no persistence)")
        return self

    async def __aexit__(self, *args: object) -> None:
        """Выход из context manager — cleanup."""
        self._checkpointer = None

    def get_checkpointer(self) -> CheckpointerType:
        """Получить checkpointer для передачи в build_graph().

        Returns:
            BaseCheckpointSaver (MemorySaver или PostgresSaver).

        Raises:
            PersistenceError: если __aenter__ не был вызван.
        """
        if self._checkpointer is None:
            raise PersistenceError("PersistenceManager not entered — use 'async with'")
        return self._checkpointer

    @staticmethod
    def _create_memory_saver() -> CheckpointerType:
        """Создать MemorySaver (in-memory, без persistence)."""
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()


def _mask_dsn(dsn: str) -> str:
    """Скрыть пароль в DSN для логов.

    Args:
        dsn: строка подключения вида postgresql://user:password@host:port/db.

    Returns:
        DSN с заменённым паролем на '***'.
    """
    if "@" in dsn and "://" in dsn:
        prefix, _, rest = dsn.partition("://")
        creds, _, host_part = rest.partition("@")
        if ":" in creds:
            user, _, _ = creds.partition(":")
            return f"{prefix}://{user}:***@{host_part}"
    return dsn


@asynccontextmanager
async def create_persistence_manager(
    dsn: str | None = None,
) -> AsyncIterator[PersistenceManager]:
    """Удобная фабрика для создания PersistenceManager.

    Args:
        dsn: PostgreSQL DSN или None для MemorySaver.

    Yields:
        PersistenceManager.
    """
    pm = PersistenceManager(dsn=dsn)
    async with pm:
        yield pm
