"""gather node — сбор контекста для подзадачи.

Sprint 3: KB context (паттерны + антипаттерны) через KbServer.
Sprint 4: + metadata + codebase MCP (полный fan-out).

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from typing import Any

from ..contracts import GatheredCode, GatheredKnowledge, GatheredMetadata, GatherResult
from ..logging import get_logger
from ..state import FSMState, TaskState

log = get_logger(__name__)


async def gather_node(
    state: TaskState,
    kb_server: Any = None,
) -> dict[str, Any]:
    """Собрать контекст: KB паттерны + антипаттерны.

    Sprint 3: KB context (patterns + antipatterns).
    Sprint 4: + metadata (metadata-server) + codebase (codebase-server).

    Args:
        state: текущее состояние pipeline.
        kb_server: KbServer инстанс. Если None — создаётся.

    Returns:
        dict с gather_result, fsm_state.
    """
    subtask = state.current_subtask
    assert subtask is not None

    log.info("gather_start", task_id=state.task_id, subtask_id=subtask.id)

    # Создаём KbServer если не передан
    if kb_server is None:
        try:
            from mcp_servers.kb.server import KbServer

            kb_server = KbServer()
        except Exception as exc:
            log.warning("gather_kb_unavailable", error=str(exc))
            kb_server = None

    patterns: list[dict[str, Any]] = []
    antipatterns: list[dict[str, Any]] = []
    mcp_calls_made: list[str] = []

    # Ищем релевантные паттерны через KB
    if kb_server is not None:
        try:
            # Search KB по описанию подзадачи
            search_result = await kb_server.search_kb(
                query=subtask.description,
                top_k=3,
                category="pattern",
            )
            for result in search_result.results:
                pattern = kb_server.kb.get_pattern(result["id"])
                if pattern:
                    patterns.append(pattern)
            mcp_calls_made.append("kb.search_kb")
        except Exception as exc:
            log.warning("gather_kb_search_error", error=str(exc))

        try:
            # Получаем все critical антипаттерны для напоминания Coder'у
            all_ap = kb_server.kb.list_antipatterns(severity="critical")
            antipatterns = all_ap[:5]  # top 5 critical
            mcp_calls_made.append("kb.list_antipatterns")
        except Exception as exc:
            log.warning("gather_kb_antipatterns_error", error=str(exc))

    # Собираем context_summary для Coder'а
    summary_lines: list[str] = []
    summary_lines.append(f"## Целевой объект: {subtask.target_module}")
    summary_lines.append(f"## Задача: {subtask.description}")

    if patterns:
        summary_lines.append("\n## Релевантные паттерны:")
        for p in patterns:
            summary_lines.append(f"- **{p['title']}** ({p['id']})")
            if p.get("code_template"):
                summary_lines.append(f"  Шаблон: {p['code_template'][:200]}...")

    if antipatterns:
        summary_lines.append("\n## Критические антипаттерны (избегать!):")
        for ap in antipatterns:
            summary_lines.append(f"- **{ap['title']}** ({ap['id']}): {ap.get('recommendation_for_llm', '')[:100]}...")

    if not patterns and not antipatterns:
        summary_lines.append("\nКонтекст не собран. Действуй по стандартам 1С.")

    context_summary = "\n".join(summary_lines)

    gather_result = GatherResult(
        subtask_id=subtask.id,
        metadata=GatheredMetadata(target_object={}),
        code=GatheredCode(),
        knowledge=GatheredKnowledge(
            patterns=patterns,
            antipatterns=antipatterns,
        ),
        context_summary=context_summary,
        mcp_calls_made=mcp_calls_made,
    )

    log.info(
        "gather_done",
        task_id=state.task_id,
        subtask_id=subtask.id,
        patterns=len(patterns),
        antipatterns=len(antipatterns),
        mcp_calls=len(mcp_calls_made),
    )

    return {
        "gather_result": gather_result.model_dump(mode="json"),
        "fsm_state": FSMState.CODING,
    }
