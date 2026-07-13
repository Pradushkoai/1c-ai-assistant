"""Тесты для mcp_servers контрактов — 21 tools + Facade (5 KB + 2 standards TD-S4.2-03)."""

from __future__ import annotations

import pytest

from mcp_servers.bsl_ls.contracts import BSL_LS_TOOLS
from mcp_servers.codebase.contracts import CODEBASE_TOOLS
from mcp_servers.facade import FACADE_TOOL_NAMES, FACADE_TOOLS
from mcp_servers.git.contracts import GIT_TOOLS
from mcp_servers.kb.contracts import KB_TOOLS
from mcp_servers.metadata.contracts import METADATA_TOOLS
from mcp_servers.shared import ToolContract, ToolError


ALL_DOMAIN_TOOLS = METADATA_TOOLS + CODEBASE_TOOLS + KB_TOOLS + BSL_LS_TOOLS + GIT_TOOLS


# ─── ToolError ──────────────────────────────────────────────────────────────


class TestToolError:
    @pytest.mark.smoke
    def test_create(self):
        err = ToolError("test error")
        assert str(err) == "test error"
        assert err.code == "TOOL_ERROR"
        assert err.details == {}

    def test_with_code(self):
        err = ToolError("test", code="CUSTOM_CODE")
        assert err.code == "CUSTOM_CODE"

    def test_with_details(self):
        err = ToolError("test", details={"tool": "metadata.get_metadata"})
        assert err.details["tool"] == "metadata.get_metadata"

    def test_is_exception(self):
        err = ToolError("test")
        assert isinstance(err, Exception)


# ─── 21 domain tools — CI-проверки ─────────────────────────────────────────


class TestDomainToolsCount:
    @pytest.mark.smoke
    def test_total_21_tools(self):
        assert len(ALL_DOMAIN_TOOLS) == 21

    def test_metadata_4(self):
        assert len(METADATA_TOOLS) == 4

    def test_codebase_4(self):
        assert len(CODEBASE_TOOLS) == 4

    def test_kb_7(self):
        # 5 базовых + 2 standards (TD-S4.2-03): get_standard, check_standards
        assert len(KB_TOOLS) == 7

    def test_bsl_ls_2(self):
        assert len(BSL_LS_TOOLS) == 2

    def test_git_4(self):
        assert len(GIT_TOOLS) == 4


class TestToolNames:
    @pytest.mark.smoke
    def test_names_unique(self):
        names = [t.name for t in ALL_DOMAIN_TOOLS]
        assert len(names) == len(set(names)), f"Duplicate tool names: {names}"

    def test_names_follow_convention(self):
        """Все имена вида '{server}.{action}'."""
        for tool in ALL_DOMAIN_TOOLS:
            assert "." in tool.name, f"Invalid tool name: {tool.name}"
            server, action = tool.name.split(".", 1)
            assert server in {"metadata", "codebase", "kb", "bsl_ls", "git"}
            assert action.islower()

    def test_all_names(self):
        expected_names = {
            "metadata.get_metadata",
            "metadata.get_form_structure",
            "metadata.get_api_reference",
            "metadata.get_dependency_graph",
            "codebase.semantic_search",
            "codebase.get_module",
            "codebase.get_similar",
            "codebase.call_graph",
            "kb.get_pattern",
            "kb.get_antipattern",
            "kb.search_kb",
            "kb.check_method_availability",
            "kb.check_antipatterns",
            "kb.get_standard",
            "kb.check_standards",
            "bsl_ls.lint",
            "bsl_ls.format",
            "git.create_branch",
            "git.commit",
            "git.open_pr",
            "git.diff",
        }
        actual_names = {t.name for t in ALL_DOMAIN_TOOLS}
        assert actual_names == expected_names


class TestToolAttributes:
    @pytest.mark.smoke
    def test_all_tools_have_required_attributes(self):
        for tool in ALL_DOMAIN_TOOLS:
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert hasattr(tool, "input_schema")
            assert hasattr(tool, "output_model")
            assert hasattr(tool, "error_contract")
            assert hasattr(tool, "timeout")
            assert hasattr(tool, "idempotent")
            assert hasattr(tool, "required_role")

    def test_all_timeouts_positive(self):
        for tool in ALL_DOMAIN_TOOLS:
            assert tool.timeout > 0, f"{tool.name}: timeout must be positive"

    def test_error_contract_valid(self):
        valid_contracts = {"exception", "error_dict", "empty_result"}
        for tool in ALL_DOMAIN_TOOLS:
            assert tool.error_contract in valid_contracts

    def test_required_role_valid(self):
        valid_roles = {"PLANNER", "GATHERER", "CODER", "VALIDATOR", "REVIEWER", "COMMITTER"}
        for tool in ALL_DOMAIN_TOOLS:
            assert tool.required_role in valid_roles, f"{tool.name}: invalid role {tool.required_role}"

    def test_input_schema_is_dict(self):
        for tool in ALL_DOMAIN_TOOLS:
            assert isinstance(tool.input_schema, dict)

    def test_output_model_is_basemodel_subclass(self):
        from pydantic import BaseModel

        for tool in ALL_DOMAIN_TOOLS:
            assert issubclass(tool.output_model, BaseModel)


class TestToolCallNotImplemented:
    """Все 19 tools должны возвращать NotImplementedError в Sprint 1.5."""

    @pytest.mark.asyncio
    async def test_all_tools_raise_not_implemented(self):
        for tool_class in ALL_DOMAIN_TOOLS:
            instance = tool_class()
            with pytest.raises(NotImplementedError):
                await instance()


# ─── Facade tools ───────────────────────────────────────────────────────────


class TestFacadeTools:
    @pytest.mark.smoke
    def test_8_facade_tools(self):
        assert len(FACADE_TOOL_NAMES) == 8

    def test_facade_tool_names(self):
        expected = {
            "plan",
            "gather",
            "generate",
            "validate",
            "review",
            "explain",
            "run_cli",
            "data_status",
        }
        assert expected == FACADE_TOOL_NAMES

    def test_facade_tools_list(self):
        assert len(FACADE_TOOLS) == 8
        for tool in FACADE_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool


class TestFacadeHandlers:
    @pytest.mark.asyncio
    async def test_all_handlers_raise_not_implemented(self):
        from mcp_servers.facade.handlers import FacadeHandlers

        handlers = FacadeHandlers()
        methods = [
            handlers.handle_plan,
            handlers.handle_gather,
            handlers.handle_generate,
            handlers.handle_validate,
            handlers.handle_review,
            handlers.handle_explain,
            handlers.handle_run_cli,
            handlers.handle_data_status,
        ]
        for method in methods:
            with pytest.raises(NotImplementedError):
                await method({})


class TestNextActionBuilders:
    @pytest.mark.smoke
    def test_after_plan_with_subtask(self):
        from mcp_servers.facade.next_action import after_plan

        action = after_plan("plan-001", "st-001")
        assert action.tool == "gather"
        assert action.args["plan_id"] == "plan-001"
        assert action.args["subtask_id"] == "st-001"

    def test_after_plan_without_subtask(self):
        from mcp_servers.facade.next_action import after_plan

        action = after_plan("plan-001", None)
        assert action.tool == "data_status"

    def test_after_gather(self):
        from mcp_servers.facade.next_action import after_gather

        action = after_gather("plan-001", "st-001")
        assert action.tool == "generate"

    def test_after_generate(self):
        from mcp_servers.facade.next_action import after_generate

        action = after_generate("plan-001", "st-001", 1)
        assert action.tool == "validate"
        assert "st-001#1" in action.args["artifact_id"]

    def test_after_validate_passed(self):
        from mcp_servers.facade.next_action import after_validate

        action = after_validate("plan-001", "st-001", 1, passed=True)
        assert action.tool == "review"

    def test_after_validate_failed(self):
        from mcp_servers.facade.next_action import after_validate

        action = after_validate("plan-001", "st-001", 1, passed=False)
        assert action.tool == "generate"
        assert action.args["iteration"] == 2

    def test_after_review_proceed_with_next(self):
        from mcp_servers.facade.next_action import after_review

        action = after_review("plan-001", "st-001", 1, "proceed", next_subtask_id="st-002")
        assert action.tool == "gather"
        assert action.args["subtask_id"] == "st-002"

    def test_after_review_proceed_last(self):
        from mcp_servers.facade.next_action import after_review

        action = after_review("plan-001", "st-001", 1, "proceed", next_subtask_id=None)
        assert action.tool == "data_status"

    def test_after_review_retry(self):
        from mcp_servers.facade.next_action import after_review

        action = after_review("plan-001", "st-001", 1, "retry")
        assert action.tool == "generate"
        assert action.args["iteration"] == 2

    def test_after_review_escalate(self):
        from mcp_servers.facade.next_action import after_review

        action = after_review("plan-001", "st-001", 1, "escalate")
        assert action.tool == "data_status"


class TestGraphStructure:
    """Каркас графа — константы и get_graph_structure."""

    @pytest.mark.smoke
    def test_get_graph_structure(self):
        from orchestrator.graph import get_graph_structure

        structure = get_graph_structure()
        assert "entry_point" in structure
        assert "nodes" in structure
        assert "edges" in structure
        assert "conditional_edges" in structure

    def test_graph_has_10_nodes(self):
        from orchestrator.graph import NODES

        assert len(NODES) == 10

    def test_build_graph_compiles(self):
        from orchestrator.graph import build_graph

        graph = build_graph()
        assert graph is not None
        assert hasattr(graph, "nodes")
