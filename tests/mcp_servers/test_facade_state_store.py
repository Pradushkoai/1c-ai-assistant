"""tests/mcp_servers/test_facade_state_store.py — FacadeStateStore (TD-S7-01).

Покрытие:
- In-memory fallback (no checkpointer): load/save round-trip, load None if not saved,
  save overwrites, delete.
- Mock checkpointer: aput/aget_tuple mock, load после save, survive-restart (2 store
  instances с тем же mock — второй находит state от первого).
- TaskState round-trip (model_dump_json → model_validate_json) с datetime, subtasks,
  iterations.
- is_persistent / is_postgres properties.
- FacadeHandlers с state_store: handle_plan сохраняет в store, handle_gather загружает.
- state_class parameter (для тестов с _FakeState).

См. ADR-0013, ADR-0014, D-2026-07-13-13.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_servers.facade.state_store import FacadeStateStore


# ─── Test state class (Pydantic-like) ───────────────────────────────────────


class _TestState:
    """Простой Pydantic-like state для тестов (имитация TaskState)."""

    def __init__(
        self,
        task_id: str = "test-1",
        description: str = "d",
        fsm_state: str = "planning",
        subtasks: list[dict[str, Any]] | None = None,
    ) -> None:
        self.task_id = task_id
        self.description = description
        self.fsm_state = fsm_state
        self.subtasks = subtasks or []
        self.current_subtask_idx = 0

    def model_dump_json(self) -> str:
        import json

        # Subtasks могут быть dict или objects с .id — сериализуем в dict.
        subtasks_data = []
        for s in self.subtasks:
            if isinstance(s, dict):
                subtasks_data.append(s)
            elif hasattr(s, "id"):
                subtasks_data.append({"id": s.id})
            else:
                subtasks_data.append(str(s))

        return json.dumps(
            {
                "task_id": self.task_id,
                "description": self.description,
                "fsm_state": self.fsm_state,
                "subtasks": subtasks_data,
                "current_subtask_idx": self.current_subtask_idx,
            },
            ensure_ascii=False,
        )

    @classmethod
    def model_validate_json(cls, json_str: str) -> _TestState:
        import json

        data = json.loads(json_str)
        # subtasks — list of dict; конвертируем в MagicMock с .id для tests.
        subtasks: list[Any] = []
        for s in data.get("subtasks", []):
            if isinstance(s, dict) and "id" in s:
                st = MagicMock()
                st.id = s["id"]
                subtasks.append(st)
            else:
                subtasks.append(s)
        state = cls(
            task_id=data["task_id"],
            description=data["description"],
            fsm_state=data.get("fsm_state", "planning"),
        )
        state.subtasks = subtasks
        state.current_subtask_idx = data.get("current_subtask_idx", 0)
        return state

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _TestState):
            return False
        return (
            self.task_id == other.task_id
            and self.description == other.description
            and self.fsm_state == other.fsm_state
            and self.subtasks == other.subtasks
        )

    def model_copy(self, *, update: dict[str, Any] | None = None) -> _TestState:
        """Создать копию с обновлениями (имитация Pydantic model_copy)."""
        import copy

        new = copy.copy(self)
        new.subtasks = list(self.subtasks)
        if update:
            for k, v in update.items():
                setattr(new, k, v)
        return new


# ─── In-memory fallback ─────────────────────────────────────────────────────


class TestInMemoryFallback:
    """In-memory fallback (checkpointer=None)."""

    @pytest.mark.asyncio
    async def test_load_none_if_not_saved(self) -> None:
        store = FacadeStateStore(state_class=_TestState)
        assert await store.load_state("plan-x") is None

    @pytest.mark.asyncio
    async def test_save_load_round_trip(self) -> None:
        store = FacadeStateStore(state_class=_TestState)
        state = _TestState(task_id="t1", description="test", fsm_state="planning")
        await store.save_state("plan-1", state)

        loaded = await store.load_state("plan-1")
        assert loaded is not None
        assert loaded.task_id == "t1"
        assert loaded.description == "test"
        assert loaded.fsm_state == "planning"

    @pytest.mark.asyncio
    async def test_save_overwrites(self) -> None:
        store = FacadeStateStore(state_class=_TestState)
        state1 = _TestState(task_id="t1", description="v1")
        state2 = _TestState(task_id="t1", description="v2")

        await store.save_state("plan-1", state1)
        await store.save_state("plan-1", state2)

        loaded = await store.load_state("plan-1")
        assert loaded.description == "v2"

    @pytest.mark.asyncio
    async def test_delete_state(self) -> None:
        store = FacadeStateStore(state_class=_TestState)
        state = _TestState(task_id="t1")
        await store.save_state("plan-1", state)
        await store.delete_state("plan-1")
        assert await store.load_state("plan-1") is None

    @pytest.mark.asyncio
    async def test_multiple_plans(self) -> None:
        store = FacadeStateStore(state_class=_TestState)
        s1 = _TestState(task_id="t1", description="plan1")
        s2 = _TestState(task_id="t2", description="plan2")

        await store.save_state("plan-1", s1)
        await store.save_state("plan-2", s2)

        l1 = await store.load_state("plan-1")
        l2 = await store.load_state("plan-2")
        assert l1.description == "plan1"
        assert l2.description == "plan2"

    def test_is_persistent_false_without_checkpointer(self) -> None:
        store = FacadeStateStore()
        assert store.is_persistent is False
        assert store.is_postgres is False


# ─── Mock checkpointer (survive-restart) ────────────────────────────────────


def _make_mock_checkpointer() -> MagicMock:
    """Mock LangGraph checkpointer с in-memory storage (dict thread_id → checkpoint)."""
    storage: dict[
        str, dict[str, Any]
    ] = {}  # thread_id → {checkpoint_ns → {checkpoint_id → (checkpoint, metadata, parent)}}

    cp = MagicMock()

    async def _aget_tuple(config: dict[str, Any]) -> Any:
        thread_id = config["configurable"]["thread_id"]
        ns = config["configurable"].get("checkpoint_ns", "")
        if thread_id not in storage or ns not in storage[thread_id]:
            return None
        # Возвращаем последний checkpoint.
        checkpoints = storage[thread_id][ns]
        if not checkpoints:
            return None
        last_id = list(checkpoints.keys())[-1]
        checkpoint_data, metadata, parent_id = checkpoints[last_id]
        # CheckpointTuple-like.
        tuple_result = MagicMock()
        tuple_result.checkpoint = checkpoint_data
        tuple_result.metadata = metadata
        tuple_result.parent_config = {"configurable": {"checkpoint_id": parent_id}} if parent_id else None
        return tuple_result

    async def _aput(
        config: dict[str, Any],
        checkpoint: dict[str, Any],
        metadata: dict[str, Any],
        new_versions: dict[str, Any],
    ) -> dict[str, Any]:
        thread_id = config["configurable"]["thread_id"]
        ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent_id = config["configurable"].get("checkpoint_id")

        storage.setdefault(thread_id, {}).setdefault(ns, {})[checkpoint_id] = (
            checkpoint,
            metadata,
            parent_id,
        )
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    cp.aget_tuple = _aget_tuple
    cp.aput = _aput
    # Сохраняем storage на mock для inspect в тестах.
    cp._storage = storage  # type: ignore[attr-defined]
    return cp


class TestMockCheckpointer:
    """Mock checkpointer — persistence through storage dict."""

    @pytest.mark.asyncio
    async def test_save_load_with_checkpointer(self) -> None:
        cp = _make_mock_checkpointer()
        store = FacadeStateStore(checkpointer=cp, state_class=_TestState)

        state = _TestState(task_id="t1", description="test")
        await store.save_state("plan-1", state)

        loaded = await store.load_state("plan-1")
        assert loaded is not None
        assert loaded.task_id == "t1"
        assert loaded.description == "test"

    @pytest.mark.asyncio
    async def test_load_none_if_not_saved(self) -> None:
        cp = _make_mock_checkpointer()
        store = FacadeStateStore(checkpointer=cp, state_class=_TestState)

        assert await store.load_state("plan-nonexistent") is None

    @pytest.mark.asyncio
    async def test_survive_restart_same_checkpointer(self) -> None:
        """Survive-restart: 2 store instances с тем же checkpointer — второй находит state."""
        cp = _make_mock_checkpointer()

        # "Первый запуск": store1 сохраняет state.
        store1 = FacadeStateStore(checkpointer=cp, state_class=_TestState)
        state = _TestState(task_id="t1", description="survive-restart")
        await store1.save_state("plan-1", state)

        # "Рестарт контейнера": store2 — новый instance, тот же checkpointer (storage).
        store2 = FacadeStateStore(checkpointer=cp, state_class=_TestState)
        loaded = await store2.load_state("plan-1")
        assert loaded is not None
        assert loaded.task_id == "t1"
        assert loaded.description == "survive-restart"

    @pytest.mark.asyncio
    async def test_save_overwrites_with_checkpointer(self) -> None:
        cp = _make_mock_checkpointer()
        store = FacadeStateStore(checkpointer=cp, state_class=_TestState)

        await store.save_state("plan-1", _TestState(task_id="t1", description="v1"))
        await store.save_state("plan-1", _TestState(task_id="t1", description="v2"))

        loaded = await store.load_state("plan-1")
        assert loaded.description == "v2"

    @pytest.mark.asyncio
    async def test_is_persistent_with_checkpointer(self) -> None:
        cp = _make_mock_checkpointer()
        store = FacadeStateStore(checkpointer=cp, is_postgres=True)
        assert store.is_persistent is True
        assert store.is_postgres is True

    @pytest.mark.asyncio
    async def test_checkpointer_failure_falls_back_to_in_memory(self) -> None:
        """Если aput падает — state сохраняется in-memory (fallback)."""
        cp = MagicMock()
        cp.aput = AsyncMock(side_effect=RuntimeError("connection lost"))

        store = FacadeStateStore(checkpointer=cp, state_class=_TestState)
        state = _TestState(task_id="t1")
        # Не должно поднять исключение — fallback на in-memory.
        await store.save_state("plan-1", state)

        # Load тоже упадёт на checkpointer → вернёт None (не in-memory fallback при load).
        # Но state в in-memory сохранён.
        assert "plan-1" in store._in_memory

    @pytest.mark.asyncio
    async def test_load_checkpointer_failure_returns_none(self) -> None:
        """Если aget_tuple падает — load возвращает None (graceful degradation)."""
        cp = MagicMock()
        cp.aget_tuple = AsyncMock(side_effect=RuntimeError("connection lost"))

        store = FacadeStateStore(checkpointer=cp, state_class=_TestState)
        loaded = await store.load_state("plan-1")
        assert loaded is None


# ─── TaskState round-trip (real TaskState) ──────────────────────────────────


class TestTaskStateRoundTrip:
    """Round-trip через FacadeStateStore с real TaskState."""

    @pytest.mark.asyncio
    async def test_task_state_with_subtasks_and_iterations(self) -> None:
        from orchestrator.state import FSMState, Iteration, Subtask, TaskState
        from parsers.models import ObjectRef

        store = FacadeStateStore(state_class=TaskState)

        state = TaskState(
            task_id="task-1",
            description="Add posting handler",
            config_name="ut11",
            config_version="4.5.3",
            platform_version="8.3.20",
            fsm_state=FSMState.CODING,
            subtasks=[
                Subtask(
                    id="st-001",
                    name="ОбработкаПроведения",
                    target_module=ObjectRef(type="CommonModule", name="ОбработкаПроведения"),
                    description="Add handler",
                    max_iterations=3,
                )
            ],
            current_iteration=1,
            iterations=[
                Iteration(
                    number=1,
                    code="Функция Тест() КонецФункции",
                    llm_response={"explanation": "test"},
                )
            ],
        )

        await store.save_state("plan-1", state)
        loaded = await store.load_state("plan-1")

        assert loaded is not None
        assert loaded.task_id == "task-1"
        assert loaded.description == "Add posting handler"
        assert loaded.fsm_state == FSMState.CODING
        assert len(loaded.subtasks) == 1
        assert loaded.subtasks[0].id == "st-001"
        assert loaded.subtasks[0].name == "ОбработкаПроведения"
        assert len(loaded.iterations) == 1
        assert loaded.iterations[0].number == 1
        assert "Тест" in loaded.iterations[0].code

    @pytest.mark.asyncio
    async def test_task_state_with_datetime_fields(self) -> None:
        """datetime поля (created_at, updated_at) корректно round-trip."""
        from orchestrator.state import FSMState, TaskState

        store = FacadeStateStore(state_class=TaskState)
        state = TaskState(
            task_id="t1",
            description="d",
            config_name="ut11",
            config_version="4.5.3",
            platform_version="8.3.20",
            fsm_state=FSMState.INIT,
        )

        await store.save_state("plan-1", state)
        loaded = await store.load_state("plan-1")
        assert loaded is not None
        assert loaded.created_at is not None
        assert loaded.updated_at is not None

    @pytest.mark.asyncio
    async def test_task_state_survive_restart_with_mock_checkpointer(self) -> None:
        """Survive-restart с real TaskState + mock checkpointer."""
        from orchestrator.state import FSMState, Subtask, TaskState
        from parsers.models import ObjectRef

        cp = _make_mock_checkpointer()

        store1 = FacadeStateStore(checkpointer=cp, state_class=TaskState)
        state = TaskState(
            task_id="task-restart",
            description="survive restart test",
            config_name="ut11",
            config_version="4.5.3",
            platform_version="8.3.20",
            fsm_state=FSMState.GATHERING,
            subtasks=[
                Subtask(
                    id="st-001",
                    name="X",
                    target_module=ObjectRef(type="CommonModule", name="X"),
                    description="d",
                )
            ],
        )
        await store1.save_state("plan-restart", state)

        # "Рестарт": новый store, тот же checkpointer.
        store2 = FacadeStateStore(checkpointer=cp, state_class=TaskState)
        loaded = await store2.load_state("plan-restart")
        assert loaded is not None
        assert loaded.task_id == "task-restart"
        assert loaded.fsm_state == FSMState.GATHERING
        assert len(loaded.subtasks) == 1
        assert loaded.subtasks[0].id == "st-001"


# ─── Integration: FacadeHandlers with state_store ───────────────────────────


class TestFacadeHandlersWithStore:
    """FacadeHandlers использует state_store (survive-restart через store)."""

    @pytest.mark.asyncio
    async def test_handle_plan_saves_to_store(self) -> None:
        """handle_plan сохраняет state в store (не in-memory dict handlers)."""
        from mcp_servers.facade import FacadeHandlers, FacadeStateStore

        # Mock state_factory (sync) + node_plan с _TestState.
        def _state_factory(**kwargs: Any) -> _TestState:
            return _TestState(
                task_id=kwargs.get("task_id", ""),
                description=kwargs.get("description", ""),
                fsm_state=kwargs.get("fsm_state", "planning"),
            )

        async def _plan_node(state: Any, llm: Any = None, metadata_server: Any = None) -> dict[str, Any]:
            state.subtasks = []
            return {"subtasks": [], "plan_result": {"strategy": "single"}, "fsm_state": "planning"}

        store = FacadeStateStore(state_class=_TestState)
        h = FacadeHandlers(
            state_factory=_state_factory,
            node_plan=_plan_node,
            state_store=store,
        )

        result = await h.handle_plan(
            {
                "task": "test",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        plan_id = result["plan_id"]

        # State в store.
        saved = await store.load_state(plan_id)
        assert saved is not None
        assert saved.task_id == plan_id

    @pytest.mark.asyncio
    async def test_handle_gather_loads_from_store(self) -> None:
        """handle_gather загружает state из store (а не in-memory dict)."""
        from mcp_servers.facade import FacadeHandlers, FacadeStateStore

        async def _state_factory(**kwargs: Any) -> _TestState:
            return _TestState(
                task_id=kwargs.get("task_id", ""),
                description=kwargs.get("description", ""),
                fsm_state=kwargs.get("fsm_state", "planning"),
            )

        async def _gather_node(state: Any, kb_server: Any = None, metadata_server: Any = None) -> dict[str, Any]:
            return {"gather_result": {"context_summary": "ctx"}, "fsm_state": "gathering"}

        store = FacadeStateStore(state_class=_TestState)
        h = FacadeHandlers(
            state_factory=_state_factory,
            node_gather=_gather_node,
            state_store=store,
        )

        # Pre-populate store с state (имитация после plan).
        state = _TestState(task_id="plan-1", description="d", fsm_state="planning")
        # subtasks — list of objects с .id (имитация Subtask).
        st = MagicMock()
        st.id = "st-001"
        state.subtasks = [st]
        await h._save_state("plan-1", state)

        # handle_gather должен загрузить из store.
        result = await h.handle_gather({"plan_id": "plan-1", "subtask_id": "st-001"})
        assert result["subtask_id"] == "st-001"
        assert result["context_summary"] == "ctx"

    @pytest.mark.asyncio
    async def test_survive_restart_handlers_with_store(self) -> None:
        """2 FacadeHandlers instances с тем же store — второй находит state."""
        from mcp_servers.facade import FacadeHandlers, FacadeStateStore

        def _state_factory(**kwargs: Any) -> _TestState:
            return _TestState(
                task_id=kwargs.get("task_id", ""),
                description=kwargs.get("description", ""),
                fsm_state=kwargs.get("fsm_state", "planning"),
            )

        async def _gather_node(state: Any, kb_server: Any = None, metadata_server: Any = None) -> dict[str, Any]:
            return {"gather_result": {"context_summary": "after-restart"}, "fsm_state": "gathering"}

        # Shared store (in-memory, имитирует persistent для теста).
        store = FacadeStateStore(state_class=_TestState)

        # "Первый запуск": handlers1 сохраняет state.
        h1 = FacadeHandlers(
            state_factory=_state_factory,
            state_store=store,
        )
        state = _TestState(task_id="plan-1", description="d", fsm_state="planning")
        st = MagicMock()
        st.id = "st-001"
        state.subtasks = [st]
        await h1._save_state("plan-1", state)

        # "Рестарт": handlers2 — новый instance, тот же store.
        h2 = FacadeHandlers(
            state_factory=_state_factory,
            node_gather=_gather_node,
            state_store=store,
        )
        result = await h2.handle_gather({"plan_id": "plan-1", "subtask_id": "st-001"})
        assert result["context_summary"] == "after-restart"
