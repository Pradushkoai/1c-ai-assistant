"""Сборка главного StateGraph через LangGraph.

Детерминированный backbone:
  preflight → plan → gather → code → validate → review → commit → end
                                                   ↘ retry → code
                                                   ↘ escalate → end

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from .nodes import (
    code_node,
    commit_node,
    escalate_node,
    gather_node,
    next_subtask_node,
    plan_node,
    preflight_node,
    retry_node,
    review_node,
    validate_node,
)
from .routers import (
    route_after_commit,
    route_after_retry,
    route_after_review,
    route_after_validate,
)
from .state import TaskState

# ─── Константы для документации ─────────────────────────────────────────────

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

EDGES: list[tuple[str, str]] = [
    ("preflight", "plan"),
    ("plan", "gather"),
    ("gather", "code"),
    ("code", "validate"),
    ("next_subtask", "gather"),
    ("escalate", "__end__"),
]

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


def build_graph(
    checkpointer: Any = None,
    bsl_ls_server: Any = None,
    kb_server: Any = None,
    metadata_server: Any = None,
    codebase_server: Any = None,
    git_server: Any = None,
    repo_path: Any = None,
    llm: Any = None,
) -> Any:
    """Собрать главный pipeline с dependency injection.

    Sprint 3.2.1: устранены boundary violations (orchestrator → mcp_servers).
    Серверы и LLM создаются ВНЕ orchestrator и передаются сюда через DI.
    Соответствует CONCEPTUAL.md §1.1: «зависимости только вниз».

    Stage 4 (TD-S6-01): + metadata_server DI для plan/gather (ADR-0003/0005/0010).
    Stage 4 (TD-S6-02): + git_server + repo_path DI для commit (ADR-0004/0005/0010).
    Stage 7 (TD-S9-03): + codebase_server DI для gather/review.
    """
    from functools import partial

    from langgraph.checkpoint.memory import MemorySaver

    graph = StateGraph(TaskState)

    # Узлы — с пробросом зависимостей через partial.
    graph.add_node("preflight", preflight_node)
    # Stage 4: plan_node + gather_node получают metadata_server (ADR-0005 compliance).
    graph.add_node(
        "plan",
        partial(plan_node, llm=llm, metadata_server=metadata_server) if llm or metadata_server else plan_node,
    )
    graph.add_node(
        "gather",
        partial(gather_node, kb_server=kb_server, metadata_server=metadata_server, codebase_server=codebase_server),
    )
    graph.add_node("code", partial(code_node, llm=llm) if llm else code_node)
    graph.add_node("validate", partial(validate_node, bsl_ls_server=bsl_ls_server, kb_server=kb_server))
    graph.add_node(
        "review",
        partial(review_node, llm=llm, kb_server=kb_server, codebase_server=codebase_server)
        if llm
        else partial(review_node, kb_server=kb_server, codebase_server=codebase_server),
    )
    graph.add_node("retry", retry_node)
    # Stage 4 (TD-S6-02): commit_node получает git_server + repo_path (ADR-0005 COMMITTER).
    graph.add_node(
        "commit",
        partial(commit_node, git_server=git_server, repo_path=repo_path) if git_server or repo_path else commit_node,
    )
    graph.add_node("escalate", escalate_node)
    graph.add_node("next_subtask", next_subtask_node)

    # Рёбра — детерминированный backbone
    graph.set_entry_point("preflight")
    graph.add_edge("preflight", "plan")
    graph.add_edge("plan", "gather")
    graph.add_edge("gather", "code")
    graph.add_edge("code", "validate")

    # Validate → {review | retry}
    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {"review": "review", "retry": "retry"},
    )

    # Review → {commit | retry | escalate}
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {"commit": "commit", "retry": "retry", "escalate": "escalate"},
    )

    # Retry → {code | escalate}
    graph.add_conditional_edges(
        "retry",
        route_after_retry,
        {"code": "code", "escalate": "escalate"},
    )

    # Commit → {next_subtask | end}
    graph.add_conditional_edges(
        "commit",
        route_after_commit,
        {"next_subtask": "next_subtask", "end": END},
    )

    # next_subtask → gather (новая подзадача)
    graph.add_edge("next_subtask", "gather")

    # Escalate → END
    graph.add_edge("escalate", END)

    return graph.compile(checkpointer=checkpointer or MemorySaver())


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
