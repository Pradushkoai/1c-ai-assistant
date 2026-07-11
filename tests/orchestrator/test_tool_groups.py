"""Тесты для orchestrator.tool_groups и tool_provider — TOOL_GROUPS registry."""

from __future__ import annotations

import pytest

from orchestrator.tool_groups import (
    MULTI_ROLE_OK,
    TOOL_GROUPS,
    AgentRole,
)
from orchestrator.tool_provider import (
    ToolProvider,
    get_all_tool_names,
    get_tools_for_role,
    make_tool_provider,
)


# ─── AgentRole ──────────────────────────────────────────────────────────────


class TestAgentRole:
    @pytest.mark.smoke
    def test_all_roles(self):
        roles = list(AgentRole)
        assert len(roles) == 6
        assert AgentRole.PLANNER in roles
        assert AgentRole.GATHERER in roles
        assert AgentRole.CODER in roles
        assert AgentRole.VALIDATOR in roles
        assert AgentRole.REVIEWER in roles
        assert AgentRole.COMMITTER in roles


# ─── TOOL_GROUPS CI-проверки ───────────────────────────────────────────────


class TestToolGroups:
    @pytest.mark.smoke
    def test_coder_has_no_tools(self):
        """CRITICAL: Coder не должен иметь инструментов."""
        coder_tools: set[str] = set()
        for tools in TOOL_GROUPS[AgentRole.CODER].values():
            coder_tools.update(tools)
        assert coder_tools == set(), f"CODER must have ZERO tools, got: {coder_tools}"

    def test_all_roles_in_groups(self):
        for role in AgentRole:
            assert role in TOOL_GROUPS

    def test_no_unexpected_multi_role(self):
        """Tool принадлежит >1 роли только если в MULTI_ROLE_OK."""
        tool_to_roles: dict[str, set[AgentRole]] = {}
        for role, servers in TOOL_GROUPS.items():
            for tools in servers.values():
                for tool in tools:
                    tool_to_roles.setdefault(tool, set()).add(role)

        for tool_name, roles in tool_to_roles.items():
            if len(roles) > 1:
                assert tool_name in MULTI_ROLE_OK, (
                    f"Tool {tool_name} is in {len(roles)} roles {roles} but not in MULTI_ROLE_OK"
                )

    def test_multi_role_ok_consistent(self):
        """MULTI_ROLE_OK должен точно отражать реальное распределение."""
        for tool_name, expected_roles in MULTI_ROLE_OK.items():
            actual_roles: set[AgentRole] = set()
            for role, servers in TOOL_GROUPS.items():
                for tools in servers.values():
                    if tool_name in tools:
                        actual_roles.add(role)
            assert actual_roles == set(expected_roles), (
                f"MULTI_ROLE_OK[{tool_name}] = {expected_roles}, actual = {actual_roles}"
            )

    def test_gatherer_has_8_tools(self):
        gatherer_tools: set[str] = set()
        for tools in TOOL_GROUPS[AgentRole.GATHERER].values():
            gatherer_tools.update(tools)
        assert len(gatherer_tools) == 8

    def test_committer_has_4_tools(self):
        committer_tools: set[str] = set()
        for tools in TOOL_GROUPS[AgentRole.COMMITTER].values():
            committer_tools.update(tools)
        assert len(committer_tools) == 4

    def test_validator_has_4_tools(self):
        validator_tools: set[str] = set()
        for tools in TOOL_GROUPS[AgentRole.VALIDATOR].values():
            validator_tools.update(tools)
        assert len(validator_tools) == 4


# ─── ToolProvider ───────────────────────────────────────────────────────────


class TestToolProvider:
    @pytest.mark.smoke
    def test_coder_provider_has_no_tools(self):
        provider = make_tool_provider(AgentRole.CODER)
        assert provider.allowed_tools == frozenset()
        assert provider.has_tool("metadata.get_metadata") is False

    def test_gatherer_provider(self):
        provider = make_tool_provider(AgentRole.GATHERER)
        assert len(provider.allowed_tools) == 8
        assert provider.has_tool("metadata.get_metadata") is True
        assert provider.has_tool("codebase.semantic_search") is True
        assert provider.has_tool("kb.get_pattern") is True
        assert provider.has_tool("git.commit") is False

    def test_committer_provider(self):
        provider = make_tool_provider(AgentRole.COMMITTER)
        assert len(provider.allowed_tools) == 4
        assert provider.has_tool("git.commit") is True
        assert provider.has_tool("git.create_branch") is True
        assert provider.has_tool("metadata.get_metadata") is False

    def test_get_tools_by_server(self):
        provider = make_tool_provider(AgentRole.GATHERER)
        by_server = provider.get_tools_by_server()
        assert "metadata" in by_server
        assert "codebase" in by_server
        assert "kb" in by_server
        assert "bsl_ls" not in by_server
        assert "git" not in by_server


# ─── Helper functions ───────────────────────────────────────────────────────


class TestHelperFunctions:
    def test_get_all_tool_names(self):
        all_tools = get_all_tool_names()
        assert len(all_tools) == 19  # 19 unique tool names across all roles
        assert "metadata.get_metadata" in all_tools
        assert "git.commit" in all_tools
        assert "bsl_ls.lint" in all_tools

    def test_get_tools_for_role(self):
        coder_tools = get_tools_for_role(AgentRole.CODER)
        assert coder_tools == frozenset()

        gatherer_tools = get_tools_for_role(AgentRole.GATHERER)
        assert len(gatherer_tools) == 8
