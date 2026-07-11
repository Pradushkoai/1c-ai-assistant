"""Каркас главного StateGraph.

В Sprint 1.5 (каркас) — только константы и stub build_graph().
LangGraph integration — в Sprint 2.

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from typing import Any

# ─── Узлы графа ─────────────────────────────────────────────────────────────

ENTRY_POINT = "preflight"

NODES: list[str] = [
    "preflight",
    "plan",
    "gather",
    "code",
    "validate",
    "review",
    "retry",
    "commit",
    "escalate",
    "next_subtask",
]

# ─── Рёбра — детерминированный backbone ─────────────────────────────────────

EDGES: list[tuple[str, str]] = [
    ("preflight", "plan"),
    ("plan", "gather"),
    ("gather", "code"),
    ("code", "validate"),
    # validate → conditional (review | retry)
    # review → conditional (commit | retry | escalate)
    # retry → conditional (code | escalate)
    # commit → conditional (next_subtask | end)
    ("next_subtask", "gather"),
    ("escalate", "__end__"),
]

# ─── Conditional edges ──────────────────────────────────────────────────────

CONDITIONAL_EDGES: dict[str, dict[str, list[str]]] = {
    "validate": {
        "route_after_validate": ["review", "retry"],
    },
    "review": {
        "route_after_review": ["commit", "retry", "escalate"],
    },
    "retry": {
        "route_after_retry": ["code", "escalate"],
    },
    "commit": {
        "route_after_commit": ["next_subtask", "__end__"],
    },
}


def build_graph(checkpointer: Any = None) -> Any:
    """Собрать главный pipeline.

    В Sprint 1.5 — stub, raise NotImplementedError.
    В Sprint 2 — полная реализация с LangGraph StateGraph.

    Args:
        checkpointer: LangGraph checkpointer (MemorySaver или PostgresSaver).

    Returns:
        Compiled StateGraph.

    Raises:
        NotImplementedError: в Sprint 1.5 (каркас).
    """
    raise NotImplementedError(
        "build_graph — реализация в Sprint 2 (LangGraph integration). "
        f"Каркас: ENTRY_POINT={ENTRY_POINT!r}, NODES={len(NODES)}, "
        f"EDGES={len(EDGES)}, CONDITIONAL_EDGES={len(CONDITIONAL_EDGES)}"
    )


def get_graph_structure() -> dict[str, Any]:
    """Вернуть структуру графа для документации и тестов.

    Returns:
        dict с entry_point, nodes, edges, conditional_edges.
    """
    return {
        "entry_point": ENTRY_POINT,
        "nodes": NODES,
        "edges": EDGES,
        "conditional_edges": CONDITIONAL_EDGES,
    }
