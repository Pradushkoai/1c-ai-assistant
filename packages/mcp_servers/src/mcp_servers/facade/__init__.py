"""mcp_servers.facade — 8 lifecycle tools (TD-S5-02, ADR-0013).

Контракты, handlers, MCP server. 8 tools: plan, gather, generate, validate,
review, explain, run_cli, data_status.

См. ADR-0013 (Agent-Facade — 7 lifecycle tools + data_status).
"""

from __future__ import annotations

from .contracts import (
    DataStatusOutput,
    ExplainInput,
    ExplainOutput,
    GatherInput,
    GatherOutput,
    GenerateInput,
    GenerateOutput,
    NextAction,
    PlanInput,
    PlanOutput,
    ReviewInput,
    ReviewOutput,
    RunCliInput,
    RunCliOutput,
    ValidateInput,
    ValidateOutput,
)
from .handlers import FacadeHandlers
from .next_action import (
    after_gather,
    after_generate,
    after_plan,
    after_review,
    after_validate,
)
from .server import create_facade_server, run_facade_server, run_sync
from .state_store import FacadeStateStore
from .tool_definitions import FACADE_TOOL_NAMES, FACADE_TOOLS

__all__ = [
    # contracts
    "NextAction",
    "PlanInput",
    "PlanOutput",
    "GatherInput",
    "GatherOutput",
    "GenerateInput",
    "GenerateOutput",
    "ValidateInput",
    "ValidateOutput",
    "ReviewInput",
    "ReviewOutput",
    "ExplainInput",
    "ExplainOutput",
    "RunCliInput",
    "RunCliOutput",
    "DataStatusOutput",
    # handlers
    "FacadeHandlers",
    # state store (TD-S7-01)
    "FacadeStateStore",
    # server
    "create_facade_server",
    "run_facade_server",
    "run_sync",
    # next_action builders
    "after_plan",
    "after_gather",
    "after_generate",
    "after_validate",
    "after_review",
    # tool definitions
    "FACADE_TOOL_NAMES",
    "FACADE_TOOLS",
]
