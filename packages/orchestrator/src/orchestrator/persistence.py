"""PersistenceManager — управление checkpoint'ами для LangGraph.

Production (DATABASE_URL задан): ``AsyncPostgresSaver`` — LangGraph checkpoints
в Postgres. ``setup()`` создаёт checkpoint-таблицы идемпотентно (LangGraph сам
управляет их схемой через внутренний ``MIGRATIONS`` список — см. ADR-0018,
D-2026-07-13-05). Рестарт контейнера не теряет state.

Tests/dev (нет DSN): ``MemorySaver`` — in-memory, без persistence.

См. ADR-0014 (Error taxonomy + PostgresSaver), ADR-0018 (migration strategy),
ADR-0015 (3-container deployment), D-2026-07-13-04.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from .errors import PersistenceError

# Type alias для checkpointer — LangGraph BaseCheckpointSaver (generic).
# Any — чтобы не тащить generic-параметры LangGraph в mypy (TD-011-стиль).
CheckpointerType = Any

log = logging.getLogger(__name__)


class PersistenceManager:
    """Управление checkpoint store для LangGraph.

    Async context manager. При входе с DSN инициализирует ``AsyncPostgresSaver``
    и вызывает ``setup()`` (идемпотентное создание checkpoint-таблиц). Без DSN —
    ``MemorySaver``. При отсутствии ``langgraph-checkpoint-postgres`` — graceful
    fallback на ``MemorySaver`` (с warning). При ошибке подключения —
    ``PersistenceError`` (ABORT).

    Usage::

        async with PersistenceManager.from_env() as pm:
            checkpointer = pm.get_checkpointer()
            graph = build_graph(checkpointer=checkpointer)
            ...
    """

    def __init__(self, dsn: str | None = None) -> None:
        """Инициализация.

        Args:
            dsn: PostgreSQL DSN для PostgresSaver. ``None`` → MemorySaver.
        """
        self.dsn = dsn
        self._checkpointer: CheckpointerType = None
        # Удерживаем async context manager AsyncPostgresSaver.from_conn_string,
        # чтобы корректно закрыть connection в __aexit__.
        self._saver_cm: Any = None
        self._is_postgres = False

    @classmethod
    def from_env(cls, dsn_env_var: str = "DATABASE_URL") -> PersistenceManager:
        """Создать PersistenceManager из переменной окружения.

        Args:
            dsn_env_var: имя env-переменной с PostgreSQL DSN
                (по умолчанию ``DATABASE_URL``).

        Returns:
            PersistenceManager (``dsn=None`` если переменная не задана → MemorySaver).
        """
        dsn = os.environ.get(dsn_env_var) or None
        return cls(dsn=dsn)

    async def __aenter__(self) -> PersistenceManager:
        """Вход в context manager — инициализация checkpointer."""
        if not self.dsn:
            self._checkpointer = self._create_memory_saver()
            log.info("MemorySaver initialized (no persistence)")
            return self

        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        except ImportError:
            log.warning("langgraph-checkpoint-postgres not installed; falling back to MemorySaver")
            self._checkpointer = self._create_memory_saver()
            return self

        try:
            # from_conn_string — @asynccontextmanager (AsyncIterator[AsyncPostgresSaver]).
            # Удерживаем CM, чтобы закрыть connection в __aexit__.
            self._saver_cm = AsyncPostgresSaver.from_conn_string(self.dsn)
            saver = await self._saver_cm.__aenter__()
            # setup() — корутина; идемпотентно создаёт checkpoint-таблицы
            # (checkpoints, checkpoint_blobs, checkpoint_writes, checkpoint_migrations).
            await saver.setup()
            self._checkpointer = saver
            self._is_postgres = True
            log.info("PostgresSaver initialized (DSN: %s)", _mask_dsn(self.dsn))
        except Exception as exc:
            # Гарантируем освобождение connection при частичном падении.
            await self._close_saver_cm()
            raise PersistenceError(
                f"Cannot initialize PostgresSaver: {exc}",
                details={"dsn": _mask_dsn(self.dsn)},
            ) from exc
        return self

    async def __aexit__(self, *args: object) -> None:
        """Выход из context manager — cleanup connection."""
        await self._close_saver_cm()
        self._checkpointer = None
        self._is_postgres = False

    async def _close_saver_cm(self) -> None:
        """Безопасно закрыть удерживаемый async context manager PostgresSaver."""
        if self._saver_cm is not None:
            try:
                await self._saver_cm.__aexit__(None, None, None)
            except Exception as exc:  # noqa: BLE001
                log.warning("error closing PostgresSaver connection: %s", exc)
            finally:
                self._saver_cm = None

    def get_checkpointer(self) -> CheckpointerType:
        """Получить checkpointer для передачи в ``build_graph()``.

        Returns:
            BaseCheckpointSaver (MemorySaver или AsyncPostgresSaver).

        Raises:
            PersistenceError: если ``__aenter__`` не был вызван.
        """
        if self._checkpointer is None:
            raise PersistenceError("PersistenceManager not entered — use 'async with'")
        return self._checkpointer

    @property
    def is_postgres(self) -> bool:
        """True, если активен PostgresSaver (production). False — MemorySaver."""
        return self._is_postgres

    async def health_check(self) -> bool:
        """Проверить работоспособность persistence-слоя.

        Для PostgresSaver — легковесный пробный ``aget_tuple`` (несуществующий
        thread_id → None, без побочных эффектов). Для MemorySaver — всегда True.
        Используется Docker healthcheck (TD-S5-04) и Facade (TD-S5-02).

        Returns:
            True если persistence-слой отвечает.
        """
        if self._checkpointer is None:
            return False
        if not self._is_postgres:
            return True
        try:
            await self._checkpointer.aget_tuple({"configurable": {"thread_id": "__healthcheck__"}})
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("persistence health_check failed: %s", exc)
            return False

    @staticmethod
    def _create_memory_saver() -> CheckpointerType:
        """Создать MemorySaver (in-memory, без persistence)."""
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()


def _mask_dsn(dsn: str) -> str:
    """Скрыть пароль в DSN для логов.

    Args:
        dsn: строка подключения вида ``postgresql://user:password@host:port/db``.

    Returns:
        DSN с заменённым паролем на ``***``.
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
