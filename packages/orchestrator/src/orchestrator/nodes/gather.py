"""gather node — сбор контекста для подзадачи.

Stage 3: KB context (паттерны + антипаттерны) через KbServer.
Stage 4 (TD-S6-01): + metadata через MetadataServer (DI, контракт-совместимо —
убран прямой FS-доступ к api-reference.json).

См. ADR-0004 (Hierarchical orchestration), ADR-0009 (Pipeline contracts),
ADR-0003 (MCP-архитектура), D-2026-07-13-10.
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
    metadata_server: Any = None,
) -> dict[str, Any]:
    """Собрать контекст: KB паттерны + антипаттерны + metadata (API reference).

    Stage 3: KB context (patterns + antipatterns) через kb_server.
    Stage 4 (TD-S6-01): + metadata (api-reference) через metadata_server.

    Args:
        state: текущее состояние pipeline.
        kb_server: KbServer инстанс. Если None — warning.
        metadata_server: MetadataServer инстанс. Если None — warning, контекст
            без API reference (backward compat для тестов без DI).

    Returns:
        dict с gather_result, fsm_state.
    """
    subtask = state.current_subtask
    assert subtask is not None

    log.info("gather_start", task_id=state.task_id, subtask_id=subtask.id)

    # Sprint 3.2.1: servers должны передаваться через DI.
    # Создание сервера — ответственность agent/facade, не orchestrator.
    if kb_server is None:
        log.warning("gather_kb_not_provided", hint="Use build_graph(kb_server=...)")
    if metadata_server is None:
        log.warning("gather_metadata_not_provided", hint="Use build_graph(metadata_server=...)")

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

    # ─── Stage 4 (TD-S6-01): api-reference через metadata_server (MCP) ──────
    # Загружаем export-методы конфигурации, чтобы Coder видел существующий API.
    # Контракт-совместимо: раньше был прямой FS-доступ (PathManager + load_api_reference),
    # теперь — через metadata_server.get_api_reference (ADR-0003, ADR-0010).
    available_methods: list[dict[str, Any]] = []
    if metadata_server is not None:
        try:
            target_ref = str(subtask.target_module)
            # Если target_module — CommonModule.X, запрашиваем API reference для X.
            # Иначе — пропускаем (api-reference только для общих модулей).
            if target_ref.startswith("CommonModule."):
                module_name = target_ref.split(".", 1)[1]
                api_ref_result = await metadata_server.get_api_reference(
                    module_name=module_name,
                    config_name=state.config_name,
                    config_version=state.config_version,
                )
                available_methods = list(api_ref_result.methods)
                mcp_calls_made.append("metadata.get_api_reference")

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
        api_methods=len(available_methods),
        mcp_calls=len(mcp_calls_made),
    )

    return {
        "gather_result": gather_result.model_dump(mode="json"),
        "fsm_state": FSMState.CODING,
    }
