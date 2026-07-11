# Шаг 8 — Agent-Facade lifecycle tools

> **ADR-0013:** Agent-Facade — 7 lifecycle tools + `_next_action` для внешних клиентов
> **Зависимости:** Шаг 4 (узлы pipeline), Шаг 5 (MCP tool contracts для `run_cli` proxy), Шаг 6 (TOOL_GROUPS для проверки прав)
> **Артефакт:** `packages/mcp_servers/src/mcp_servers/facade/`

## 1. Зачем Facade

Внешний клиент (Cursor, Claude, Codex) подключается к нашему проекту через MCP. Если показать ему **все 19 tools** из 5 доменных серверов — LLM запутается:
- tool interference — модель вызывает не тот tool
- длинный контекст — описание 19 tools отъедает токены
- нет вменяемого workflow — LLM не знает, что за чем вызывать

Facade решает это через **2 приёма**:

1. **7 lifecycle tools** вместо 19 — глаголы высокого уровня (`plan`, `gather`, `generate`, `validate`, `review`, `explain`, `run_cli`)
2. **`_next_action` паттерн** — каждый tool возвращает не только результат, но и **одно конкретное следующее действие**

LLM внешнего клиента идёт по workflow как по рельсам: `plan` → `gather` → `generate` → `validate` → `review` → commit. Без Facade это был бы хаотический поиск.

## 2. 7 lifecycle tools — карта

| # | Tool | Что делает | `_next_action` |
|---|---|---|---|
| 1 | `plan(task, config)` | Декомпозиция задачи на подзадачи | `gather` |
| 2 | `gather(plan_id, subtask_id)` | Сбор контекста для подзадачи | `generate` |
| 3 | `generate(plan_id, subtask_id)` | LLM генерация кода | `validate` |
| 4 | `validate(artifact_id)` | BSL LS + KB-антипаттерны | `review` (pass) или `generate` (retry) |
| 5 | `review(artifact_id)` | LLM-рецензент | `commit` (proceed) или `generate` (retry) |
| 6 | `explain(artifact_or_query)` | Объяснить существующий код | — |
| 7 | `run_cli(tool_name, args)` | Proxy к скрытым tools | — |
| + | `data_status()` | Статус данных проекта | — |

**Coder'а среди них нет.** `generate` — это обёртка над `code_node`, но Coder живёт ВНУТРИ pipeline. Внешний клиент не видит «Coder» как отдельный tool — он видит `generate`, который запускает весь мини-pipeline `gather → code → validate` внутри.

## 3. Структура Facade

```
packages/mcp_servers/src/mcp_servers/facade/
├── __init__.py
├── server.py              ← MCP server entry point (stdio)
├── handlers.py            ← 7 lifecycle handlers
├── next_action.py         ← _next_action builder
└── contracts.py           ← input/output для facade tools
```

## 4. Контракты Facade

```python
# packages/mcp_servers/src/mcp_servers/facade/contracts.py
"""Контракты lifecycle tools.

Каждый tool возвращает:
- свой основной результат
- _next_action: {tool, args, why} — что вызывать дальше
- _artifact_id: для передачи между вызовами
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class NextAction(BaseModel):
    """Что вызывать дальше — для LLM внешнего клиента."""
    tool: str = Field(description="Имя следующего lifecycle tool'а")
    args: dict[str, Any] = Field(description="Аргументы для следующего вызова")
    why: str = Field(description="Почему именно это действие")


class PlanInput(BaseModel):
    task: str = Field(description="Описание задачи на естественном языке")
    config_name: str
    config_version: str
    platform_version: str


class PlanOutput(BaseModel):
    plan_id: str = Field(description="ID плана — для передачи в gather")
    subtasks: list[dict[str, Any]] = Field(description="Список подзадач")
    decomposition_strategy: str
    rationale: str
    _next_action: NextAction
    _artifact_id: str = Field(description="= plan_id")


class GatherInput(BaseModel):
    plan_id: str
    subtask_id: str


class GatherOutput(BaseModel):
    subtask_id: str
    context_summary: str
    patterns_applied: list[str]
    mcp_calls_made: list[str]
    _next_action: NextAction
    _artifact_id: str = Field(description="plan_id + subtask_id (для generate)")


class GenerateInput(BaseModel):
    plan_id: str
    subtask_id: str
    iteration: int = Field(default=1, ge=1)


class GenerateOutput(BaseModel):
    subtask_id: str
    iteration: int
    code: str
    explanation: str
    patterns_applied: list[str]
    _next_action: NextAction
    _artifact_id: str = Field(description="= subtask_id + iteration (для validate)")


class ValidateInput(BaseModel):
    artifact_id: str = Field(description="Из GenerateOutput._artifact_id")


class ValidateOutput(BaseModel):
    artifact_id: str
    passed: bool
    findings: list[dict[str, Any]]
    severity_breakdown: dict[str, int]
    failed_checks: list[dict[str, Any]] = Field(description="Для retry")
    _next_action: NextAction


class ReviewInput(BaseModel):
    artifact_id: str


class ReviewOutput(BaseModel):
    artifact_id: str
    decision: Literal["proceed", "retry", "escalate"]
    findings: list[dict[str, Any]]
    rationale: str
    pr_url: str | None = None
    _next_action: NextAction


class ExplainInput(BaseModel):
    """Explain — обратный путь: код → объяснение."""
    code: str | None = None
    query: str | None = Field(default=None, description="Текстовый запрос (что объяснить)")
    config_name: str | None = None
    config_version: str | None = None


class ExplainOutput(BaseModel):
    explanation: str
    related_patterns: list[dict[str, Any]]
    related_antipatterns: list[dict[str, Any]]
    similar_modules: list[dict[str, Any]]


class RunCliInput(BaseModel):
    """Proxy к скрытым MCP tools (не lifecycle)."""
    tool_name: str = Field(description="metadata.get_metadata | codebase.call_graph | ...")
    args: dict[str, Any]
    caller_role: str = Field(default="GATHERER", description="Для проверки прав через TOOL_GROUPS")


class RunCliOutput(BaseModel):
    tool_name: str
    result: dict[str, Any]
    _warning: str | None = Field(default=None, description="Если tool не найден/запрещён")


class DataStatusOutput(BaseModel):
    paths: dict[str, bool]
    configs: list[dict[str, Any]]
    indexes_freshness: dict[str, dict[str, bool]]
    _missing_prerequisites: list[str] = Field(description="Что нужно сделать до старта")
```

## 5. `_next_action` builder

```python
# packages/mcp_servers/src/mcp_servers/facade/next_action.py
"""Конструирование _next_action для каждого lifecycle tool'а."""
from __future__ import annotations

from .contracts import NextAction


def after_plan(plan_id: str, first_subtask_id: str) -> NextAction:
    return NextAction(
        tool="gather",
        args={"plan_id": plan_id, "subtask_id": first_subtask_id},
        why="Собрать контекст для первой подзадачи из плана",
    )


def after_gather(plan_id: str, subtask_id: str) -> NextAction:
    return NextAction(
        tool="generate",
        args={"plan_id": plan_id, "subtask_id": subtask_id, "iteration": 1},
        why="Контекст собран — можно генерировать код",
    )


def after_generate(plan_id: str, subtask_id: str, iteration: int) -> NextAction:
    artifact_id = f"{subtask_id}#{iteration}"
    return NextAction(
        tool="validate",
        args={"artifact_id": artifact_id},
        why="Код сгенерирован — проверить через BSL LS + антипаттерны",
    )


def after_validate(plan_id: str, subtask_id: str, iteration: int, passed: bool) -> NextAction:
    if passed:
        artifact_id = f"{subtask_id}#{iteration}"
        return NextAction(
            tool="review",
            args={"artifact_id": artifact_id},
            why="Код прошёл детерминированную валидацию — ревью LLM",
        )
    return NextAction(
        tool="generate",
        args={"plan_id": plan_id, "subtask_id": subtask_id, "iteration": iteration + 1},
        why="Валидация не прошла — retry с конкретными failed_checks в фидбеке",
    )


def after_review(
    plan_id: str,
    subtask_id: str,
    iteration: int,
    decision: str,
    next_subtask_id: str | None = None,
) -> NextAction:
    if decision == "proceed":
        if next_subtask_id:
            return NextAction(
                tool="gather",
                args={"plan_id": plan_id, "subtask_id": next_subtask_id},
                why="Подзадача прошла ревью — следующая подзадача",
            )
        return NextAction(
            tool="data_status",
            args={},
            why="Все подзадачи выполнены — можно проверять итог и коммитить",
        )
    if decision == "retry":
        return NextAction(
            tool="generate",
            args={"plan_id": plan_id, "subtask_id": subtask_id, "iteration": iteration + 1},
            why="Рецензент нашёл замечания — retry",
        )
    return NextAction(
        tool="data_status",
        args={},
        why="Эскалация к человеку — пайплайн остановлен",
    )
```

## 6. Handlers — реализация

```python
# packages/mcp_servers/src/mcp_servers/facade/handlers.py
"""Handlers для 7 lifecycle tools.

Каждый handler:
1. Создаёт или восстанавливает TaskState из checkpoint
2. Запускает соответствующий узел/субграф orchestrator'а
3. Возвращает результат + _next_action
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import mcp.types as types
from langgraph.checkpoint.memory import MemorySaver

from orchestrator.state import TaskState, FSMState
from orchestrator.graph import build_graph
from orchestrator.tool_groups import AgentRole
from orchestrator.tool_provider import make_tool_provider
from data_layer import PathManager
from .contracts import (
    PlanInput, PlanOutput, NextAction,
    GatherInput, GatherOutput,
    GenerateInput, GenerateOutput,
    ValidateInput, ValidateOutput,
    ReviewInput, ReviewOutput,
    ExplainInput, ExplainOutput,
    RunCliInput, RunCliOutput,
    DataStatusOutput,
)
from .next_action import (
    after_plan, after_gather, after_generate,
    after_validate, after_review,
)


class FacadeHandlers:
    """Все lifecycle handlers в одном классе."""

    def __init__(self) -> None:
        self.pm = PathManager()
        self.graph = build_graph(checkpointer=MemorySaver())
        # Кэш: plan_id → thread_id (для LangGraph checkpoint)
        self._thread_map: dict[str, str] = {}

    # ─── plan ──────────────────────────────────────────────────────────────
    async def handle_plan(self, args: dict[str, Any]) -> list[types.TextContent]:
        input_ = PlanInput.model_validate(args)

        plan_id = str(uuid.uuid4())
        thread_id = str(uuid.uuid4())
        self._thread_map[plan_id] = thread_id

        # Создаём TaskState и запускаем Plan subgraph
        state = TaskState(
            task_id=plan_id,
            description=input_.task,
            config_name=input_.config_name,
            config_version=input_.config_version,
            platform_version=input_.platform_version,
            fsm_state=FSMState.PLANNING,
        )

        # Запускаем граф до конца Plan-узла
        # (в реальной реализации — invoke с interrupt_before="gather")
        result = await self.graph.ainvoke(
            state.model_dump(),
            config={"configurable": {"thread_id": thread_id}},
        )

        plan_result = result.get("plan_result", {})
        subtasks = plan_result.get("subtasks", [])
        first_subtask_id = subtasks[0]["id"] if subtasks else None

        output = PlanOutput(
            plan_id=plan_id,
            subtasks=subtasks,
            decomposition_strategy=plan_result.get("decomposition_strategy", "single"),
            rationale=plan_result.get("rationale", ""),
            _next_action=after_plan(plan_id, first_subtask_id) if first_subtask_id else NextAction(
                tool="data_status", args={}, why="Plan пустой — проверьте данные"
            ),
            _artifact_id=plan_id,
        )
        return _wrap(output)

    # ─── gather ────────────────────────────────────────────────────────────
    async def handle_gather(self, args: dict[str, Any]) -> list[types.TextContent]:
        input_ = GatherInput.model_validate(args)
        thread_id = self._thread_map[input_.plan_id]

        # Resume graph с собранным контекстом
        result = await self.graph.ainvoke(
            None,  # state уже в checkpoint
            config={"configurable": {"thread_id": thread_id}},
        )

        gather_result = result.get("gather_result", {})
        output = GatherOutput(
            subtask_id=input_.subtask_id,
            context_summary=gather_result.get("context_summary", ""),
            patterns_applied=[p["id"] for p in gather_result.get("knowledge", {}).get("patterns", [])],
            mcp_calls_made=gather_result.get("mcp_calls_made", []),
            _next_action=after_gather(input_.plan_id, input_.subtask_id),
            _artifact_id=f"{input_.plan_id}#{input_.subtask_id}",
        )
        return _wrap(output)

    # ─── generate ──────────────────────────────────────────────────────────
    async def handle_generate(self, args: dict[str, Any]) -> list[types.TextContent]:
        input_ = GenerateInput.model_validate(args)
        thread_id = self._thread_map[input_.plan_id]

        result = await self.graph.ainvoke(
            None,
            config={"configurable": {"thread_id": thread_id}},
        )

        iterations = result.get("iterations", [])
        current = iterations[-1] if iterations else {}

        output = GenerateOutput(
            subtask_id=input_.subtask_id,
            iteration=input_.iteration,
            code=current.get("code", ""),
            explanation=current.get("llm_response", {}).get("explanation", ""),
            patterns_applied=current.get("llm_response", {}).get("patterns_applied", []),
            _next_action=after_generate(input_.plan_id, input_.subtask_id, input_.iteration),
            _artifact_id=f"{input_.subtask_id}#{input_.iteration}",
        )
        return _wrap(output)

    # ─── validate ──────────────────────────────────────────────────────────
    async def handle_validate(self, args: dict[str, Any]) -> list[types.TextContent]:
        input_ = ValidateInput.model_validate(args)
        # artifact_id имеет формат "subtask_id#iteration"
        subtask_id, iteration_str = input_.artifact_id.split("#")
        iteration = int(iteration_str)

        # Найти plan_id по subtask_id — пробегаем по _thread_map
        plan_id = self._find_plan_for_subtask(subtask_id)
        thread_id = self._thread_map[plan_id]

        result = await self.graph.ainvoke(
            None,
            config={"configurable": {"thread_id": thread_id}},
        )

        validate_result = result.get("validate_result", {})
        passed = validate_result.get("passed", False)

        output = ValidateOutput(
            artifact_id=input_.artifact_id,
            passed=passed,
            findings=validate_result.get("findings", []),
            severity_breakdown=validate_result.get("severity_breakdown", {}),
            failed_checks=validate_result.get("failed_checks", []),
            _next_action=after_validate(plan_id, subtask_id, iteration, passed),
        )
        return _wrap(output)

    # ─── review ────────────────────────────────────────────────────────────
    async def handle_review(self, args: dict[str, Any]) -> list[types.TextContent]:
        input_ = ReviewInput.model_validate(args)
        subtask_id, iteration_str = input_.artifact_id.split("#")
        iteration = int(iteration_str)
        plan_id = self._find_plan_for_subtask(subtask_id)
        thread_id = self._thread_map[plan_id]

        result = await self.graph.ainvoke(
            None,
            config={"configurable": {"thread_id": thread_id}},
        )

        review_result = result.get("review_result", {})
        decision = review_result.get("decision", "escalate")

        # Найти следующую подзадачу (если proceed)
        next_subtask_id = None
        if decision == "proceed":
            subtasks = result.get("subtasks", [])
            current_idx = result.get("current_subtask_idx", 0)
            if current_idx + 1 < len(subtasks):
                next_subtask_id = subtasks[current_idx + 1]["id"]

        output = ReviewOutput(
            artifact_id=input_.artifact_id,
            decision=decision,
            findings=review_result.get("findings", []),
            rationale=review_result.get("rationale", ""),
            pr_url=result.get("commit_result", {}).get("pr_url"),
            _next_action=after_review(plan_id, subtask_id, iteration, decision, next_subtask_id),
        )
        return _wrap(output)

    # ─── explain ───────────────────────────────────────────────────────────
    async def handle_explain(self, args: dict[str, Any]) -> list[types.TextContent]:
        """Explain — reverse engineering: код → объяснение."""
        input_ = ExplainInput.model_validate(args)

        # Используем LLM напрямую (не через pipeline) — это "read-only" tool
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_template("""
        Объясни этот BSL-код:
        ```
        {code}
        ```

        Структура:
        1. Назначение модуля/функции
        2. Ключевые алгоритмы
        3. Возможные проблемы (если есть)
        4. Связанные паттерны и антипаттерны
        """)

        # ... вызов LLM
        explanation = "..."  # заглушка

        output = ExplainOutput(
            explanation=explanation,
            related_patterns=[],  # через kb.search_kb
            related_antipatterns=[],  # через kb.check_antipatterns
            similar_modules=[],  # через codebase.get_similar
        )
        return _wrap(output)

    # ─── run_cli ───────────────────────────────────────────────────────────
    async def handle_run_cli(self, args: dict[str, Any]) -> list[types.TextContent]:
        """Proxy к скрытым MCP tools (не lifecycle).

        Проверяет права через TOOL_GROUPS.
        """
        input_ = RunCliInput.model_validate(args)

        # Проверка прав
        role = AgentRole(input_.caller_role)
        provider = make_tool_provider(role)

        if not provider.has_tool(input_.tool_name):
            output = RunCliOutput(
                tool_name=input_.tool_name,
                result={},
                _warning=f"Role {role.value} не имеет прав на {input_.tool_name}",
            )
            return _wrap(output)

        # Вызов tool'а
        all_contracts = _collect_all_tool_contracts()
        contract_cls = all_contracts[input_.tool_name]
        contract = contract_cls()
        try:
            result = await contract(**input_.args)
            output = RunCliOutput(tool_name=input_.tool_name, result=result)
        except Exception as exc:
            output = RunCliOutput(
                tool_name=input_.tool_name,
                result={"error": str(exc), "code": "TOOL_EXECUTION_ERROR"},
            )
        return _wrap(output)

    # ─── data_status ───────────────────────────────────────────────────────
    async def handle_data_status(self, args: dict[str, Any]) -> list[types.TextContent]:
        """Статус данных проекта — для preflight check."""
        from data_layer import ConfigRegistry

        paths = self.pm.validate()
        registry = ConfigRegistry(self.pm.config_registry_path())
        configs = [c.model_dump(mode="json") for c in registry.list()]

        # Freshness для каждой конфигурации
        freshness: dict[str, dict[str, bool]] = {}
        for cfg in configs:
            freshness[cfg["name"]] = self.pm.freshness_check(cfg["name"], cfg["version"])

        # Что нужно сделать до старта
        missing: list[str] = []
        if not paths.get("data_dir"):
            missing.append("Run: 1c-ai init (создать директории)")
        if not paths.get("config_registry"):
            missing.append("No configs loaded. Run: 1c-ai config add --name X --version Y --zip X.zip")
        if not configs:
            missing.append("No configurations loaded")
        for cfg_name, fr in freshness.items():
            stale = [k for k, v in fr.items() if not v]
            if stale:
                missing.append(f"Stale indexes for {cfg_name}: {stale}. Run: 1c-ai config build --name {cfg_name} --force")

        output = DataStatusOutput(
            paths=paths,
            configs=configs,
            indexes_freshness=freshness,
            _missing_prerequisites=missing,
        )
        return _wrap(output)

    # ─── helpers ───────────────────────────────────────────────────────────
    def _find_plan_for_subtask(self, subtask_id: str) -> str:
        """Найти plan_id, в котором есть данная подзадача.

        В реальной реализации — запрос в Postgres checkpoint store.
        """
        for plan_id, thread_id in self._thread_map.items():
            # state = self.graph.get_state({"configurable": {"thread_id": thread_id}})
            # if subtask_id in [s["id"] for s in state.values.get("subtasks", [])]:
            #     return plan_id
            pass
        raise ValueError(f"No plan found for subtask {subtask_id}")


def _collect_all_tool_contracts() -> dict[str, type]:
    """Собрать все tool contracts."""
    from mcp_servers.metadata.contracts import METADATA_TOOLS
    from mcp_servers.codebase.contracts import CODEBASE_TOOLS
    from mcp_servers.kb.contracts import KB_TOOLS
    from mcp_servers.bsl_ls.contracts import BSL_LS_TOOLS
    from mcp_servers.git.contracts import GIT_TOOLS

    result: dict[str, type] = {}
    for cls in METADATA_TOOLS + CODEBASE_TOOLS + KB_TOOLS + BSL_LS_TOOLS + GIT_TOOLS:
        result[cls.name] = cls
    return result


def _wrap(output: BaseModel) -> list[types.TextContent]:
    """Обернуть Pydantic-модель в MCP TextContent."""
    return [types.TextContent(
        type="text",
        text=json.dumps(output.model_dump(mode="json"), ensure_ascii=False, indent=2),
    )]
```

## 7. Server entry point

```python
# packages/mcp_servers/src/mcp_servers/facade/server.py
"""MCP server entry point для Agent-Facade.

Запуск:
    1c-ai mcp serve                          # facade (по умолчанию)
    1c-ai mcp serve --server metadata        # доменный сервер напрямую (power-user)
"""
from __future__ import annotations

import asyncio
import contextlib
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .handlers import FacadeHandlers


def create_facade_server() -> Server:
    server = Server("1c-ai-agent-facade")
    handlers = FacadeHandlers()

    # Map tool names → handler methods
    HANDLER_MAP = {
        "plan": handlers.handle_plan,
        "gather": handlers.handle_gather,
        "generate": handlers.handle_generate,
        "validate": handlers.handle_validate,
        "review": handlers.handle_review,
        "explain": handlers.handle_explain,
        "run_cli": handlers.handle_run_cli,
        "data_status": handlers.handle_data_status,
    }

    @server.list_tools()
    async def list_tools() -> list:
        from mcp_servers.facade.tool_definitions import FACADE_TOOLS
        return FACADE_TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list:
        with contextlib.suppress(Exception):
            pass  # logging
        handler = HANDLER_MAP.get(name)
        if handler is None:
            import json
            from mcp.types import TextContent
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
        return await handler(arguments)

    return server


async def run_facade_server() -> None:
    server = create_facade_server()
    options = server.create_initialization_options()
    async with stdio_server() as (read, write):
        await server.run(read, write, options)


def run_sync() -> None:
    """Для [project.scripts] в pyproject.toml."""
    asyncio.run(run_facade_server())


if __name__ == "__main__":
    run_sync()
```

## 8. Tool definitions для Facade

```python
# packages/mcp_servers/src/mcp_servers/facade/tool_definitions.py
"""Описания 8 visible tools Facade'а.

Это единственное, что видит LLM внешнего клиента.
"""
from __future__ import annotations

import mcp.types as types


FACADE_TOOLS: list[types.Tool] = [
    types.Tool(
        name="plan",
        description=(
            "Запустить план декомпозиции задачи. Возвращает plan_id + список подзадач + "
            "_next_action (что вызывать дальше). "
            "Пример: plan(task='Добавить обработку проведения для Реализации', "
            "config_name='ut11', config_version='4.5.3', platform_version='8.3.20')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Описание задачи"},
                "config_name": {"type": "string"},
                "config_version": {"type": "string"},
                "platform_version": {"type": "string"},
            },
            "required": ["task", "config_name", "config_version", "platform_version"],
        },
    ),
    types.Tool(
        name="gather",
        description=(
            "Собрать контекст для подзадачи. Запускает metadata + codebase + kb MCP-серверы "
            "параллельно. Возвращает context_summary + _next_action=generate. "
            "Пример: gather(plan_id='...', subtask_id='...')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "subtask_id": {"type": "string"},
            },
            "required": ["plan_id", "subtask_id"],
        },
    ),
    types.Tool(
        name="generate",
        description=(
            "Сгенерировать BSL-код для подзадачи. Coder agent использует собранный контекст. "
            "Возвращает код + explanation + _next_action=validate."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "subtask_id": {"type": "string"},
                "iteration": {"type": "integer", "minimum": 1, "default": 1},
            },
            "required": ["plan_id", "subtask_id"],
        },
    ),
    types.Tool(
        name="validate",
        description=(
            "Запустить детерминированную валидацию (BSL LS + KB антипаттерны). "
            "Возвращает passed/findings + _next_action (review или generate для retry)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string", "description": "Из generate._artifact_id"},
            },
            "required": ["artifact_id"],
        },
    ),
    types.Tool(
        name="review",
        description=(
            "LLM-рецензент: проверить код и решить proceed/retry/escalate. "
            "При proceed — открывается PR. При retry — _next_action=generate. "
            "При escalate — _next_action=data_status."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string"},
            },
            "required": ["artifact_id"],
        },
    ),
    types.Tool(
        name="explain",
        description=(
            "Объяснить существующий BSL-код или найти ответ на вопрос. "
            "Read-only — не изменяет код. Использует kb + codebase MCP."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "query": {"type": "string"},
                "config_name": {"type": "string"},
                "config_version": {"type": "string"},
            },
        },
    ),
    types.Tool(
        name="run_cli",
        description=(
            "Proxy к скрытым MCP tools (не lifecycle). "
            "Пример: run_cli(tool_name='metadata.get_metadata', "
            "args={'object_ref': 'Catalog.Контрагенты', ...}, caller_role='GATHERER')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "tool_name": {"type": "string"},
                "args": {"type": "object"},
                "caller_role": {"type": "string", "default": "GATHERER"},
            },
            "required": ["tool_name", "args"],
        },
    ),
    types.Tool(
        name="data_status",
        description="Статус данных проекта: paths, configs, freshness, missing prerequisites.",
        inputSchema={"type": "object", "properties": {}},
    ),
]
```

## 9. Пример workflow внешнего клиента (Cursor)

Cursor видит только 8 tools. Типичная сессия:

```
USER: "Добавь обработку проведения для документа Реализация"

CURSOR → 1. data_status()
       ← {"paths": {...}, "_missing_prerequisites": []}  # всё ок

CURSOR → 2. plan(task="Добавить обработку проведения для документа Реализация",
                 config_name="ut11", config_version="4.5.3", platform_version="8.3.20")
       ← {"plan_id": "abc-123", "subtasks": [{id: "st-1", ...}], 
          "_next_action": {"tool": "gather", "args": {"plan_id": "abc-123", "subtask_id": "st-1"}}}

CURSOR → 3. gather(plan_id="abc-123", subtask_id="st-1")
       ← {"context_summary": "...", "patterns_applied": ["posting-handler"],
          "_next_action": {"tool": "generate", "args": {"plan_id": "abc-123", "subtask_id": "st-1", "iteration": 1}}}

CURSOR → 4. generate(plan_id="abc-123", subtask_id="st-1", iteration=1)
       ← {"code": "Процедура ОбработкаПроведения(...)...", "_next_action": {"tool": "validate", ...}}

CURSOR → 5. validate(artifact_id="st-1#1")
       ← {"passed": false, "findings": [{"code": "BSL-WS-001", ...}], 
          "_next_action": {"tool": "generate", "args": {"iteration": 2}}}

CURSOR → 6. generate(plan_id="abc-123", subtask_id="st-1", iteration=2)
       ← {"code": "...", "_next_action": {"tool": "validate", ...}}

CURSOR → 7. validate(artifact_id="st-1#2")
       ← {"passed": true, "_next_action": {"tool": "review", ...}}

CURSOR → 8. review(artifact_id="st-1#2")
       ← {"decision": "proceed", "pr_url": "https://github.com/.../pull/42",
          "_next_action": {"tool": "data_status"}}
```

**8 вызовов для завершения задачи.** Без `_next_action` Cursor бы блуждал и вызывал tools хаотично.

## 10. CLI `1c-ai generate` — тот же pipeline

CLI использует те же handlers, но без `_next_action` (запускает всё за один вызов):

```python
# packages/agent/src/agent/cli_commands/generate.py
async def cmd_generate(task: str, config: str, version: str, platform: str) -> None:
    handlers = FacadeHandlers()

    # Полный pipeline за один прогон
    plan_resp = await handlers.handle_plan({
        "task": task, "config_name": config, "config_version": version, "platform_version": platform,
    })
    plan = json.loads(plan_resp[0].text)
    print(f"Plan: {len(plan['subtasks'])} subtasks")

    for subtask in plan["subtasks"]:
        await handlers.handle_gather({"plan_id": plan["plan_id"], "subtask_id": subtask["id"]})
        iteration = 1
        while iteration <= 3:
            await handlers.handle_generate({
                "plan_id": plan["plan_id"], "subtask_id": subtask["id"], "iteration": iteration,
            })
            artifact_id = f"{subtask['id']}#{iteration}"
            validate_resp = await handlers.handle_validate({"artifact_id": artifact_id})
            validate_result = json.loads(validate_resp[0].text)
            if validate_result["passed"]:
                review_resp = await handlers.handle_review({"artifact_id": artifact_id})
                review_result = json.loads(review_resp[0].text)
                if review_result["decision"] == "proceed":
                    print(f"Subtask {subtask['id']}: PR {review_result['pr_url']}")
                    break
                elif review_result["decision"] == "escalate":
                    print(f"Subtask {subtask['id']}: escalated")
                    break
            iteration += 1
```

## 11. Взаимосвязь с другими шагами

| Шаг | Связь |
|---|---|
| Шаг 4 (Pipeline contracts) | `handle_plan`/`handle_gather`/... запускают узлы графа |
| Шаг 5 (MCP tool contracts) | `run_cli` proxy проверяет `required_role` через TOOL_GROUPS |
| Шаг 6 (TOOL_GROUPS) | `run_cli` использует `make_tool_provider(role).has_tool()` |
| Шаг 7 (KB-as-code) | `explain` возвращает KB-описания из `kb.search_kb` |
| Шаг 9 (Persistence) | `plan_id → thread_id` map — в Postgres, не в памяти |

---

**Шаг 8 завершён.** Следующий — Шаг 9: Error taxonomy + state persistence. Это последний шаг проектирования — закрывает вопрос «что делать, когда что-то идёт не так».
