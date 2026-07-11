"""ToolProvider — отдаёт LLM только разрешённые для роли инструменты.

Реализует 2 уровня изоляции:
1. Prompt-level: в system prompt LLM видит только свои tools
2. MCP-level: каждый вызов tool'а проверяет caller_role

См. ADR-0005 (TOOL_GROUPS registry) и ADR-0011 (декларативное распределение).
"""

from __future__ import annotations

from .tool_groups import TOOL_GROUPS, AgentRole


class ToolProvider:
    """Отдаёт инструменты для конкретной роли.

    Каждая роль создаёт свой ToolProvider:
        provider = ToolProvider(AgentRole.GATHERER)
        allowed = provider.allowed_tools  # frozenset[str]
    """

    def __init__(self, role: AgentRole) -> None:
        self.role = role
        self._allowed: frozenset[str] = self._compute_allowed()

    def _compute_allowed(self) -> frozenset[str]:
        """Какие tools разрешены этой роли?"""
        role_tools: set[str] = set()
        for tools_set in TOOL_GROUPS[self.role].values():
            role_tools.update(tools_set)
        return frozenset(role_tools)

    @property
    def allowed_tools(self) -> frozenset[str]:
        """Множество разрешённых tool names."""
        return self._allowed

    def has_tool(self, tool_name: str) -> bool:
        """Проверка: разрешён ли tool этой роли?"""
        return tool_name in self._allowed

    def get_tools_by_server(self) -> dict[str, frozenset[str]]:
        """Вернуть tools по серверам для этой роли."""
        return dict(TOOL_GROUPS[self.role])


def make_tool_provider(role: AgentRole) -> ToolProvider:
    """Создать ToolProvider для роли.

    Args:
        role: роль агента (PLANNER, GATHERER, CODER, VALIDATOR, REVIEWER, COMMITTER).

    Returns:
        ToolProvider с разрешёнными tools.

    Examples:
        >>> from orchestrator.tool_groups import AgentRole
        >>> from orchestrator.tool_provider import make_tool_provider
        >>> provider = make_tool_provider(AgentRole.CODER)
        >>> provider.allowed_tools
        frozenset()
    """
    return ToolProvider(role)


def get_all_tool_names() -> frozenset[str]:
    """Все tool names из всех TOOL_GROUPS (для CI-проверок).

    Returns:
        frozenset всех tool names, разрешённых хотя бы одной роли.
    """
    all_tools: set[str] = set()
    for servers in TOOL_GROUPS.values():
        for tools in servers.values():
            all_tools.update(tools)
    return frozenset(all_tools)


def get_tools_for_role(role: AgentRole) -> frozenset[str]:
    """Удобная функция: получить tools для роли без создания ToolProvider."""
    return ToolProvider(role).allowed_tools
