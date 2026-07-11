"""Узлы pipeline — заглушки.

В Sprint 1.5 (каркас) — все узлы возвращают NotImplementedError.
Реализация:
- preflight, code, validate, retry, escalate — Sprint 2
- plan, gather, review, next_subtask — Sprint 3
- commit — Sprint 4

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from .code import code_node
from .commit import commit_node
from .escalate import escalate_node
from .gather import gather_node
from .next_subtask import next_subtask_node
from .plan import plan_node
from .preflight import preflight_node
from .retry import retry_node
from .review import review_node
from .validate import validate_node

__all__ = [
    "preflight_node",
    "plan_node",
    "gather_node",
    "code_node",
    "validate_node",
    "review_node",
    "retry_node",
    "commit_node",
    "escalate_node",
    "next_subtask_node",
]
