# Шаг 6 — TOOL_GROUPS registry

> **ADR-0011:** TOOL_GROUPS — декларативное распределение инструментов
> **Зависимости:** Шаг 4 (роли = узлы pipeline), Шаг 5 (19 MCP tools с `required_role`)
> **Артефакт:** `packages/orchestrator/src/orchestrator/tool_groups.py` + `tool_provider.py`

## 1. Суть шага

TOOL_GROUPS — это **единственное место**, где зафиксировано, какой агент какие инструменты может вызывать. Всё остальное — implementation detail.

Если в коде где-то `gather_node` напрямую вызывает `codebase.semantic_search` без проверки через `ToolProvider` — это bug. Если Coder'у в system prompt попало описание `kb.get_pattern` — это bug. Если `validator_node` попытался вызвать `git.commit` — это bug.

TOOL_GROUPS + CI-тесты = гарантия фокус-контроля.

## 2. AgentRole enum

```python
# packages/orchestrator/src/orchestrator/tool_groups.py (часть 1)
"""TOOL_GROUPS registry — декларативное распределение инструментов по ролям.

Этот файл — единственный источник правды.
Все остальные модули импортируют TOOL_GROUPS и/или MULTI_ROLE_OK.
"""
from __future__ import annotations

from enum import Enum
from frozenset import frozenset  # type: ignore # стандартный typing.frozenset в 3.12+


class AgentRole(str, Enum):
    """Роли агентов в pipeline. Соответствуют узлам графа (Шаг 4)."""
    PLANNER = "PLANNER"          # Plan subgraph
    GATHERER = "GATHERER"        # Gather subgraph
    CODER = "CODER"              # Code node — без инструментов
    VALIDATOR = "VALIDATOR"      # Validate subgraph
    REVIEWER = "REVIEWER"        # Review subgraph
    COMMITTER = "COMMITTER"      # Commit node
```

## 3. TOOL_GROUPS — главная таблица

```python
# tool_groups.py (часть 2)

# MCPServer — для удобства чтения, не enforcement
MCPServer = str  # "metadata" | "codebase" | "kb" | "bsl_ls" | "git"
ToolName = str   # "metadata.get_metadata" | ...


TOOL_GROUPS: dict[AgentRole, dict[MCPServer, frozenset[ToolName]]] = {
    AgentRole.PLANNER: {
        "metadata": frozenset({
            "metadata.get_dependency_graph",   # структурный анализ для декомпозиции
        }),
        "kb": frozenset({
            "kb.search_kb",                    # поиск релевантных паттернов/стандартов
        }),
    },

    AgentRole.GATHERER: {
        "metadata": frozenset({
            "metadata.get_metadata",           # метаданные target-объекта
            "metadata.get_form_structure",     # форма (если задача про форму)
            "metadata.get_api_reference",      # API общих модулей, которые можно вызывать
        }),
        "codebase": frozenset({
            "codebase.semantic_search",        # поиск похожего кода
            "codebase.get_module",             # полный модуль для примера
            "codebase.call_graph",             # граф вызовов (кто кого вызывает)
        }),
        "kb": frozenset({
            "kb.get_pattern",                  # эталонный паттерн
            "kb.check_method_availability",    # доступность методов в контексте
        }),
    },

    AgentRole.CODER: {
        # CODER НЕ ИМЕЕТ ИНСТРУМЕНТОВ.
        # Это критично — Coder генерирует код из собранного Gather'ом контекста.
        # Если Coder получит semantic_search, он начнёт "исследовать" вместо генерации.
    },

    AgentRole.VALIDATOR: {
        "bsl_ls": frozenset({
            "bsl_ls.lint",                     # 187 диагностик — главный gate
            "bsl_ls.format",                   # форматирование (опционально)
        }),
        "kb": frozenset({
            "kb.check_antipatterns",           # YAML-правила
            "kb.check_method_availability",    # context violations (server vs client)
        }),
    },

    AgentRole.REVIEWER: {
        "kb": frozenset({
            "kb.get_antipattern",              # полное описание антипаттерна по id
            "kb.check_antipatterns",           # повторная проверка (LLM может просить)
        }),
        "codebase": frozenset({
            "codebase.get_similar",            # похожие модули — есть ли pattern в кодовой базе
        }),
    },

    AgentRole.COMMITTER: {
        "git": frozenset({
            "git.create_branch",
            "git.commit",
            "git.open_pr",
            "git.diff",
        }),
    },
}
```

## 4. MULTI_ROLE_OK — исключения

По умолчанию каждый tool принадлежит **строго одной** роли. Это ловит случайные дублирования. Но есть осознанные исключения:

```python
# tool_groups.py (часть 3)

# Tools, которые законно принадлежат нескольким ролям.
# Каждый случай — с обоснованием в комментарии.
MULTI_ROLE_OK: dict[ToolName, list[AgentRole]] = {
    "kb.check_method_availability": [
        AgentRole.GATHERER,    # Gatherer проверяет методы, которые Coder может вызвать
        AgentRole.VALIDATOR,   # Validator проверяет, что Coder не нарушил контекст
    ],
    "kb.check_antipatterns": [
        AgentRole.VALIDATOR,   # Validator детектирует антипаттерны
        AgentRole.REVIEWER,    # Reviewer повторно проверяет + интерпретирует
    ],
}


def _validate_multi_role() -> None:
    """Проверка при импорте: MULTI_ROLE_OK согласован с TOOL_GROUPS."""
    for tool_name, expected_roles in MULTI_ROLE_OK.items():
        actual_roles = [
            role for role, servers in TOOL_GROUPS.items()
            for tools in servers.values()
            if tool_name in tools
        ]
        if sorted(actual_roles) != sorted(expected_roles):
            raise RuntimeError(
                f"MULTI_ROLE_OK inconsistent for {tool_name}: "
                f"expected {expected_roles}, actual {actual_roles}"
            )


_validate_multi_role()  # запускается при импорте модуля
```

## 5. ToolProvider — LangChain adapter

```python
# packages/orchestrator/src/orchestrator/tool_provider.py
"""ToolProvider — отдаёт LLM только разрешённые для роли инструменты.

Реализует 2 уровня изоляции:
1. Prompt-level: в system prompt LLM видит только свои tools
2. MCP-level: каждый вызов tool'а проверяет caller_role

Используется каждым LLM-узлом pipeline.
"""
from __future__ import annotations

from typing import Any, Protocol
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.runnables import RunnableConfig

from .tool_groups import AgentRole, TOOL_GROUPS, MULTI_ROLE_OK
from mcp_servers.shared.protocol import ToolContract, ToolError


class ToolProvider:
    """Отдаёт LangChain BaseTool'ы для конкретной роли.

    Каждая роль создаёт свой ToolProvider:
        provider = ToolProvider(AgentRole.GATHERER)
        tools = provider.get_tools()  # list[BaseTool]
        llm_with_tools = llm.bind_tools(tools)
    """

    def __init__(
        self,
        role: AgentRole,
        tool_contracts: dict[str, type[ToolContract]],
    ) -> None:
        """tool_contracts: {'metadata.get_metadata': GetMetadata, ...}"""
        self.role = role
        self._all_contracts = tool_contracts
        self._allowed = self._compute_allowed()

    def _compute_allowed(self) -> frozenset[str]:
        """Какие tools разрешены этой роли?"""
        role_tools: set[str] = set()
        for tools_set in TOOL_GROUPS[self.role].values():
            role_tools.update(tools_set)
        return frozenset(role_tools)

    def get_tools(self) -> list[BaseTool]:
        """Вернуть list[BaseTool] для LangChain bind_tools()."""
        tools: list[BaseTool] = []
        for tool_name in sorted(self._allowed):
            contract_cls = self._all_contracts[tool_name]
            tools.append(self._wrap_contract(contract_cls))
        return tools

    def _wrap_contract(self, contract_cls: type[ToolContract]) -> BaseTool:
        """Превратить ToolContract в LangChain BaseTool."""
        async def _run(**kwargs: Any) -> dict[str, Any]:
            # MCP-level check (defense in depth)
            if contract_cls.required_role not in self._roles_for_tool(contract_cls.name):
                raise ToolError(
                    f"Role {self.role.value} is not allowed to call {contract_cls.name}",
                    code="ROLE_FORBIDDEN",
                )
            contract = contract_cls()  # инстанцируем (нужно для __call__)
            try:
                return await contract(**kwargs)
            except ToolError:
                raise
            except Exception as exc:
                if contract_cls.error_contract == "exception":
                    raise ToolError(str(exc), code="TOOL_EXECUTION_ERROR") from exc
                # error_dict / empty_result — контракт сам управляет
                raise

        return StructuredTool.from_function(
            coroutine=_run,
            name=contract_cls.name,
            description=contract_cls.description,
            args_schema=contract_cls.input_schema,
        )

    def _roles_for_tool(self, tool_name: str) -> list[AgentRole]:
        """Все роли, которым разрешён этот tool (через MULTI_ROLE_OK)."""
        for key, roles in MULTI_ROLE_OK.items():
            if key == tool_name:
                return roles
        # Если не в MULTI_ROLE_OK — единственная роль из TOOL_GROUPS
        for role, servers in TOOL_GROUPS.items():
            for tools in servers.values():
                if tool_name in tools:
                    return [role]
        return []

    def has_tool(self, tool_name: str) -> bool:
        """Проверка: разрешён ли tool этой роли?"""
        return tool_name in self._allowed


# ─── Фабрика ─────────────────────────────────────────────────────────────────

def make_tool_provider(
    role: AgentRole,
    tool_contracts: dict[str, type[ToolContract]] | None = None,
) -> ToolProvider:
    """Создать ToolProvider для роли.

    tool_contracts: если None — собираются из всех MCP-серверов автоматически.
    """
    if tool_contracts is None:
        tool_contracts = _collect_all_tool_contracts()
    return ToolProvider(role, tool_contracts)


def _collect_all_tool_contracts() -> dict[str, type[ToolContract]]:
    """Собрать все tool contracts из 5 MCP-серверов."""
    from mcp_servers.metadata.contracts import METADATA_TOOLS
    from mcp_servers.codebase.contracts import CODEBASE_TOOLS
    from mcp_servers.kb.contracts import KB_TOOLS
    from mcp_servers.bsl_ls.contracts import BSL_LS_TOOLS
    from mcp_servers.git.contracts import GIT_TOOLS

    all_contracts: dict[str, type[ToolContract]] = {}
    for tool_cls in METADATA_TOOLS + CODEBASE_TOOLS + KB_TOOLS + BSL_LS_TOOLS + GIT_TOOLS:
        if tool_cls.name in all_contracts:
            raise RuntimeError(f"Duplicate tool name: {tool_cls.name}")
        all_contracts[tool_cls.name] = tool_cls
    return all_contracts
```

## 6. Использование в узлах pipeline

```python
# orchestrator/nodes/gather.py (фрагмент, использующий ToolProvider)
from ..tool_groups import AgentRole
from ..tool_provider import make_tool_provider


async def gather_supervisor_node(state: TaskState) -> dict:
    """LLM: решить, какие MCP нужны для текущей подзадачи."""
    provider = make_tool_provider(AgentRole.GATHERER)
    tools = provider.get_tools()

    # LLM видит ТОЛЬКО инструменты GATHERER'а:
    #   metadata.get_metadata, metadata.get_form_structure, metadata.get_api_reference,
    #   codebase.semantic_search, codebase.get_module, codebase.call_graph,
    #   kb.get_pattern, kb.check_method_availability

    llm_with_tools = llm.bind_tools(tools)
    decision = await llm_with_tools.ainvoke(_build_supervisor_prompt(state, tools))
    return {"gather_decision": _parse_decision(decision)}


async def code_node(state: TaskState) -> dict:
    """Coder генерирует BSL-код. БЕЗ ИНСТРУМЕНТОВ."""
    provider = make_tool_provider(AgentRole.CODER)
    # provider.get_tools() вернёт [] — Coder не имеет tools
    # LLM вызывается БЕЗ bind_tools — только structured_output
    llm_with_output = llm.with_structured_output(CodeResult)
    response = await llm_with_output.ainvoke(_build_coder_prompt(state))
    return {"code_result": response.model_dump()}
```

## 7. CI-тесты — 3 обязательные проверки

```python
# tests/orchestrator/test_tool_groups.py
"""CI-проверки для TOOL_GROUPS.

Эти тесты — гарантия фокус-контроля. Любой failure = bug.
"""
import pytest
from orchestrator.tool_groups import AgentRole, TOOL_GROUPS, MULTI_ROLE_OK
from mcp_servers.metadata.contracts import METADATA_TOOLS
from mcp_servers.codebase.contracts import CODEBASE_TOOLS
from mcp_servers.kb.contracts import KB_TOOLS
from mcp_servers.bsl_ls.contracts import BSL_LS_TOOLS
from mcp_servers.git.contracts import GIT_TOOLS


ALL_TOOL_CLASSES = METADATA_TOOLS + CODEBASE_TOOLS + KB_TOOLS + BSL_LS_TOOLS + GIT_TOOLS
ALL_TOOL_NAMES = {t.name for t in ALL_TOOL_CLASSES}


class TestToolCoverage:
    def test_no_orphan_tools(self):
        """Каждый tool из tool_definitions принадлежит хотя бы одной роли.

        Если добавили новый tool в mcp_servers/*/contracts.py, но забыли
        добавить в TOOL_GROUPS — этот тест упадёт.
        """
        tools_in_groups: set[str] = set()
        for servers in TOOL_GROUPS.values():
            for tools in servers.values():
                tools_in_groups.update(tools)

        orphans = ALL_TOOL_NAMES - tools_in_groups
        assert not orphans, f"Orphan tools (not in any group): {orphans}"

    def test_all_tools_in_groups_exist(self):
        """Все tool'ы в TOOL_GROUPS должны существовать в contracts."""
        tools_in_groups: set[str] = set()
        for servers in TOOL_GROUPS.values():
            for tools in servers.values():
                tools_in_groups.update(tools)

        nonexistent = tools_in_groups - ALL_TOOL_NAMES
        assert not nonexistent, f"TOOL_GROUPS references unknown tools: {nonexistent}"


class TestMultiRole:
    def test_no_unexpected_multi_role(self):
        """Tool принадлежит >1 роли ТОЛЬКО если явно в MULTI_ROLE_OK.

        Это ловит случайное добавление tool'а в несколько ролей.
        """
        # Соберём фактическое распределение
        tool_to_roles: dict[str, set[AgentRole]] = {}
        for role, servers in TOOL_GROUPS.items():
            for tools in servers.values():
                for tool in tools:
                    tool_to_roles.setdefault(tool, set()).add(role)

        for tool_name, roles in tool_to_roles.items():
            if len(roles) > 1:
                # Должен быть в MULTI_ROLE_OK
                assert tool_name in MULTI_ROLE_OK, (
                    f"Tool {tool_name} is in {len(roles)} roles {roles} "
                    f"but not in MULTI_ROLE_OK. Either add to MULTI_ROLE_OK "
                    f"with justification, or remove from extra roles."
                )
                # Состав ролей должен совпадать
                expected = set(MULTI_ROLE_OK[tool_name])
                assert roles == expected, (
                    f"Tool {tool_name}: actual roles {roles} != "
                    f"MULTI_ROLE_OK {expected}"
                )

    def test_multi_role_ok_is_consistent(self):
        """MULTI_ROLE_OK должен точно отражать реальное распределение."""
        # Этот тест дублирует _validate_multi_role() при импорте,
        # но как явный pytest-тест он даёт понятный failure message.
        for tool_name, expected_roles in MULTI_ROLE_OK.items():
            actual_roles = set()
            for role, servers in TOOL_GROUPS.items():
                for tools in servers.values():
                    if tool_name in tools:
                        actual_roles.add(role)
            assert actual_roles == set(expected_roles), (
                f"MULTI_ROLE_OK[{tool_name}] = {expected_roles}, "
                f"actual = {actual_roles}"
            )


class TestToolProvider:
    def test_coder_has_no_tools(self):
        """CRITICAL: Coder не должен иметь инструментов."""
        from orchestrator.tool_provider import make_tool_provider
        provider = make_tool_provider(AgentRole.CODER)
        assert provider.get_tools() == [], "CODER must have ZERO tools"

    def test_gatherer_has_correct_tools(self):
        """GATHERER имеет ровно 8 tools из 3 серверов."""
        from orchestrator.tool_provider import make_tool_provider
        provider = make_tool_provider(AgentRole.GATHERER)
        tools = provider.get_tools()
        names = {t.name for t in tools}
        expected = {
            "metadata.get_metadata",
            "metadata.get_form_structure",
            "metadata.get_api_reference",
            "codebase.semantic_search",
            "codebase.get_module",
            "codebase.call_graph",
            "kb.get_pattern",
            "kb.check_method_availability",
        }
        assert names == expected

    def test_validator_has_correct_tools(self):
        """VALIDATOR имеет 4 tools (bsl_ls + kb)."""
        from orchestrator.tool_provider import make_tool_provider
        provider = make_tool_provider(AgentRole.VALIDATOR)
        tools = provider.get_tools()
        names = {t.name for t in tools}
        expected = {
            "bsl_ls.lint", "bsl_ls.format",
            "kb.check_antipatterns", "kb.check_method_availability",
        }
        assert names == expected

    def test_committer_has_git_tools(self):
        from orchestrator.tool_provider import make_tool_provider
        provider = make_tool_provider(AgentRole.COMMITTER)
        tools = provider.get_tools()
        names = {t.name for t in tools}
        expected = {
            "git.create_branch", "git.commit", "git.open_pr", "git.diff",
        }
        assert names == expected


class TestRoleForbidden:
    """MCP-level check — даже если LLM как-то вызовет tool, проверка упадёт."""

    @pytest.mark.asyncio
    async def test_coder_cannot_call_metadata(self):
        from orchestrator.tool_provider import make_tool_provider
        from mcp_servers.shared.protocol import ToolError
        provider = make_tool_provider(AgentRole.CODER)
        assert not provider.has_tool("metadata.get_metadata")

    @pytest.mark.asyncio
    async def test_gatherer_cannot_call_git(self):
        from orchestrator.tool_provider import make_tool_provider
        provider = make_tool_provider(AgentRole.GATHERER)
        assert not provider.has_tool("git.commit")
```

## 8. Фокус-контроль — итоговая матрица

| Tool | PLANNER | GATHERER | CODER | VALIDATOR | REVIEWER | COMMITTER |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| metadata.get_metadata | | ✅ | | | | |
| metadata.get_form_structure | | ✅ | | | | |
| metadata.get_api_reference | | ✅ | | | | |
| metadata.get_dependency_graph | ✅ | | | | | |
| codebase.semantic_search | | ✅ | | | | |
| codebase.get_module | | ✅ | | | | |
| codebase.get_similar | | | | | ✅ | |
| codebase.call_graph | | ✅ | | | | |
| kb.get_pattern | | ✅ | | | | |
| kb.get_antipattern | | | | | ✅ | |
| kb.search_kb | ✅ | | | | | |
| kb.check_method_availability | | ✅ | | ✅ | | |
| kb.check_antipatterns | | | | ✅ | ✅ | |
| bsl_ls.lint | | | | ✅ | | |
| bsl_ls.format | | | | ✅ | | |
| git.create_branch | | | | | | ✅ |
| git.commit | | | | | | ✅ |
| git.open_pr | | | | | | ✅ |
| git.diff | | | | | | ✅ |

**Ключевое наблюдение:** Coder — пустая колонка. Это **главная защита от drift**.

## 9. System prompt — генерация из TOOL_GROUPS

```python
# orchestrator/prompts/system_prompt_builder.py
"""Сборка system prompt для каждого агента.

Промпт включает:
- Persona (из soul.template.md)
- Описание роли (из TOOL_GROUPS)
- Список разрешённых tools (только свои)
- DON'T list + MUST list для подзадачи (если есть)
- Constraints_reminder из state
"""
from jinja2 import Template
from .tool_groups import AgentRole, TOOL_GROUPS


SYSTEM_PROMPT_TEMPLATE = """
Ты — {{ persona }}.

## Твоя роль: {{ role }}

## Разрешённые инструменты
{% if tools %}
{% for tool in tools %}
- `{{ tool.name }}`: {{ tool.description }}
{% endfor %}
{% else %}
У тебя НЕТ инструментов. Только генерация кода на основе контекста.
{% endif %}

## Ограничения
{% for dont in constraints.dont_list %}
- НЕ {{ dont }}
{% endfor %}

{% for must in constraints.must_list %}
- ОБЯЗАТЕЛЬНО {{ must }}
{% endfor %}

## Доступные модули
{% for module in constraints.available_modules %}
- {{ module }}
{% endfor %}

{% if constraints_reminder %}
## НАПОМИНАНИЕ
{{ constraints_reminder }}
{% endif %}
"""


def build_system_prompt(
    role: AgentRole,
    persona: str,
    constraints: dict | None = None,
    constraints_reminder: str = "",
    tool_descriptions: list[dict] | None = None,
) -> str:
    """Собрать system prompt для агента.

    tool_descriptions: если None — берётся из TOOL_GROUPS автоматически.
    """
    if tool_descriptions is None:
        # Собрать описания только разрешённых tools
        tool_descriptions = _get_tool_descriptions_for_role(role)

    template = Template(SYSTEM_PROMPT_TEMPLATE)
    return template.render(
        persona=persona,
        role=role.value,
        tools=tool_descriptions,
        constraints=constraints or {"dont_list": [], "must_list": [], "available_modules": []},
        constraints_reminder=constraints_reminder,
    )


def _get_tool_descriptions_for_role(role: AgentRole) -> list[dict]:
    """Только описания tools, разрешённых роли."""
    from mcp_servers.shared.protocol import ToolContract
    from .tool_provider import make_tool_provider

    provider = make_tool_provider(role)
    return [{"name": t.name, "description": t.description} for t in provider.get_tools()]
```

## 10. Взаимосвязь с другими шагами

| Шаг | Связь |
|---|---|
| Шаг 4 (Pipeline contracts) | Узлы pipeline создают `ToolProvider(AgentRole.X)` перед LLM-вызовом |
| Шаг 5 (MCP tool contracts) | `required_role` каждого tool должен совпадать с распределением в TOOL_GROUPS |
| Шаг 7 (KB-as-code) | `kb.check_antipatterns`, `kb.get_pattern` — их output-формат фиксируется YAML-schema |
| Шаг 8 (Facade) | `run_cli` proxy вызывает `ToolProvider.has_tool()` перед пробросом к скрытому tool'у |

## 11. Что НЕ делает TOOL_GROUPS

- **Не управляет промптами** — это в `prompts/system_prompt_builder.py`
- **Не реализует MCP-серверы** — это `mcp_servers/{server}/server.py`
- **Не запускает MCP-серверы** — это `1c-ai mcp serve --server NAME` (CLI)
- **Не хранит state** — это `TaskState` + `PostgresSaver`

TOOL_GROUPS — это **декларация**. Исполнение — в `ToolProvider`.

---

**Шаг 6 завершён.** Следующий — Шаг 7: KB-as-code формат — YAML-schema для паттернов и антипаттернов, которые `kb.get_pattern`, `kb.check_antipatterns` и `kb.get_antipattern` отдают агентам.
