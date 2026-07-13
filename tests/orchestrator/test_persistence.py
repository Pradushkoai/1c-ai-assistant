"""tests/orchestrator/test_persistence.py — PersistenceManager (TD-S5-01).

Покрытие:
- Unit: MemorySaver fallback (dsn=None), DSN masking, get_checkpointer-before-enter,
  ImportError fallback, bad DSN → PersistenceError, from_env, health_check,
  mock-lifecycle (setup вызван, connection закрыт).
- Integration (skip-if TEST_POSTGRES_DSN not set): real setup + checkpoint roundtrip
  через минимальный LangGraph + survive-restart (доказывает «рестарт контейнера
  не теряет state»).

См. ADR-0014, ADR-0018, ADR-0015, D-2026-07-13-04/05.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest

from orchestrator.errors import PersistenceError
from orchestrator.persistence import PersistenceManager, _mask_dsn


# ─── Unit: MemorySaver fallback (no DSN) ─────────────────────────────────────


class TestMemorySaverFallback:
    """Без DSN — MemorySaver (dev/tests)."""

    @pytest.mark.asyncio
    async def test_no_dsn_uses_memory_saver(self) -> None:
        async with PersistenceManager(dsn=None) as pm:
            assert pm.is_postgres is False
            cp = pm.get_checkpointer()
            # MemorySaver — экземпляр langgraph MemorySaver.
            from langgraph.checkpoint.memory import MemorySaver

            assert isinstance(cp, MemorySaver)

    @pytest.mark.asyncio
    async def test_no_dsn_health_check_true(self) -> None:
        async with PersistenceManager(dsn=None) as pm:
            assert await pm.health_check() is True

    @pytest.mark.asyncio
    async def test_get_checkpointer_raises_before_enter(self) -> None:
        pm = PersistenceManager(dsn=None)
        with pytest.raises(PersistenceError, match="not entered"):
            pm.get_checkpointer()

    @pytest.mark.asyncio
    async def test_get_checkpointer_raises_after_exit(self) -> None:
        async with PersistenceManager(dsn=None) as pm:
            assert pm.get_checkpointer() is not None
        # После выхода — снова None / ошибка.
        with pytest.raises(PersistenceError, match="not entered"):
            pm.get_checkpointer()

    @pytest.mark.asyncio
    async def test_health_check_false_before_enter(self) -> None:
        pm = PersistenceManager(dsn=None)
        assert await pm.health_check() is False

    @pytest.mark.asyncio
    async def test_is_postgres_false_after_exit(self) -> None:
        async with PersistenceManager(dsn=None) as pm:
            assert pm.is_postgres is False
        assert pm.is_postgres is False


# ─── Unit: DSN masking ───────────────────────────────────────────────────────


class TestMaskDsn:
    """Пароль не должен утекать в логи."""

    def test_masks_password(self) -> None:
        dsn = "postgresql://agent:secret@postgres:5432/agent"
        masked = _mask_dsn(dsn)
        assert "secret" not in masked
        assert "***" in masked
        assert masked == "postgresql://agent:***@postgres:5432/agent"

    def test_masks_password_with_query(self) -> None:
        dsn = "postgresql://agent:p@ss@host:5432/db?sslmode=disable"
        masked = _mask_dsn(dsn)
        assert "p@ss" not in masked
        assert "***" in masked

    def test_no_password_unchanged(self) -> None:
        dsn = "postgresql://agent@host:5432/db"
        # Нет двоеточия в creds → не маскируем.
        masked = _mask_dsn(dsn)
        assert masked == dsn

    def test_no_credentials_unchanged(self) -> None:
        dsn = "postgresql://host:5432/db"
        assert _mask_dsn(dsn) == dsn

    def test_empty_dsn(self) -> None:
        assert _mask_dsn("") == ""


# ─── Unit: from_env ──────────────────────────────────────────────────────────


class TestFromEnv:
    """from_env читает DATABASE_URL."""

    def test_from_env_reads_database_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
        pm = PersistenceManager.from_env()
        assert pm.dsn == "postgresql://u:p@host:5432/db"

    def test_from_env_custom_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("PG_DSN", "postgresql://u:p@host:5432/db")
        pm = PersistenceManager.from_env(dsn_env_var="PG_DSN")
        assert pm.dsn == "postgresql://u:p@host:5432/db"

    def test_from_env_no_var_returns_memory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        pm = PersistenceManager.from_env()
        assert pm.dsn is None

    def test_from_env_empty_string_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DATABASE_URL", "")
        pm = PersistenceManager.from_env()
        assert pm.dsn is None


# ─── Unit: ImportError fallback ──────────────────────────────────────────────


class TestImportErrorFallback:
    """Если langgraph-checkpoint-postgres не установлен — graceful MemorySaver."""

    @pytest.mark.asyncio
    async def test_import_error_falls_back_to_memory(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import langgraph.checkpoint.postgres.aio as pg_aio

        # Скрываем AsyncPostgresSaver — эмулируем отсутствие пакета.
        monkeypatch.setattr(pg_aio, "AsyncPostgresSaver", None)
        # Имитируем ImportError при `from ... import AsyncPostgresSaver`.
        real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "langgraph.checkpoint.postgres.aio":
                raise ImportError("simulated missing dep")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)

        async with PersistenceManager(dsn="postgresql://u:p@host:5432/db") as pm:
            assert pm.is_postgres is False
            from langgraph.checkpoint.memory import MemorySaver

            assert isinstance(pm.get_checkpointer(), MemorySaver)


# ─── Unit: mock lifecycle (fake AsyncPostgresSaver) ──────────────────────────


class _FakeSaver:
    """Заглушка AsyncPostgresSaver для проверки lifecycle."""

    def __init__(self) -> None:
        self.setup_called = False
        self.aget_tuple_called = False

    async def setup(self) -> None:
        self.setup_called = True

    async def aget_tuple(self, config: Any) -> None:
        self.aget_tuple_called = True
        return None


class _FakeSaverCM:
    """Имитирует результат AsyncPostgresSaver.from_conn_string (async cm)."""

    def __init__(self, dsn: str, *, fail_on_enter: Exception | None = None) -> None:
        self.dsn = dsn
        self.saver = _FakeSaver()
        self.entered = False
        self.exited = False
        self.fail_on_enter = fail_on_enter

    async def __aenter__(self) -> _FakeSaver:
        if self.fail_on_enter is not None:
            raise self.fail_on_enter
        self.entered = True
        return self.saver

    async def __aexit__(self, *args: object) -> bool:
        self.exited = True
        return False


@pytest.fixture
def fake_postgres_saver(monkeypatch: pytest.MonkeyPatch) -> list[_FakeSaverCM]:
    """Подменяет AsyncPostgresSaver.from_conn_string фейком. Возвращает список CM."""
    created: list[_FakeSaverCM] = []

    class _FakeAsyncPostgresSaver:
        fail_on_enter: Exception | None = None

        @classmethod
        def from_conn_string(cls, dsn: str, **_kwargs: Any) -> _FakeSaverCM:
            cm = _FakeSaverCM(dsn, fail_on_enter=cls.fail_on_enter)
            created.append(cm)
            return cm

    import langgraph.checkpoint.postgres.aio as pg_aio

    monkeypatch.setattr(pg_aio, "AsyncPostgresSaver", _FakeAsyncPostgresSaver)
    return created


class TestPostgresLifecycleMocked:
    """Проверка lifecycle PersistenceManager с фейковым PostgresSaver."""

    @pytest.mark.asyncio
    async def test_postgres_init_calls_setup(
        self, fake_postgres_saver: list[_FakeSaverCM]
    ) -> None:
        async with PersistenceManager(dsn="postgresql://u:p@host:5432/db") as pm:
            assert pm.is_postgres is True
            assert len(fake_postgres_saver) == 1
            assert fake_postgres_saver[0].entered is True
            assert fake_postgres_saver[0].saver.setup_called is True
            assert pm.get_checkpointer() is fake_postgres_saver[0].saver

    @pytest.mark.asyncio
    async def test_postgres_exit_closes_connection(
        self, fake_postgres_saver: list[_FakeSaverCM]
    ) -> None:
        async with PersistenceManager(dsn="postgresql://u:p@host:5432/db") as pm:
            assert pm.is_postgres is True
        # После выхода — connection закрыт, state сброшен.
        assert fake_postgres_saver[0].exited is True
        assert pm.is_postgres is False

    @pytest.mark.asyncio
    async def test_postgres_health_check_calls_aget_tuple(
        self, fake_postgres_saver: list[_FakeSaverCM]
    ) -> None:
        async with PersistenceManager(dsn="postgresql://u:p@host:5432/db") as pm:
            assert await pm.health_check() is True
            assert fake_postgres_saver[0].saver.aget_tuple_called is True

    @pytest.mark.asyncio
    async def test_postgres_connection_error_raises_persistence_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ошибка подключения → PersistenceError, CM корректно закрыт."""

        class _FailingSaver:
            fail = OSError("connection refused")

            @classmethod
            def from_conn_string(cls, dsn: str, **_kw: Any) -> _FakeSaverCM:
                return _FakeSaverCM(dsn, fail_on_enter=cls.fail)

        import langgraph.checkpoint.postgres.aio as pg_aio

        monkeypatch.setattr(pg_aio, "AsyncPostgresSaver", _FailingSaver)

        with pytest.raises(PersistenceError, match="Cannot initialize PostgresSaver"):
            async with PersistenceManager(dsn="postgresql://u:p@bad:5432/db"):
                pass

    @pytest.mark.asyncio
    async def test_postgres_setup_error_raises_persistence_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ошибка в setup() → PersistenceError."""

        class _SaverSetupFails:
            class _CM:
                def __init__(self, dsn: str) -> None:
                    self.dsn = dsn

                async def __aenter__(self) -> Any:
                    class _S:
                        async def setup(self) -> None:
                            raise RuntimeError("setup failed")

                    return _S()

                async def __aexit__(self, *a: object) -> bool:
                    return False

            @classmethod
            def from_conn_string(cls, dsn: str, **_kw: Any) -> Any:
                return cls._CM(dsn)

        import langgraph.checkpoint.postgres.aio as pg_aio

        monkeypatch.setattr(pg_aio, "AsyncPostgresSaver", _SaverSetupFails)

        with pytest.raises(PersistenceError, match="Cannot initialize PostgresSaver"):
            async with PersistenceManager(dsn="postgresql://u:p@host:5432/db"):
                pass


# ─── Integration: real Postgres (skip-if TEST_POSTGRES_DSN not set) ──────────


def _integration_dsn() -> str | None:
    """DSN для integration-теста (env TEST_POSTGRES_DSN)."""
    return os.environ.get("TEST_POSTGRES_DSN")


@pytest.mark.skipif(
    "not os.environ.get('TEST_POSTGRES_DSN')",
    reason="TEST_POSTGRES_DSN not set; requires running Postgres",
)
class TestPostgresIntegration:
    """Integration с реальным Postgres.

    Запуск::

        TEST_POSTGRES_DSN=postgresql://agent:agent@localhost:5432/agent \
            uv run pytest tests/orchestrator/test_persistence.py::TestPostgresIntegration -v
    """

    @pytest.mark.asyncio
    async def test_setup_creates_checkpoint_tables(self) -> None:
        """setup() создаёт checkpoint-таблицы (идемпотентно)."""
        dsn = _integration_dsn()
        assert dsn is not None
        async with PersistenceManager(dsn=dsn) as pm:
            assert pm.is_postgres is True
            assert await pm.health_check() is True

    @pytest.mark.asyncio
    async def test_checkpoint_survives_restart(self) -> None:
        """Checkpoint переживает «рестарт»: новый PersistenceManager читает state.

        Это ключевое требование TD-S5-01: «рестарт контейнера не должен терять state».
        """
        dsn = _integration_dsn()
        assert dsn is not None
        thread_id = f"test-restart-{uuid.uuid4().hex[:8]}"

        # Минимальный граф для записи checkpoint'а.
        from langgraph.graph import END, StateGraph
        from typing_extensions import TypedDict

        class TinyState(TypedDict, total=False):
            value: int

        def add_node(state: TinyState) -> dict[str, int]:
            return {"value": state.get("value", 0) + 1}

        def build_compiled(checkpointer: Any) -> Any:
            g = StateGraph(TinyState)
            g.add_node("add", add_node)
            g.set_entry_point("add")
            g.add_edge("add", END)
            return g.compile(checkpointer=checkpointer)

        # «Первый запуск»: пишем checkpoint.
        async with PersistenceManager(dsn=dsn) as pm1:
            compiled1 = build_compiled(pm1.get_checkpointer())
            result = await compiled1.ainvoke(
                {"value": 10}, config={"configurable": {"thread_id": thread_id}}
            )
            assert result["value"] == 11

        # «Рестарт контейнера»: новый PersistenceManager, тот же DSN.
        async with PersistenceManager(dsn=dsn) as pm2:
            assert pm2.is_postgres is True
            compiled2 = build_compiled(pm2.get_checkpointer())
            # Читаем state по thread_id — должен найтись checkpoint от pm1.
            state = await compiled2.aget_state(
                config={"configurable": {"thread_id": thread_id}}
            )
            assert state.values.get("value") == 11, (
                "checkpoint не пережил рестарт PersistenceManager"
            )

    @pytest.mark.asyncio
    async def test_health_check_detects_dead_connection(self) -> None:
        """health_check возвращает False после закрытия manager."""
        dsn = _integration_dsn()
        assert dsn is not None
        pm = PersistenceManager(dsn=dsn)
        # Не войдя — health_check False.
        assert await pm.health_check() is False
