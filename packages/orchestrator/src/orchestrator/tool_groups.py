"""TOOL_GROUPS registry — декларативное распределение инструментов по ролям.

Этот файл — единственный источник правды.
Все остальные модули импортируют TOOL_GROUPS и/или MULTI_ROLE_OK.

См. ADR-0005 (TOOL_GROUPS registry) и ADR-0011 (декларативное распределение).
"""

from __future__ import annotations

from enum import StrEnum

# MCPServer — для удобства чтения, не enforcement
MCPServer = str  # "metadata" | "codebase" | "kb" | "bsl_ls" | "git"
ToolName = str  # "metadata.get_metadata" | ...


class AgentRole(StrEnum):
    """Роли агентов в pipeline. Соответствуют узлам графа (Шаг 4)."""

    PLANNER = "PLANNER"  # Plan subgraph
    GATHERER = "GATHERER"  # Gather subgraph
    CODER = "CODER"  # Code node — без инструментов
    VALIDATOR = "VALIDATOR"  # Validate subgraph
    REVIEWER = "REVIEWER"  # Review subgraph
    COMMITTER = "COMMITTER"  # Commit node


TOOL_GROUPS: dict[AgentRole, dict[MCPServer, frozenset[ToolName]]] = {
    AgentRole.PLANNER: {
        "metadata": frozenset(
            {
                "metadata.get_dependency_graph",  # структурный анализ для декомпозиции
            }
        ),
        "kb": frozenset(
            {
                "kb.search_kb",  # поиск релевантных паттернов/стандартов
            }
        ),
    },
    AgentRole.GATHERER: {
        "metadata": frozenset(
            {
                "metadata.get_metadata",  # метаданные target-объекта
                "metadata.get_form_structure",  # форма (если задача про форму)
                "metadata.get_api_reference",  # API общих модулей, которые можно вызывать
            }
        ),
        "codebase": frozenset(
            {
                "codebase.semantic_search",  # поиск похожего кода
                "codebase.get_module",  # полный модуль для примера
                "codebase.call_graph",  # граф вызовов (кто кого вызывает)
            }
        ),
        "kb": frozenset(
            {
                "kb.get_pattern",  # эталонный паттерн
                "kb.check_method_availability",  # доступность методов в контексте
            }
        ),
    },
    AgentRole.CODER: {
        # CODER НЕ ИМЕЕТ ИНСТРУМЕНТОВ.
        # Это критично — Coder генерирует код из собранного Gather'ом контекста.
        # Если Coder получит semantic_search, он начнёт "исследовать" вместо генерации.
    },
    AgentRole.VALIDATOR: {
        "bsl_ls": frozenset(
            {
                "bsl_ls.lint",  # 187 диагностик — главный gate
                "bsl_ls.format",  # форматирование (опционально)
            }
        ),
        "kb": frozenset(
            {
                "kb.check_antipatterns",  # YAML-правила
                "kb.check_method_availability",  # context violations (server vs client)
            }
        ),
    },
    AgentRole.REVIEWER: {
        "kb": frozenset(
            {
                "kb.get_antipattern",  # полное описание антипаттерна по id
                "kb.check_antipatterns",  # повторная проверка (LLM может просить)
            }
        ),
        "codebase": frozenset(
            {
                "codebase.get_similar",  # похожие модули — есть ли pattern в кодовой базе
            }
        ),
    },
    AgentRole.COMMITTER: {
        "git": frozenset(
            {
                "git.create_branch",
                "git.commit",
                "git.open_pr",
                "git.diff",
            }
        ),
    },
}


# Tools, которые законно принадлежат нескольким ролям.
# Каждый случай — с обоснованием в комментарии.
MULTI_ROLE_OK: dict[ToolName, list[AgentRole]] = {
    "kb.check_method_availability": [
        AgentRole.GATHERER,  # Gatherer проверяет методы, которые Coder может вызвать
        AgentRole.VALIDATOR,  # Validator проверяет, что Coder не нарушил контекст
    ],
    "kb.check_antipatterns": [
        AgentRole.VALIDATOR,  # Validator детектирует антипаттерны
        AgentRole.REVIEWER,  # Reviewer повторно проверяет + интерпретирует
    ],
}


def _validate_multi_role() -> None:
    """Проверка при импорте: MULTI_ROLE_OK согласован с TOOL_GROUPS.

    Raises:
        RuntimeError: если MULTI_ROLE_OK не соответствует TOOL_GROUPS.
    """
    for tool_name, expected_roles in MULTI_ROLE_OK.items():
        actual_roles = [
            role for role, servers in TOOL_GROUPS.items() for tools in servers.values() if tool_name in tools
        ]
        if sorted(actual_roles, key=lambda r: r.value) != sorted(expected_roles, key=lambda r: r.value):
            raise RuntimeError(
                f"MULTI_ROLE_OK inconsistent for {tool_name}: expected {expected_roles}, actual {actual_roles}"
            )


_validate_multi_role()  # запускается при импорте модуля
