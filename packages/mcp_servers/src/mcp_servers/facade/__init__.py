"""mcp_servers.facade — 7 lifecycle tools + data_status.

Контракты и заглушки handlers. Реализация — Sprint 2-4.

См. ADR-0013 (Agent-Facade — 7 lifecycle tools).
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
