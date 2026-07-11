# Шаг 9 — Error taxonomy + state persistence

> **ADR-0014:** Error taxonomy + PostgresSaver для персистентности state
> **Зависимости:** Шаг 4 (TaskState, EscalateResult), Шаг 5 (error_contract у каждого tool), Шаг 8 (Facade error propagation)
> **Артефакт:** `packages/orchestrator/src/orchestrator/{errors.py, persistence.py}`

## 1. Зачем отдельный шаг для ошибок и persistence

Pipeline длинный (Plan → Gather → Code → Validate → Review → Commit, плюс retry-циклы). На любом этапе может что-то пойти не так:

- LLM вернул невалидный JSON (schema violation)
- BSL LS subprocess завис (timeout 60s)
- Qdrant недоступен (network error)
- git push упал из-за конфликта
- 3 итерации Coder'а — все failed → escalate
- Превышен token budget
- LLM-провайдер недоступен (5xx)

Без таксономии — retry-логика превращается в спагетти `if/elif` без возможности тестирования. Без persistence — длинные задачи (>1 часа) теряются при рестарте процесса.

Этот шаг — **закрывает обе дыры**: явная иерархия ошибок + явная схема Postgres-таблицы для checkpoint'ов.

## 2. Иерархия ошибок

```python
# packages/orchestrator/src/orchestrator/errors.py
"""Taxonomy ошибок pipeline.

Иерархия:
    AgentError (базовый)
    ├── PreflightError           — данные не готовы
    ├── IndexStaleError          — индексы устарели
    ├── SchemaViolationError     — LLM нарушила JSON Schema
    ├── ToolError                — ошибка MCP tool
    │   ├── ToolTimeoutError
    │   ├── ToolConnectionError
    │   ├── ToolExecutionError
    │   └── RoleForbiddenError
    ├── LLMError                 — ошибка LLM-провайдера
    │   ├── LLMUnavailableError
    │   ├── LLMRateLimitError
    │   └── LLMBudgetExceededError
    ├── ValidationFailedError    — детерминированный gate не прошёл
    ├── ReviewRejectedError      — LLM-рецензент отверг
    ├── MaxIterationsExceededError — 3 итерации failed
    ├── EscalationRequestedError — явная эскалация
    └── PersistenceError         — PostgresSaver упал

Каждая ошибка → action: retry | escalate | abort
"""
from __future__ import annotations

from enum import Enum
from typing import Literal


class ErrorAction(str, Enum):
    """Что делать с ошибкой."""
    RETRY = "retry"          # попробовать ещё раз (после небольшой паузы)
    ESCALATE = "escalate"    # остановить pipeline, PR с меткой needs-human-review
    ABORT = "abort"          # критическая ошибка, pipeline не резюмируется


class AgentError(Exception):
    """Базовый класс всех ошибок pipeline."""
    code: str = "AGENT_ERROR"
    action: ErrorAction = ErrorAction.ESCALATE
    http_status: int | None = None  # для REST API (если будет)

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        action: ErrorAction | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        if code:
            self.code = code
        if action:
            self.action = action
        self.details = details or {}


# ─── Preflight ошибки ────────────────────────────────────────────────────────

class PreflightError(AgentError):
    """Данные не готовы к запуску pipeline."""
    code = "PREFLIGHT_FAILED"
    action = ErrorAction.ABORT  # нет данных — нет pipeline


class IndexStaleError(AgentError):
    """Индексы устарели, нужен config build --force."""
    code = "INDEX_STALE"
    action = ErrorAction.ABORT


# ─── Schema violations ───────────────────────────────────────────────────────

class SchemaViolationError(AgentError):
    """LLM нарушила JSON Schema при structured_output.

    Если срабатывает в retry-цикле > 2 раз — escalate.
    """
    code = "SCHEMA_VIOLATION"
    action = ErrorAction.RETRY

    def __init__(self, message: str, *, schema_errors: list, **kwargs) -> None:
        super().__init__(message, details={"schema_errors": schema_errors}, **kwargs)


# ─── Tool errors ─────────────────────────────────────────────────────────────

class ToolError(AgentError):
    """Базовая ошибка MCP tool."""
    code = "TOOL_ERROR"
    action = ErrorAction.RETRY


class ToolTimeoutError(ToolError):
    """Tool превысил timeout."""
    code = "TOOL_TIMEOUT"
    action = ErrorAction.RETRY  # один retry — вдруг Java разогрелась

    def __init__(self, tool_name: str, timeout: int, **kwargs) -> None:
        super().__init__(
            f"Tool {tool_name} timed out after {timeout}s",
            details={"tool_name": tool_name, "timeout": timeout},
            **kwargs,
        )


class ToolConnectionError(ToolError):
    """MCP-сервер недоступен (network error)."""
    code = "TOOL_CONNECTION_FAILED"
    action = ErrorAction.RETRY

    def __init__(self, tool_name: str, original: Exception, **kwargs) -> None:
        super().__init__(
            f"Cannot connect to {tool_name}: {original}",
            details={"tool_name": tool_name, "original_type": type(original).__name__},
            **kwargs,
        )


class ToolExecutionError(ToolError):
    """Tool выполнен, но вернул ошибку."""
    code = "TOOL_EXECUTION_ERROR"
    action = ErrorAction.ESCALATE  # если сама логика tool'а упала — это серьёзно


class RoleForbiddenError(ToolError):
    """Роль не имеет прав на вызов этого tool'а.

    Это НЕ retry — это bug в TOOL_GROUPS или в коде узла.
    """
    code = "ROLE_FORBIDDEN"
    action = ErrorAction.ABORT

    def __init__(self, role: str, tool_name: str, **kwargs) -> None:
        super().__init__(
            f"Role {role} cannot call {tool_name}",
            details={"role": role, "tool_name": tool_name},
            **kwargs,
        )


# ─── LLM errors ──────────────────────────────────────────────────────────────

class LLMError(AgentError):
    """Базовая ошибка LLM-провайдера."""
    code = "LLM_ERROR"
    action = ErrorAction.RETRY


class LLMUnavailableError(LLMError):
    """5xx от LLM-провайдера."""
    code = "LLM_UNAVAILABLE"
    action = ErrorAction.RETRY


class LLMRateLimitError(LLMError):
    """429 — превышен rate limit."""
    code = "LLM_RATE_LIMIT"
    action = ErrorAction.RETRY

    def __init__(self, retry_after: int | None = None, **kwargs) -> None:
        super().__init__(
            "Rate limit exceeded",
            details={"retry_after": retry_after},
            **kwargs,
        )


class LLMBudgetExceededError(LLMError):
    """Превышен token budget для задачи."""
    code = "LLM_BUDGET_EXCEEDED"
    action = ErrorAction.ESCALATE  # бюджет не освободится сам

    def __init__(self, used: int, limit: int, **kwargs) -> None:
        super().__init__(
            f"Token budget exceeded: {used}/{limit}",
            details={"used": used, "limit": limit},
            **kwargs,
        )


# ─── Pipeline-flow ошибки ────────────────────────────────────────────────────

class ValidationFailedError(AgentError):
    """Детерминированный gate (BSL LS + антипаттерны) не прошёл.

    Это НЕ критическая ошибка — это сигнал для retry Coder'а.
    """
    code = "VALIDATION_FAILED"
    action = ErrorAction.RETRY

    def __init__(self, failed_checks: list[dict], **kwargs) -> None:
        super().__init__(
            f"Validation failed: {len(failed_checks)} checks",
            details={"failed_checks": failed_checks},
            **kwargs,
        )


class ReviewRejectedError(AgentError):
    """LLM-рецензент отверг код."""
    code = "REVIEW_REJECTED"
    action = ErrorAction.RETRY


class MaxIterationsExceededError(AgentError):
    """Достигнут max_iterations (3) — нужна эскалация."""
    code = "MAX_ITERATIONS_EXCEEDED"
    action = ErrorAction.ESCALATE

    def __init__(self, subtask_id: str, iterations: int, **kwargs) -> None:
        super().__init__(
            f"Subtask {subtask_id}: {iterations} iterations failed",
            details={"subtask_id": subtask_id, "iterations": iterations},
            **kwargs,
        )


class EscalationRequestedError(AgentError):
    """Явный запрос эскалации от Review'ера."""
    code = "ESCALATION_REQUESTED"
    action = ErrorAction.ESCALATE


# ─── Persistence ─────────────────────────────────────────────────────────────

class PersistenceError(AgentError):
    """PostgresSaver не смог сохранить/прочитать state."""
    code = "PERSISTENCE_ERROR"
    action = ErrorAction.ABORT  # без persistence — продолжать нельзя


# ─── Mapping: error → escalate reason ────────────────────────────────────────

def error_to_escalate_reason(err: AgentError) -> Literal[
    "max_iterations_exceeded",
    "critical_findings_count",
    "schema_violation_loop",
    "tool_error",
    "llm_unavailable",
    "budget_exceeded",
    "manual_request",
]:
    """Преобразовать ошибку в reason для EscalateResult (Шаг 4)."""
    if isinstance(err, MaxIterationsExceededError):
        return "max_iterations_exceeded"
    if isinstance(err, SchemaViolationError):
        return "schema_violation_loop"
    if isinstance(err, LLMBudgetExceededError):
        return "budget_exceeded"
    if isinstance(err, LLMUnavailableError):
        return "llm_unavailable"
    if isinstance(err, ToolError):
        return "tool_error"
    # critical_findings_count — ставится роутером review, не ошибкой
    # manual_request — пользователь сам запросил эскалацию
    return "tool_error"
```

## 3. Retry-логика — единое место

```python
# packages/orchestrator/src/orchestrator/retry.py
"""Retry-логика для всех ошибок с action=RETRY.

Не spread'ится по коду — единая функция.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, TypeVar

from .errors import (
    AgentError, ErrorAction,
    LLMRateLimitError, ToolTimeoutError, ToolConnectionError,
    LLMUnavailableError,
)

log = logging.getLogger(__name__)

T = TypeVar("T")


RETRYABLE_ERRORS = (
    ToolTimeoutError,
    ToolConnectionError,
    LLMUnavailableError,
    LLMRateLimitError,
)


async def with_retry(
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    on_retry: Callable[[Exception, int], None] | None = None,
) -> T:
    """Выполнить func с retry для retryable ошибок.

    Логика:
    - LLMRateLimitError → delay = retry_after (если есть)
    - ToolTimeoutError → exponential backoff (base * 2^attempt)
    - ToolConnectionError → linear backoff (base * attempt)
    - LLMUnavailableError → exponential backoff
    - Другие AgentError с action=RETRY → exponential backoff
    - action=ESCALATE/ABORT → raise immediately
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await func()
        except AgentError as err:
            last_error = err
            if err.action != ErrorAction.RETRY:
                raise
            if attempt == max_attempts:
                # Превратили retryable в escalate
                log.warning(
                    "Retry exhausted: %s (code=%s, attempt=%d/%d)",
                    err, err.code, attempt, max_attempts,
                )
                raise MaxIterationsExceededError(
                    subtask_id=str(err.details.get("subtask_id", "unknown")),
                    iterations=max_attempts,
                ) from err

            delay = _compute_delay(err, attempt, base_delay, max_delay)
            log.info(
                "Retry %d/%d after %.1fs: %s (code=%s)",
                attempt, max_attempts, delay, err, err.code,
            )
            if on_retry:
                on_retry(err, attempt)
            await asyncio.sleep(delay)
        except Exception as err:
            # Не AgentError — не retry'им
            raise

    # Unreachable, но для mypy
    assert last_error is not None
    raise last_error


def _compute_delay(
    err: AgentError,
    attempt: int,
    base: float,
    max_delay: float,
) -> float:
    if isinstance(err, LLMRateLimitError):
        return min(err.details.get("retry_after") or base, max_delay)
    if isinstance(err, ToolConnectionError):
        return min(base * attempt, max_delay)
    # exponential backoff
    return min(base * (2 ** (attempt - 1)), max_delay)
```

## 4. Persistence — PostgresSaver

```python
# packages/orchestrator/src/orchestrator/persistence.py
"""PostgresSaver wrapper для LangGraph checkpoint'ов.

Схема таблицы — управляется LangGraph, мы только оборачиваем.
Миграции — через alembic (см. migrations/).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.base import BaseCheckpointSaver

from .errors import PersistenceError


class PersistenceManager:
    """Управление Postgres-соединением для checkpoint'ов.

    Использование:
        async with PersistenceManager(dsn) as pm:
            checkpointer = pm.get_checkpointer()
            graph = build_graph(checkpointer=checkpointer)
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._saver: AsyncPostgresSaver | None = None

    async def __aenter__(self) -> "PersistenceManager":
        try:
            self._saver = AsyncPostgresSaver.from_conn_string(self.dsn)
            await self._saver.setup()  # создать таблицы, если нет
        except Exception as exc:
            raise PersistenceError(
                f"Cannot connect to Postgres: {exc}",
                details={"dsn": _mask_dsn(self.dsn)},
            ) from exc
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._saver:
            await self._saver.__aexit__(*args)
            self._saver = None

    def get_checkpointer(self) -> BaseCheckpointSaver:
        if self._saver is None:
            raise PersistenceError("PersistenceManager not entered")
        return self._saver


def _mask_dsn(dsn: str) -> str:
    """Скрыть пароль в DSN для логов."""
    if "@" in dsn and "://" in dsn:
        prefix, _, rest = dsn.partition("://")
        creds, _, host_part = rest.partition("@")
        if ":" in creds:
            user, _, _ = creds.partition(":")
            return f"{prefix}://{user}:***@{host_part}"
    return dsn
```

## 5. Схема Postgres-таблицы

LangGraph `AsyncPostgresSaver` создаёт свою схему (см. документацию LangGraph). Нам важны 3 таблицы:

```sql
-- Создаётся автоматически AsyncPostgresSaver.setup()
-- Приведено для понимания, не для ручного создания.

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint BYTEA,
    metadata JSONB,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel)
);

CREATE TABLE IF NOT EXISTS migration_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version INTEGER NOT NULL,
    type TEXT,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx ON checkpoints (thread_id);
CREATE INDEX IF NOT EXISTS checkpoints_thread_checkpoint_idx
    ON checkpoints (thread_id, checkpoint_id);
```

### 5.1. Миграция TaskState

`TaskState` сериализуется в `checkpoint` BYTEA (через pickle или JSON — LangGraph выбирает). При изменении полей `TaskState`:

- **Добавление опционального поля** — обратно-совместимо, старые checkpoint'ы грузятся
- **Удаление поля** — обратно-совместимо, поле просто не используется
- **Переименование поля** — breaking change, требуется migration script
- **Изменение типа** — breaking change, требуется migration script

Для breaking changes — alembic migration:

```python
# migrations/versions/001_rename_subtask_id_to_id.py
"""Rename subtasks[].id field (breaking change in TaskState v0.2).

Раньше: subtasks: [{subtask_id: "...", ...}]
Теперь: subtasks: [{id: "...", ...}]
"""
import json
import pickle
import psycopg
from alembic import op


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute("SELECT thread_id, checkpoint_id, checkpoint FROM checkpoints").fetchall()
    for thread_id, checkpoint_id, checkpoint_bytes in rows:
        # Десериализация LangGraph checkpoint'а
        checkpoint = pickle.loads(checkpoint_bytes)
        channel_values = checkpoint.get("channel_values", {})
        subtasks = channel_values.get("subtasks", [])
        changed = False
        for st in subtasks:
            if "subtask_id" in st and "id" not in st:
                st["id"] = st.pop("subtask_id")
                changed = True
        if changed:
            new_bytes = pickle.dumps(checkpoint)
            conn.execute(
                "UPDATE checkpoints SET checkpoint = %s WHERE thread_id = %s AND checkpoint_id = %s",
                (new_bytes, thread_id, checkpoint_id),
            )


def downgrade() -> None:
    # Обратная миграция
    pass
```

## 6. Эскалация — формат PR

```python
# packages/orchestrator/src/orchestrator/nodes/escalate.py
"""Escalate node — создаёт PR с меткой needs-human-review.

Формат PR body — структурированный, для ревьюера.
"""
from __future__ import annotations

import json
from typing import Any

from ..state import TaskState
from ..errors import error_to_escalate_reason


ESCALATE_PR_TEMPLATE = """# Эскалация: требуется ручная проверка

## Причина
{reason}

## Задача
- **Описание**: {description}
- **Конфигурация**: {config_name} {config_version}
- **Подзадача**: {subtask_name} (`{subtask_id}`)
- **Итераций сделано**: {iterations_count}

## История итераций
{iterations_log}

## Рекомендуемые действия
{suggested_actions}

## Что уже сделано
- Plan: ✅
- Gather: ✅
- Code: ✅ (но не прошёл валидацию или ревью)
- Validate: {validate_status}
- Review: {review_status}

## Метаданные
- task_id: `{task_id}`
- thread_id: `{thread_id}`
- timestamp: {timestamp}
"""


async def escalate_node(state: TaskState) -> dict[str, Any]:
    """Создать PR с меткой needs-human-review."""
    subtask = state.current_subtask
    assert subtask is not None

    reason = state.review_result.get("escalate_reason", "manual_request") if state.review_result else "max_iterations_exceeded"

    # Лог итераций
    iterations_log = _format_iterations(state.iterations)

    # Рекомендации
    suggested_actions = _suggest_actions(reason, state)

    # Тело PR
    pr_body = ESCALATE_PR_TEMPLATE.format(
        reason=reason,
        description=state.description,
        config_name=state.config_name,
        config_version=state.config_version,
        subtask_name=subtask.name,
        subtask_id=subtask.id,
        iterations_count=len(state.iterations),
        iterations_log=iterations_log,
        suggested_actions=suggested_actions,
        validate_status="✅" if state.validation_passed else "❌",
        review_status="❌" if not state.review_passed else "—",
        task_id=state.task_id,
        thread_id=state.trace_metadata.get("thread_id", "unknown"),
        timestamp=state.updated_at.isoformat(),
    )

    # Git operations через COMMITTER tools
    from ..tool_groups import AgentRole
    from ..tool_provider import make_tool_provider
    provider = make_tool_provider(AgentRole.COMMITTER)

    # create_branch + commit (с кодом последней итерации) + open_pr (с label needs-human-review)
    branch_name = f"escalation/{state.task_id[:8]}-{subtask.id[:8]}"
    last_code = state.iterations[-1].code if state.iterations else ""

    # ... вызовы git tools
    # result = await provider.get_tools()[0] ... (create_branch, commit, open_pr)

    return {
        "fsm_state": "escalated",
        "escalate_result": {
            "subtask_id": subtask.id,
            "reason": reason,
            "iteration_log": [it.model_dump(mode="json") for it in state.iterations],
            "pr_url": None,  # заполнится после git.open_pr
            "suggested_actions": suggested_actions,
        },
    }


def _format_iterations(iterations: list) -> str:
    if not iterations:
        return "Итераций не было."
    lines = []
    for it in iterations:
        findings_count = len(it.failed_checks)
        lines.append(
            f"### Итерация {it.number}\n"
            f"- Сгенерировано {len(it.code.splitlines())} строк\n"
            f"- Failed checks: {findings_count}\n"
            f"- Edit distance vs prev: {it.edit_distance_vs_prev:.0%}\n"
        )
    return "\n".join(lines)


def _suggest_actions(reason: str, state: TaskState) -> str:
    suggestions = {
        "max_iterations_exceeded": (
            "1. Проверьте последние 2 итерации — если edit distance <5%, "
            "модель топчется. Возможно, нужно упростить подзадачу в Plan.\n"
            "2. Если все итерации упали на одном правиле BSL LS — "
            "добавьте пример в KB patterns."
        ),
        "critical_findings_count": (
            "1. Проверьте findings в Review — если они все одного типа, "
            "возможно, паттерн в KB неполный.\n"
            "2. Перепроверьте, что Gather дал Coder'у нужный паттерн."
        ),
        "schema_violation_loop": (
            "1. Проверьте JSON Schema для Coder'а (knowledge-base/schemas/code-output.schema.json).\n"
            "2. Возможно, схема слишком сложная — упростите."
        ),
        "tool_error": (
            "1. Проверьте, что все MCP-серверы запущены: `1c-ai mcp serve`.\n"
            "2. Проверьте логи BSL LS Java-процесса."
        ),
        "llm_unavailable": (
            "1. Проверьте connectivity к LLM-провайдеру.\n"
            "2. Если budget exceeded — пополните счёт."
        ),
        "budget_exceeded": (
            "1. Превышен token budget. Проверьте LangSmith trace — какие вызовы самые дорогие.\n"
            "2. Возможно, Gather собрал слишком большой контекст."
        ),
        "manual_request": (
            "Эскалация запрошена явно. Проверьте rationale в Review."
        ),
    }
    return suggestions.get(reason, "Проверьте логи и state в Postgres.")
```

## 7. Конфигурация persistence

```python
# packages/orchestrator/src/orchestrator/config.py
"""Конфигурация persistence и retry."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PersistenceConfig:
    """Настройки PostgresSaver."""
    dsn: str = os.environ.get(
        "1C_AI_AGENT_PG_DSN",
        "postgresql://agent:agent@localhost:5432/agent",
    )
    schema_name: str = "agent"
    pool_size: int = 10


@dataclass(frozen=True)
class RetryConfig:
    """Настройки retry-логики."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0


@dataclass(frozen=True)
class LLMConfig:
    """Настройки LLM."""
    model_name: str = os.environ.get("1C_AI_AGENT_LLM_MODEL", "gpt-4o-mini")
    api_key: str = os.environ.get("OPENAI_API_KEY", "")
    base_url: str | None = os.environ.get("1C_AI_AGENT_LLM_BASE_URL")
    max_tokens: int = 8000
    temperature: float = 0.2
    token_budget_per_task: int = 200_000


@dataclass(frozen=True)
class OrchestratorConfig:
    """Полная конфигурация orchestrator'а."""
    persistence: PersistenceConfig = PersistenceConfig()
    retry: RetryConfig = RetryConfig()
    llm: LLMConfig = LLMConfig()
    enable_langsmith: bool = bool(os.environ.get("LANGSMITH_API_KEY"))
    langsmith_project: str = os.environ.get("LANGSMITH_PROJECT", "1c-ai-agent")
```

## 8. Граф pipeline с error handling

```python
# packages/orchestrator/src/orchestrator/graph.py (расширение из Шага 4)
"""Сборка графа с обработкой ошибок.

Каждый узел оборачивается в error_handler, который:
1. Ловит AgentError
2. Логирует в structlog
3. Решает: retry / escalate / abort
4. Передаёт в state для следующего роутера
"""
from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable

from langgraph.graph import StateGraph, END
from .state import TaskState
from .errors import (
    AgentError, ErrorAction,
    MaxIterationsExceededError, PersistenceError,
)
from .retry import with_retry

log = logging.getLogger(__name__)


def error_handler(node_fn: Callable) -> Callable:
    """Декоратор для узлов LangGraph — ловит ошибки и обновляет state."""
    @wraps(node_fn)
    async def wrapper(state: TaskState) -> dict[str, Any]:
        try:
            return await with_retry(lambda: node_fn(state))
        except MaxIterationsExceededError as err:
            log.warning("Max iterations exceeded in %s: %s", node_fn.__name__, err)
            return {
                "fsm_state": "escalated",
                "escalate_reason": err.code.lower(),
                "trace_metadata": {
                    **state.trace_metadata,
                    "last_error": err.code,
                    "last_error_details": err.details,
                },
            }
        except AgentError as err:
            log.error("AgentError in %s: %s (action=%s)", node_fn.__name__, err, err.action)
            if err.action == ErrorAction.ABORT:
                return {
                    "fsm_state": "failed",
                    "trace_metadata": {
                        **state.trace_metadata,
                        "last_error": err.code,
                        "abort_reason": str(err),
                    },
                }
            # ESCALATE
            return {
                "fsm_state": "escalated",
                "escalate_reason": err.code.lower(),
                "trace_metadata": {
                    **state.trace_metadata,
                    "last_error": err.code,
                    "last_error_details": err.details,
                },
            }
        except PersistenceError as err:
            log.critical("Persistence error: %s", err)
            return {"fsm_state": "failed"}
        except Exception as err:
            log.exception("Unexpected error in %s", node_fn.__name__)
            return {
                "fsm_state": "failed",
                "trace_metadata": {
                    **state.trace_metadata,
                    "last_error": "UNEXPECTED",
                    "abort_reason": str(err),
                },
            }
    return wrapper


def build_graph(checkpointer=None) -> StateGraph:
    """Собрать pipeline graph с error handling."""
    from .nodes import (
        preflight_node, plan_node, gather_node, code_node,
        validate_node, review_node, commit_node,
        escalate_node, next_subtask_node, retry_node,
    )
    from .routers import (
        route_after_validate, route_after_review,
        route_after_retry, route_after_commit,
    )

    graph = StateGraph(TaskState)

    # Узлы — обёрнутые в error_handler
    graph.add_node("preflight", error_handler(preflight_node))
    graph.add_node("plan", error_handler(plan_node))
    graph.add_node("gather", error_handler(gather_node))
    graph.add_node("code", error_handler(code_node))
    graph.add_node("validate", error_handler(validate_node))
    graph.add_node("review", error_handler(review_node))
    graph.add_node("retry", error_handler(retry_node))
    graph.add_node("commit", error_handler(commit_node))
    graph.add_node("escalate", error_handler(escalate_node))
    graph.add_node("next_subtask", error_handler(next_subtask_node))

    # Рёбра — те же, что в Шаге 4
    graph.set_entry_point("preflight")
    graph.add_edge("preflight", "plan")
    graph.add_edge("plan", "gather")
    graph.add_edge("gather", "code")
    graph.add_edge("code", "validate")

    graph.add_conditional_edges("validate", route_after_validate,
                                 {"review": "review", "retry": "retry"})
    graph.add_conditional_edges("review", route_after_review,
                                 {"commit": "commit", "retry": "retry", "escalate": "escalate"})
    graph.add_conditional_edges("retry", route_after_retry,
                                 {"code": "code", "escalate": "escalate"})
    graph.add_conditional_edges("commit", route_after_commit,
                                 {"next_subtask": "next_subtask", "end": END})
    graph.add_edge("next_subtask", "gather")
    graph.add_edge("escalate", END)

    return graph.compile(checkpointer=checkpointer)
```

## 9. Тесты

```python
# tests/orchestrator/test_errors.py
import pytest
from orchestrator.errors import (
    AgentError, ErrorAction,
    ToolTimeoutError, LLMRateLimitError, MaxIterationsExceededError,
    error_to_escalate_reason,
)
from orchestrator.retry import with_retry


class TestErrorTaxonomy:
    def test_tool_timeout_is_retryable(self):
        err = ToolTimeoutError("bsl_ls.lint", 60)
        assert err.action == ErrorAction.RETRY
        assert err.code == "TOOL_TIMEOUT"

    def test_role_forbidden_is_abort(self):
        from orchestrator.errors import RoleForbiddenError
        err = RoleForbiddenError("CODER", "metadata.get_metadata")
        assert err.action == ErrorAction.ABORT

    def test_budget_exceeded_is_escalate(self):
        from orchestrator.errors import LLMBudgetExceededError
        err = LLMBudgetExceededError(used=250_000, limit=200_000)
        assert err.action == ErrorAction.ESCALATE

    def test_error_to_escalate_reason_mapping(self):
        err = MaxIterationsExceededError("st-1", 3)
        assert error_to_escalate_reason(err) == "max_iterations_exceeded"


class TestRetry:
    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self):
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ToolTimeoutError("test.tool", 5)
            return "ok"

        result = await with_retry(flaky, max_attempts=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_max_iterations(self):
        async def always_fails():
            raise ToolTimeoutError("test.tool", 5)

        with pytest.raises(MaxIterationsExceededError):
            await with_retry(always_fails, max_attempts=2, base_delay=0.01)

    @pytest.mark.asyncio
    async def test_non_retryable_raises_immediately(self):
        from orchestrator.errors import RoleForbiddenError

        async def forbidden():
            raise RoleForbiddenError("CODER", "metadata.get_metadata")

        with pytest.raises(RoleForbiddenError):
            await with_retry(forbidden, max_attempts=3, base_delay=0.01)

    @pytest.mark.asyncio
    async def test_rate_limit_uses_retry_after(self):
        delays: list[float] = []

        async def rate_limited():
            raise LLMRateLimitError(retry_after=42)

        # monkeypatch asyncio.sleep чтобы ловить delay
        import orchestrator.retry as retry_mod
        original_sleep = retry_mod.asyncio.sleep

        async def fake_sleep(delay):
            delays.append(delay)

        retry_mod.asyncio.sleep = fake_sleep
        try:
            with pytest.raises(MaxIterationsExceededError):
                await with_retry(rate_limited, max_attempts=2, base_delay=1.0)
        finally:
            retry_mod.asyncio.sleep = original_sleep

        assert delays[0] == 42  # retry_after, не base*2^0


# tests/orchestrator/test_persistence.py
class TestPersistence:
    @pytest.mark.asyncio
    async def test_persistence_manager_lifecycle(self, monkeypatch):
        """Mock AsyncPostgresSaver — проверяем lifecycle."""
        # ... mock setup
        pass

    def test_mask_dsn_hides_password(self):
        from orchestrator.persistence import _mask_dsn
        dsn = "postgresql://user:secret@host:5432/db"
        masked = _mask_dsn(dsn)
        assert "secret" not in masked
        assert "***" in masked
```

## 10. Взаимосвязь с другими шагами

| Шаг | Связь |
|---|---|
| Шаг 4 (Pipeline contracts) | `EscalateResult.reason` использует коды из таксономии; `error_handler` decorator оборачивает все узлы |
| Шаг 5 (MCP tool contracts) | `error_contract` каждого tool (`exception` / `error_dict` / `empty_result`) → транслируется в `ToolError` подклассы |
| Шаг 6 (TOOL_GROUPS) | `RoleForbiddenError` — если роль попыталась вызвать неразрешённый tool |
| Шаг 8 (Facade) | `_next_action` после escalate → `data_status` (показать, что pipeline остановлен) |

## 11. Что НЕ делает этот шаг

- **Не реализует MCP-серверы** — это шаг 5
- **Не управляет TOOL_GROUPS** — это шаг 6
- **Не хранит configs/indices** — это `data_layer` (PathManager + ConfigRegistry)
- **Не реализует LLM-вызовы** — это `nodes/*.py` (использует `LLMConfig`)

Этот шаг — **последняя линия обороны**. Когда всё остальное спроектировано, этот шаг гарантирует, что pipeline не теряет задачи при сбоях.

---

**Шаг 9 завершён.** Все 9 шагов проектирования готовы. Финальная задача — ADR-каталог из 13 записей.
