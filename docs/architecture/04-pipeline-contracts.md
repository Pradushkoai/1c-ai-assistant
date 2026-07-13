# Шаг 4 — Pipeline state + node contracts

> **ADR-0009:** Pipeline contracts — центральный контракт проекта
> **Зависимости:** Шаг 2 (`BslModule`, `ObjectRef`), Шаг 3 (`PathManager`)
> **Артефакт:** `packages/orchestrator/src/orchestrator/{state.py, contracts.py, routers.py}`

## 1. Почему это центральный шаг

`orchestrator/contracts.py` — **самый часто импортируемый контракт** проекта. От него зависят:

- Шаг 5 (MCP tool contracts) — `GatherResult` содержит результаты MCP-вызовов
- Шаг 6 (TOOL_GROUPS) — роли агентов определяются узлами pipeline
- Шаг 8 (Facade) — lifecycle tools возвращают «срезы» этих контрактов
- Шаг 9 (Error taxonomy) — ошибки классифицируются по типу узла

Если контракты стыкуются плохо — pipeline не соберётся. Если state мутируемый — LangGraph checkpoint'ы ломаются. Если `route_after_*` возвращают неправильный Literal — graph compile падает.

**Принцип:** каждый узел имеет **строго один** input-тип и **строго один** output-тип. Роутеры — чистые функции `state -> Literal[...]`.

## 2. FSM — состояния конвейера

```python
# packages/orchestrator/src/orchestrator/state.py (часть 1)
"""FSM состояния pipeline.

Состояния зафиксированы в enum. LLM не может их менять.
Переходы — только через детерминированные роутеры.
"""
from enum import Enum


class FSMState(str, Enum):
    """Состояния pipeline. Сохраняются в TaskState.fsm_state."""
    INIT = "init"                    # создана задача, preflight ещё не прошёл
    PLANNING = "planning"            # Plan subgraph работает
    GATHERING = "gathering"          # Gather subgraph для текущей подзадачи
    CODING = "coding"                # Code node для текущей подзадачи
    VALIDATING = "validating"        # Validate subgraph
    REVIEWING = "reviewing"          # Review subgraph
    COMMITTING = "committing"        # Commit node
    ESCALATED = "escalated"          # нужна человеческая проверка
    DONE = "done"                    # задача завершена успешно
    FAILED = "failed"                # критическая ошибка (не ecalation, а crash)
```

## 3. TaskState — главное состояние

```python
# packages/orchestrator/src/orchestrator/state.py (часть 2)
"""TaskState — главное состояние pipeline.

Иммутабельное (frozen=True). Каждый узел возвращает НОВЫЙ state,
не мутирует старый. LangGraph checkpoint'ы сериализуют это в Postgres.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from parsers.models import ObjectRef, BslModule


class Subtask(BaseModel):
    """Подзадача — результат декомпозиции Plan'ом."""
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    id: str = Field(description="UUID подзадачи")
    name: str = Field(description="Человеческое имя, например 'ОбработкаПроведения'")
    target_module: ObjectRef = Field(description="Catalog.Контрагенты.ObjectModule")
    description: str = Field(description="Что нужно сделать")
    inputs: list[str] = Field(default_factory=list, description="Что подаётся на вход")
    outputs: list[str] = Field(default_factory=list, description="Что ожидается на выходе")
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="Критерии приёмки — используются в Test/Review"
    )
    json_schema: dict[str, Any] | None = Field(
        default=None,
        description="JSON Schema для structured_output Coder'а"
    )
    constraints: SubtaskConstraints | None = None
    max_iterations: int = Field(default=3, ge=1, le=5)
    status: Literal["pending", "in_progress", "done", "failed", "escalated"] = "pending"


class SubtaskConstraints(BaseModel):
    """Ограничения подзадачи — инжектируются в промпт."""
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    dont_list: list[str] = Field(default_factory=list, description="Что НЕ делать")
    must_list: list[str] = Field(default_factory=list, description="Что ОБЯЗАТЕЛЬНО сделать")
    available_modules: list[str] = Field(
        default_factory=list,
        description="Имена общих модулей, которые можно вызывать"
    )
    target_context: str = Field(
        default="server",
        description="server | thin_client | mobile_client — для check_method_availability"
    )


class Iteration(BaseModel):
    """Итерация генерации кода — одна попытка Coder'а для подзадачи."""
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    number: int = Field(ge=1, description="1 = первая попытка, 2 = первый retry, ...")
    code: str = Field(description="Сгенерированный BSL-код")
    llm_response: dict[str, Any] = Field(description="Полный ответ LLM (для трассировки)")
    bsl_ls_diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    review_findings: list[dict[str, Any]] = Field(default_factory=list)
    test_result: bool | None = None  # без Vanessa — всегда None
    edit_distance_vs_prev: float = Field(default=0.0, description="0..1, мера изменения кода")
    failed_checks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Конкретные ошибки для retry-промпта"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskState(BaseModel):
    """Главное состояние pipeline. Передаётся между всеми узлами.

    Frozen. Каждый узел возвращает новый TaskState через model_copy(update={...}).
    """
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    # Идентификация
    task_id: str = Field(description="UUID задачи")
    description: str = Field(description="Исходный промпт пользователя")
    config_name: str = Field(description="Имя конфигурации: 'ut11'")
    config_version: str = Field(description="Версия конфигурации: '4.5.3'")
    platform_version: str = Field(description="Версия платформы: '8.3.20'")

    # Декомпозиция
    subtasks: list[Subtask] = Field(default_factory=list)
    current_subtask_idx: int = Field(default=0, ge=0)

    # Итерации
    current_iteration: int = Field(default=0, ge=0, description="0 = ещё не было попыток")
    iterations: list[Iteration] = Field(default_factory=list, description="Только для текущей подзадачи")

    # FSM
    fsm_state: FSMState = FSMState.INIT

    # Фокус-контроль
    constraints_reminder: str = Field(
        default="",
        description="Строка, добавляемая в начало каждого промпта retry"
    )

    # Роутер-сигналы (заполняются узлами, читаются роутерами)
    validation_passed: bool = False
    review_passed: bool = False
    critical_findings: int = 0

    # Промежуточные результаты (для facade и для тестов)
    plan_result: dict[str, Any] | None = None
    gather_result: dict[str, Any] | None = None
    validate_result: dict[str, Any] | None = None
    review_result: dict[str, Any] | None = None
    commit_result: dict[str, Any] | None = None

    # Метаданные
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    parent_checkpoint_id: str | None = None

    # Трассировка (для LangSmith)
    trace_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def current_subtask(self) -> Subtask | None:
        """Текущая подзадача или None, если все выполнены."""
        if self.current_subtask_idx >= len(self.subtasks):
            return None
        return self.subtasks[self.current_subtask_idx]
```

## 4. Node contracts — вход/выход каждого узла

```python
# packages/orchestrator/src/orchestrator/contracts.py
"""Контракты узлов pipeline.

Каждый узел:
- принимает TaskState (+ опционально config)
- возвращает dict, который LangGraph merge'ит в новый state

Чтобы избежать путаницы, контракты описаны как Pydantic-модели Result.
Узлы возвращают dict, соответствующий Result.model_dump().
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from parsers.models import ObjectRef, BslModule, PlatformMethod
from .state import Subtask, Iteration


class _ResultBase(BaseModel):
    """Базовый класс для всех Result'ов."""
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


# ─── Plan ────────────────────────────────────────────────────────────────────

class PlanResult(_ResultBase):
    """Результат Plan subgraph.

    Plan возвращает декомпозицию задачи на подзадачи.
    """
    subtasks: list[Subtask] = Field(description="Упорядоченный список подзадач")
    decomposition_strategy: Literal["feature", "refactor", "bugfix", "single"] = Field(
        description="Какая стратегия декомпозиции выбрана"
    )
    rationale: str = Field(description="Почему такая декомпозиция (для трассировки)")
    plan_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Доп. метаданные (например, dep_graph_snapshot)"
    )


# ─── Gather ──────────────────────────────────────────────────────────────────

class GatheredMetadata(_ResultBase):
    """Срез метаданных из metadata-server."""
    target_object: dict[str, Any] = Field(description="Метаданные target-объекта")
    related_objects: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Связанные объекты (для контекста)"
    )
    dependency_graph_slice: dict[str, Any] | None = None


class GatheredCode(_ResultBase):
    """Срез похожего кода из codebase-server."""
    similar_modules: list[BslModule] = Field(
        default_factory=list,
        description="Похожие модули (semantic_search)"
    )
    api_reference: list[dict[str, Any]] = Field(
        default_factory=list,
        description="API-справочник по общим модулям, которые можно вызывать"
    )


class GatheredKnowledge(_ResultBase):
    """Срез из kb-server."""
    patterns: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Подходящие паттерны (YAML из knowledge-base/patterns/)"
    )
    antipatterns: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Антипаттерны, релевантные задаче"
    )
    method_availability: dict[str, PlatformMethod] = Field(
        default_factory=dict,
        description="Метод → карточка (для check_method_availability в Coder)"
    )


class GatherResult(_ResultBase):
    """Результат Gather subgraph — собранный контекст для Coder."""
    subtask_id: str
    metadata: GatheredMetadata
    code: GatheredCode
    knowledge: GatheredKnowledge
    context_summary: str = Field(
        description="Краткое summary контекста — инжектируется в system prompt Coder"
    )
    mcp_calls_made: list[str] = Field(
        default_factory=list,
        description="Какие MCP tools были вызваны (для трассировки)"
    )


# ─── Code ────────────────────────────────────────────────────────────────────

class CodeResult(_ResultBase):
    """Результат Code node — сгенерированный BSL-код."""
    subtask_id: str
    iteration_number: int = Field(ge=1)
    code: str = Field(description="Сгенерированный BSL-код")
    target_module: ObjectRef
    llm_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="model, tokens, latency — для метрик"
    )
    structured_output_valid: bool = Field(
        default=True,
        description="False = LLM нарушила JSON Schema, нужен retry"
    )


# ─── Validate ────────────────────────────────────────────────────────────────

class ValidationFinding(_ResultBase):
    """Одно замечание валидатора."""
    severity: Literal["critical", "warning", "info"]
    code: str = Field(description="BSL-WS-001, QUERY-IN-LOOP, ...")
    message: str
    line: int | None = None
    column: int | None = None
    # TD-S4.2-03: добавлен 'kb_standards' для 4-го валидатора (СТО/БСП).
    source: Literal["bsl_ls", "kb_antipatterns", "kb_standards", "custom_rules"]
    fix_hint: str | None = None


class ValidateResult(_ResultBase):
    """Результат Validate subgraph — fan-out/fan-in 4 валидаторов (TD-S4.2-03: добавлен standards)."""
    subtask_id: str
    iteration_number: int
    findings: list[ValidationFinding]
    passed: bool = Field(description="True = нет critical findings")
    severity_breakdown: dict[str, int] = Field(
        description="{'critical': N, 'warning': M, 'info': K}"
    )
    failed_checks: list[dict[str, Any]] = Field(
        description="Только failed — для retry-промпта Coder"
    )


# ─── Review ──────────────────────────────────────────────────────────────────

class ReviewFinding(_ResultBase):
    """Одно замечание рецензента."""
    severity: Literal["critical", "warning", "info"]
    category: Literal["antipattern", "context_violation", "pattern_mismatch", "style"]
    code: str
    message: str
    recommendation: str = Field(description="Что предложить LLM в retry")


class ReviewResult(_ResultBase):
    """Результат Review subgraph — LLM решает retry/escalate/proceed."""
    subtask_id: str
    iteration_number: int
    findings: list[ReviewFinding]
    decision: Literal["proceed", "retry", "escalate"]
    rationale: str = Field(description="Почему такое решение (для трассировки)")
    critical_findings: int = Field(ge=0)
    passed: bool = Field(description="True = decision == 'proceed'")


# ─── Commit ──────────────────────────────────────────────────────────────────

class CommitResult(_ResultBase):
    """Результат Commit node — git branch + commit + PR."""
    subtask_id: str
    branch_name: str
    commit_sha: str
    pr_url: str | None = None
    pr_number: int | None = None
    files_changed: list[str]
    diff_summary: str = Field(description="Краткая сводка изменений")


# ─── Escalate ────────────────────────────────────────────────────────────────

class EscalateResult(_ResultBase):
    """Результат Escalate node — PR с меткой needs-human-review."""
    subtask_id: str
    reason: Literal["max_iterations_exceeded", "critical_findings_count", "schema_violation_loop", "tool_error"]
    iteration_log: list[dict[str, Any]] = Field(description="История всех итераций")
    pr_url: str | None = None
    suggested_actions: list[str] = Field(
        default_factory=list,
        description="Что человек должен сделать руками"
    )
```

## 5. Роутеры — детерминированные Python-функции

```python
# packages/orchestrator/src/orchestrator/routers.py
"""Детерминированные роутеры — НЕ LLM.

Эти функции — единственное, что решает "куда идти дальше".
LLM в Review может "рекомендовать", но финальное решение — здесь.
"""
from __future__ import annotations

from typing import Literal
from .state import TaskState


def route_after_validate(state: TaskState) -> Literal["review", "retry"]:
    """После Validate: пройти в Review, либо назад в Code (retry)."""
    return "review" if state.validation_passed else "retry"


def route_after_review(state: TaskState) -> Literal["commit", "retry", "escalate"]:
    """После Review: commit, retry, или escalate.

    Логика:
    - decision == 'proceed' → commit
    - decision == 'retry' AND current_iteration < max → retry
    - decision == 'retry' AND current_iteration >= max → escalate
    - decision == 'escalate' → escalate
    """
    subtask = state.current_subtask
    if subtask is None:
        return "escalate"

    if state.review_passed:
        return "commit"

    if state.critical_findings >= 3:
        return "escalate"

    if state.current_iteration >= subtask.max_iterations:
        return "escalate"

    return "retry"


def route_after_retry(state: TaskState) -> Literal["code", "escalate"]:
    """После retry-узла: снова в Code, или escalate.

    Это защита от бесконечных циклов.
    """
    subtask = state.current_subtask
    if subtask is None:
        return "escalate"

    if state.current_iteration >= subtask.max_iterations:
        return "escalate"

    return "code"


def route_after_commit(state: TaskState) -> Literal["next_subtask", "end"]:
    """После Commit: следующая подзадача или завершение."""
    if state.current_subtask_idx + 1 < len(state.subtasks):
        return "next_subtask"
    return "end"
```

## 6. Граф pipeline — сборка

```python
# packages/orchestrator/src/orchestrator/graph.py
"""Сборка главного StateGraph.

Именно здесь — детерминированный backbone.
LLM живёт ВНУТРИ узлов, не ВЫШЕ них.
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver  # для тестов
from langgraph.checkpoint.postgres import PostgresSaver  # для production

from .state import TaskState, FSMState
from .routers import (
    route_after_validate,
    route_after_review,
    route_after_retry,
    route_after_commit,
)
from .nodes import (
    preflight_node,
    plan_node,           # mini-supervisor subgraph
    gather_node,         # mini-supervisor subgraph
    code_node,           # simple LLM node
    validate_node,       # parallel subgraph
    review_node,         # mini-supervisor subgraph
    commit_node,         # simple node
    escalate_node,
    next_subtask_node,
    retry_node,
)


def build_graph(checkpointer=None) -> StateGraph:
    """Собрать главный pipeline.

    checkpointer:
    - None / MemorySaver — для тестов
    - PostgresSaver — для production (Шаг 9)
    """
    graph = StateGraph(TaskState)

    # Узлы
    graph.add_node("preflight", preflight_node)
    graph.add_node("plan", plan_node)
    graph.add_node("gather", gather_node)
    graph.add_node("code", code_node)
    graph.add_node("validate", validate_node)
    graph.add_node("review", review_node)
    graph.add_node("retry", retry_node)
    graph.add_node("commit", commit_node)
    graph.add_node("escalate", escalate_node)
    graph.add_node("next_subtask", next_subtask_node)

    # Рёбра — детерминированный backbone
    graph.set_entry_point("preflight")
    graph.add_edge("preflight", "plan")
    graph.add_edge("plan", "gather")

    # Gather → Code (для каждой подзадачи)
    graph.add_edge("gather", "code")

    # Code → Validate
    graph.add_edge("code", "validate")

    # Validate → {review | retry}
    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {"review": "review", "retry": "retry"},
    )

    # Review → {commit | retry | escalate}
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {"commit": "commit", "retry": "retry", "escalate": "escalate"},
    )

    # Retry → {code | escalate}
    graph.add_conditional_edges(
        "retry",
        route_after_retry,
        {"code": "code", "escalate": "escalate"},
    )

    # Commit → {next_subtask | end}
    graph.add_conditional_edges(
        "commit",
        route_after_commit,
        {"next_subtask": "next_subtask", "end": END},
    )

    # next_subtask → gather (новая подзадача)
    graph.add_edge("next_subtask", "gather")

    # Escalate → END
    graph.add_edge("escalate", END)

    return graph.compile(checkpointer=checkpointer or MemorySaver())
```

## 7. Mini-supervisor subgraphs — план/gather/review

### 7.1. Plan subgraph

```python
# packages/orchestrator/src/orchestrator/nodes/plan.py
"""Plan — mini-supervisor subgraph.

Структура:
  plan_supervisor (LLM) → decompose (LLM, structured) → validate_plan (Python)

Если validate_plan находит ошибку —回到 supervisor с фидбеком.
Max 3 попытки декомпозиции.
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field
from typing import Literal

from ..contracts import PlanResult
from ..state import TaskState, Subtask


class PlanSupervisorDecision(BaseModel):
    """Решение supervisor'а — какая стратегия декомпозиции."""
    strategy: Literal["feature", "refactor", "bugfix", "single"]
    rationale: str
    expected_subtask_count: int = Field(ge=1, le=10)


class DecomposeOutput(BaseModel):
    """Structured output для decompose node."""
    subtasks: list[Subtask]


def plan_supervisor_node(state: TaskState) -> dict:
    """LLM: выбрать стратегию декомпозиции."""
    # ... вызов LLM с structured output PlanSupervisorDecision
    return {"plan_strategy": decision.strategy, "plan_rationale": decision.rationale}


def decompose_node(state: TaskState) -> dict:
    """LLM: сгенерировать подзадачи по выбранной стратегии."""
    # ... вызов LLM с structured output DecomposeOutput
    return {"raw_subtasks": output.subtasks}


def validate_plan_node(state: TaskState) -> dict:
    """Python: проверить структуру подзадач.

    Проверки:
    - каждая подзадача имеет id, target_module, acceptance_criteria
    - target_module валиден (есть в конфигурации)
    - json_schema (если есть) валидна
    - нет дубликатов id
    """
    subtasks = state.get("raw_subtasks", [])
    errors: list[str] = []

    seen_ids: set[str] = set()
    for st in subtasks:
        if st.id in seen_ids:
            errors.append(f"Duplicate subtask id: {st.id}")
        seen_ids.add(st.id)
        if not st.acceptance_criteria:
            errors.append(f"Subtask {st.id} has no acceptance_criteria")

    if errors:
        # Фидбек supervisor'у — retry
        return {"plan_errors": errors, "plan_attempts": state.get("plan_attempts", 0) + 1}

    return {"plan_result": PlanResult(
        subtasks=subtasks,
        decomposition_strategy=state["plan_strategy"],
        rationale=state["plan_rationale"],
    )}


def route_plan_retry(state: dict) -> Literal["supervisor", "end"]:
    """Если validate_plan нашёл ошибки — назад к supervisor (max 3 раза)."""
    if state.get("plan_errors") and state.get("plan_attempts", 0) < 3:
        return "supervisor"
    return "end"


def build_plan_subgraph() -> StateGraph:
    """Собрать Plan subgraph."""
    sg = StateGraph(dict)
    sg.add_node("supervisor", plan_supervisor_node)
    sg.add_node("decompose", decompose_node)
    sg.add_node("validate", validate_plan_node)

    sg.set_entry_point("supervisor")
    sg.add_edge("supervisor", "decompose")
    sg.add_edge("decompose", "validate")
    sg.add_conditional_edges("validate", route_plan_retry, {"supervisor": "supervisor", "end": END})

    return sg.compile(checkpointer=MemorySaver())
```

### 7.2. Gather subgraph — parallel fan-out

```python
# packages/orchestrator/src/orchestrator/nodes/gather.py
"""Gather — mini-supervisor + parallel fan-out к 3 MCP-серверам.

  gather_supervisor (LLM) → fan_out (asyncio) → merge_context (Python)

Supervisor решает, какие MCP звать. Если задача простая — можно пропустить
metadata (например, если target_module уже известен из Plan).
"""
from __future__ import annotations

import asyncio
from typing import Any
from pydantic import BaseModel, Field
from typing import Literal

from ..contracts import GatherResult, GatheredMetadata, GatheredCode, GatheredKnowledge
from ..state import TaskState


class GatherSupervisorDecision(BaseModel):
    """Решение supervisor'а — какие MCP звать."""
    need_metadata: bool = True
    need_codebase: bool = True
    need_kb: bool = True
    rationale: str


async def gather_supervisor_node(state: TaskState) -> dict:
    """LLM: решить, какие MCP нужны для текущей подзадачи."""
    # ... LLM с structured output GatherSupervisorDecision
    return {"gather_decision": decision.model_dump()}


async def fan_out_node(state: TaskState) -> dict:
    """Параллельный вызов MCP-серверов через asyncio.TaskGroup."""
    decision = GatherSupervisorDecision(**state["gather_decision"])
    subtask = state.current_subtask
    assert subtask is not None

    tasks: dict[str, asyncio.Task] = {}

    async with asyncio.TaskGroup() as tg:
        if decision.need_metadata:
            tasks["metadata"] = tg.create_task(_call_metadata_mcp(state, subtask))
        if decision.need_codebase:
            tasks["codebase"] = tg.create_task(_call_codebase_mcp(state, subtask))
        if decision.need_kb:
            tasks["kb"] = tg.create_task(_call_kb_mcp(state, subtask))

    results: dict[str, Any] = {}
    for name, task in tasks.items():
        results[name] = await task

    return {"gather_partial": results}


def merge_context_node(state: TaskState) -> dict:
    """Python: собрать финальный GatherResult из partial."""
    partial = state["gather_partial"]
    subtask = state.current_subtask
    assert subtask is not None

    metadata = GatheredMetadata(**partial.get("metadata", {"target_object": {}}))
    code = GatheredCode(**partial.get("codebase", {}))
    knowledge = GatheredKnowledge(**partial.get("kb", {}))

    # Сборка summary для system prompt Coder
    summary = _build_context_summary(metadata, code, knowledge, subtask)

    result = GatherResult(
        subtask_id=subtask.id,
        metadata=metadata,
        code=code,
        knowledge=knowledge,
        context_summary=summary,
        mcp_calls_made=list(partial.keys()),
    )
    return {"gather_result": result.model_dump()}


def _build_context_summary(
    metadata: GatheredMetadata,
    code: GatheredCode,
    knowledge: GatheredKnowledge,
    subtask: Subtask,
) -> str:
    """Сборка текстового summary для инъекции в prompt Coder'а.

    Структура:
    - Целевой объект (метаданные)
    - Похожий код (top-3 модуля)
    - Релевантные паттерны (название + краткое описание)
    - Доступные методы платформы (с availability)
    """
    lines: list[str] = []
    lines.append(f"## Целевой объект: {subtask.target_module}")
    lines.append(f"## Задача: {subtask.description}")
    # ... подробная сборка
    return "\n".join(lines)


# MCP-call helpers (вызывают tool_provider, который определён в Шаге 6)
async def _call_metadata_mcp(state: TaskState, subtask: Subtask) -> dict:
    # from ..tool_provider import get_tools_for_role
    # tools = get_tools_for_role(AgentRole.GATHERER)
    # result = await tools["metadata.get_metadata"](...)
    ...


async def _call_codebase_mcp(state: TaskState, subtask: Subtask) -> dict:
    ...


async def _call_kb_mcp(state: TaskState, subtask: Subtask) -> dict:
    ...


def build_gather_subgraph() -> StateGraph:
    """Собрать Gather subgraph."""
    sg = StateGraph(dict)
    sg.add_node("supervisor", gather_supervisor_node)
    sg.add_node("fan_out", fan_out_node)
    sg.add_node("merge", merge_context_node)

    sg.set_entry_point("supervisor")
    sg.add_edge("supervisor", "fan_out")
    sg.add_edge("fan_out", "merge")
    sg.add_edge("merge", END)

    return sg.compile()
```

## 8. Фокус-контроль — что видит каждый узел

Это **самое важное** в этом шаге. Зафиксируем явно:

| Узел | Видит | НЕ видит |
|---|---|---|
| `preflight` | TaskState (только meta-поля) | subtasks, iterations |
| `plan` (supervisor + decompose) | `description`, `config_name`, dep graph snapshot | BSL-код, метаданные объектов |
| `plan` (validate) | raw_subtasks (структура) | description, anything LLM-y |
| `gather` (supervisor) | current_subtask (target_module, description) | остальной TaskState |
| `gather` (fan_out) | то, что сказал supervisor | description, остальные подзадачи |
| `gather` (merge) | partial от MCP, current_subtask | description |
| `code` | GatherResult, SubtaskConstraints, prev Iteration (если retry) | description, другие подзадачи |
| `validate` | CodeResult (только код) | description, gather context |
| `review` (supervisor) | CodeResult, ValidateResult | description, original task |
| `review` (check_antipatterns) | code | что-либо другое |
| `review` (decide) | findings от check'ов | description |
| `commit` | CodeResult (для записи в файл) | description, gather context |
| `escalate` | все iterations, reason | — |

**Реализация фокус-контроля — в узлах.** Каждый узел явно достаёт из `TaskState` только нужные поля и передаёт в LLM-промпт только их. Это **не** автоматическая фильтрация — это дисциплина в коде.

Пример:

```python
# orchestrator/nodes/code.py
async def code_node(state: TaskState) -> dict:
    """Coder генерирует BSL-код.

    ВАЖНО: Coder не видит state.description или state.subtasks (кроме current).
    Только: GatherResult + SubtaskConstraints + prev Iteration.failed_checks.
    """
    subtask = state.current_subtask
    assert subtask is not None
    gather_result = GatherResult(**state.gather_result) if state.gather_result else None

    # Промпт собирается ТОЛЬКО из разрешённых полей
    prompt = build_coder_prompt(
        subtask=subtask,
        gather_result=gather_result,
        prev_iteration=state.iterations[-1] if state.iterations else None,
    )

    # Coder НЕ имеет MCP-инструментов (TOOL_GROUPS[CODER] = {})
    # Вызов LLM с structured_output
    llm_response = await llm.with_structured_output(CodeResult).ainvoke(prompt)

    return {
        "current_iteration": state.current_iteration + 1,
        "iterations": state.iterations + [Iteration(
            number=state.current_iteration + 1,
            code=llm_response.code,
            llm_response=llm_response.model_dump(),
        )],
    }
```

## 9. Checkpoint персистенция — сохранение между узлами

LangGraph автоматически сериализует `TaskState` между узлами. Для production — `PostgresSaver`, для тестов — `MemorySaver`. Подробности — Шаг 9.

Важно здесь:
- `TaskState` — Pydantic v2, сериализуется в JSON без потерь
- `datetime` — ISO 8601 (timezone-aware)
- `ObjectRef` — сериализуется как `{type, name}`, не как строка
- `BslModule` (в `Iteration`) — большой, но сериализуется полностью (для трассировки)

## 10. Тесты контрактов

```python
# tests/orchestrator/test_state.py
import pytest
from orchestrator.state import TaskState, Subtask, FSMState
from parsers.models import ObjectRef


class TestTaskStateFrozen:
    def test_state_is_frozen(self):
        state = TaskState(
            task_id="t1",
            description="Test",
            config_name="ut11",
            config_version="4.5.3",
            platform_version="8.3.20",
        )
        with pytest.raises(ValidationError):
            state.fsm_state = FSMState.DONE  # type: ignore

    def test_state_copy_for_update(self):
        state = TaskState(
            task_id="t1", description="Test",
            config_name="ut11", config_version="4.5.3", platform_version="8.3.20",
        )
        new_state = state.model_copy(update={"fsm_state": FSMState.PLANNING})
        assert new_state.fsm_state == FSMState.PLANNING
        assert state.fsm_state == FSMState.INIT  # оригинал не изменился


# tests/orchestrator/test_routers.py
class TestRouters:
    def test_route_after_validate_pass(self):
        state = _make_state(validation_passed=True)
        assert route_after_validate(state) == "review"

    def test_route_after_validate_fail(self):
        state = _make_state(validation_passed=False)
        assert route_after_validate(state) == "retry"

    def test_route_after_review_proceed(self):
        state = _make_state(review_passed=True)
        assert route_after_review(state) == "commit"

    def test_route_after_review_escalate_on_critical_count(self):
        state = _make_state(review_passed=False, critical_findings=3)
        assert route_after_review(state) == "escalate"

    def test_route_after_review_retry_under_limit(self):
        state = _make_state(
            review_passed=False, critical_findings=1,
            current_iteration=1, max_iterations=3,
        )
        assert route_after_review(state) == "retry"

    def test_route_after_review_escalate_at_limit(self):
        state = _make_state(
            review_passed=False, critical_findings=1,
            current_iteration=3, max_iterations=3,
        )
        assert route_after_review(state) == "escalate"


# tests/orchestrator/test_graph_compile.py
class TestGraph:
    def test_graph_compiles(self):
        from orchestrator.graph import build_graph
        graph = build_graph()
        assert graph is not None

    def test_graph_has_all_nodes(self):
        from orchestrator.graph import build_graph
        graph = build_graph()
        # LangGraph internals — проверяем, что узлы зарегистрированы
        node_names = set(graph.nodes.keys())
        expected = {"preflight", "plan", "gather", "code", "validate",
                    "review", "retry", "commit", "escalate", "next_subtask"}
        assert expected.issubset(node_names)
```

## 11. Взаимосвязь с другими шагами

| Шаг | Связь с Pipeline contracts |
|---|---|
| Шаг 5 (MCP tool contracts) | `GatherResult` содержит результаты MCP-вызовов — их форма определяется здесь |
| Шаг 6 (TOOL_GROUPS) | Роли агентов = узлы pipeline (PLANNER, GATHERER, CODER, ...) |
| Шаг 7 (KB-as-code) | `ReviewFinding.category` соответствует категориям KB |
| Шаг 8 (Facade) | `plan`, `gather`, `generate`, `validate`, `review` — facade-обёртки над этими узлами |
| Шаг 9 (Error taxonomy) | `EscalateResult.reason` — из таксономии ошибок |
| Шаг 9 (Persistence) | `TaskState` сериализуется в Postgres через `PostgresSaver` |

---

**Шаг 4 завершён.** Это был центральный шаг — самый объёмный и самый важный. Следующий — Шаг 5: контракты MCP tools, которые `gather_subgraph` вызывает параллельно.
