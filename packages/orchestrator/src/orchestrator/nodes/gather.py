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

    # Sprint 3.2.1: kb_server должен передаваться через DI.
    # Создание сервера — ответственность agent/facade, не orchestrator.
    if kb_server is None:
        log.warning("gather_kb_not_provided", hint="Use build_graph(kb_server=...)")

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

    # ─── Sprint 4.2 (TD-S4.2-07): api-reference ────────────────────────────
    # Загружаем export-методы конфигурации, чтобы Coder видел существующий API
    available_methods: list[dict[str, Any]] = []
    try:
        from data_layer import PathManager
        from parsers.indexers import load_api_reference

        pm = PathManager()
        api_ref_path = pm.unified_metadata_index(state.config_name, state.config_version).parent / "api-reference.json"
        api_ref = load_api_reference(api_ref_path)
        if api_ref is not None:
            # Ищем методы для целевого объекта
            from parsers.indexers import get_methods_for_object
            target_ref = str(subtask.target_module)
            available_methods = get_methods_for_object(api_ref, target_ref)
            mcp_calls_made.append("api_reference.get_methods")

            if available_methods:
                summary_lines.append(f"\n## Существующие методы ({target_ref}):")
                for m in available_methods[:10]:
                    params = ", ".join(m.get("parameters", []))
                    kind = "Функция" if m.get("is_function") else "Процедура"
                    summary_lines.append(f"- {kind} {m['name']}({params})")
                if len(available_methods) > 10:
                    summary_lines.append(f"... и ещё {len(available_methods) - 10} методов")
    except Exception as exc:
        log.warning("gather_api_reference_error: %s", exc)

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
