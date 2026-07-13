"""FacadeStateStore — persistence для Facade state (TD-S7-01, survival-restart).

Сохраняет TaskState по plan_id через LangGraph checkpointer (PostgresSaver в
production, MemorySaver fallback). Переживает рестарт контейнера: после restart
FacadeHandlers загружает state по plan_id из persistent store.

Architecture (D-2026-07-13-13):
- ``checkpointer.aget_tuple(config)`` где ``thread_id = plan_id`` → CheckpointTuple.
- ``checkpoint["channel_values"]["task_state"]`` → JSON-строка TaskState.
- ``TaskState.model_dump_json()`` / ``model_validate_json()`` для round-trip
  (обходит strict datetime validation).
- ``checkpointer.aput(config, checkpoint, metadata, new_versions)`` для save.
- Если checkpointer=None → in-memory fallback (dict[plan_id, json_str]).

См. ADR-0013 (Agent-Facade), ADR-0014 (PersistenceManager), ADR-0018 (TaskState
migration), D-2026-07-13-13.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

# Ключ в channel_values для TaskState JSON.
_TASK_STATE_KEY = "task_state"


class FacadeStateStore:
    """Persistence для Facade state через LangGraph checkpointer.

    Args:
        checkpointer: LangGraph BaseCheckpointSaver (PostgresSaver или MemorySaver).
            Если None — in-memory fallback (dict[plan_id, json_str]).
        is_postgres: True если checkpointer — PostgresSaver (для is_persistent property).
            Опционально; если не указано, is_persistent = checkpointer is not None.
    """

    def __init__(
        self,
        checkpointer: Any = None,
        is_postgres: bool = False,
        state_class: Any = None,
    ) -> None:
        self.checkpointer = checkpointer
        self._is_postgres = is_postgres
        # Класс для десериализации state (по умолчанию TaskState из orchestrator).
        # Для тестов можно передать _FakeState (или любой Pydantic-like с model_validate_json).
        self._state_class = state_class
        # In-memory fallback (если checkpointer=None) + cache для survive-restart tests.
        self._in_memory: dict[str, str] = {}

    @property
    def is_persistent(self) -> bool:
        """True если checkpointer задан (state переживает restart процесса)."""
        return self.checkpointer is not None

    @property
    def is_postgres(self) -> bool:
        """True если checkpointer — PostgresSaver (production persistence)."""
        return self._is_postgres

    async def load_state(self, plan_id: str) -> Any:
        """Загрузить TaskState по plan_id.

        Args:
            plan_id: идентификатор плана (= thread_id в checkpointer).

        Returns:
            TaskState или None если не найден.
        """
        if self.checkpointer is not None:
            return await self._load_from_checkpointer(plan_id)
        # In-memory fallback.
        if plan_id in self._in_memory:
            return self._deserialize(self._in_memory[plan_id], self._state_class)
        return None

    async def save_state(self, plan_id: str, state: Any) -> None:
        """Сохранить TaskState по plan_id.

        Args:
            plan_id: идентификатор плана (= thread_id в checkpointer).
            state: TaskState (или совместимый объект с model_dump_json).
        """
        json_str = self._serialize(state)
        if self.checkpointer is not None:
            await self._save_to_checkpointer(plan_id, json_str, state)
        else:
            self._in_memory[plan_id] = json_str

    async def delete_state(self, plan_id: str) -> None:
        """Удалить state по plan_id (best-effort, для cleanup).

        Note: LangGraph checkpointer не имеет delete по thread_id в public API.
        Для in-memory fallback — удаляет из dict. Для PostgresSaver — no-op
        (cleanup через TTL или отдельный maintenance job).
        """
        self._in_memory.pop(plan_id, None)
        # Для checkpointer — no-op (LangGraph не предоставляет delete by thread_id).
        log.debug("delete_state: %s (checkpointer cleanup is no-op)", plan_id)

    # ─── checkpointer integration ───────────────────────────────────────────

    async def _load_from_checkpointer(self, plan_id: str) -> Any:
        """Load через checkpointer.aget_tuple."""
        config = {
            "configurable": {"thread_id": plan_id, "checkpoint_ns": ""},
        }
        try:
            tuple_result = await self.checkpointer.aget_tuple(config)
        except Exception as exc:  # noqa: BLE001
            log.warning("state_store load failed (plan_id=%s): %s", plan_id, exc)
            return None

        if tuple_result is None:
            return None

        checkpoint = tuple_result.checkpoint
        if not isinstance(checkpoint, dict):
            log.warning("state_store: checkpoint is not dict: %s", type(checkpoint))
            return None

        channel_values = checkpoint.get("channel_values", {})
        json_str = channel_values.get(_TASK_STATE_KEY)
        if json_str is None:
            return None

        return self._deserialize(json_str, self._state_class)

    async def _save_to_checkpointer(self, plan_id: str, json_str: str, state: Any) -> None:
        """Save через checkpointer.aput с правильно structured Checkpoint."""
        checkpoint = {
            "v": 3,
            "id": uuid.uuid4().hex,
            "ts": datetime.now(UTC).isoformat(),
            "channel_values": {_TASK_STATE_KEY: json_str},
            "channel_versions": {},
            "versions_seen": {},
            "pending_sends": [],
        }
        metadata = {
            "source": "facade",
            "step": getattr(state, "fsm_state", "unknown"),
            "plan_id": plan_id,
        }
        config = {
            "configurable": {"thread_id": plan_id, "checkpoint_ns": ""},
        }
        try:
            await self.checkpointer.aput(config, checkpoint, metadata, {})
        except Exception as exc:  # noqa: BLE001
            log.warning("state_store save failed (plan_id=%s): %s", plan_id, exc)
            # Fallback на in-memory чтобы не потерять state в текущей сессии.
            self._in_memory[plan_id] = json_str

    # ─── serialization ──────────────────────────────────────────────────────

    @staticmethod
    def _serialize(state: Any) -> str:
        """Сериализовать state в JSON-строку."""
        if hasattr(state, "model_dump_json"):
            result: str = state.model_dump_json()
            return result
        # Fallback для plain dict / other.
        import json

        return json.dumps(state, ensure_ascii=False, default=str)

    @staticmethod
    def _deserialize(json_str: str, state_class: Any = None) -> Any:
        """Десериализовать JSON-строку в state.

        Использует ``state_class.model_validate_json`` если задан. Иначе — plain
        dict через ``json.loads`` (caller ответственен за reconstruction).

        Boundary rule (CONCEPTUAL §1.1): mcp_servers НЕ импортирует orchestrator.
        Production callers (agent-слой) передают ``state_class=TaskState`` через
        ``FacadeStateStore(state_class=TaskState)``.

        Args:
            json_str: JSON-строка от model_dump_json.
            state_class: класс с model_validate_json (TaskState в production,
                _FakeState/_TestState в тестах).
        """
        if state_class is not None:
            return state_class.model_validate_json(json_str)
        # Без state_class — возвращаем dict (caller реконструирует сам).
        import json

        log.warning("state_store: no state_class, returning dict")
        return json.loads(json_str)
