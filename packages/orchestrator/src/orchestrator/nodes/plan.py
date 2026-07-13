"""plan node — декомпозиция задачи на подзадачи (LLM Planner).

Sprint 3: LLM planner через planner.system.j2 промпт.
Если LLM недоступен — fallback на single subtask (Sprint 2 логика).
Stage 4 (TD-S6-01): + metadata_server DI (ADR-0005 compliance —
TOOL_GROUPS[PLANNER] включает metadata.get_dependency_graph). Реальный вызов —
когда planner научится определять target object из description (future).

См. ADR-0004 (Hierarchical orchestration), ADR-0009 (Pipeline contracts),
ADR-0005 (TOOL_GROUPS), D-2026-07-13-10.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from parsers.models import ObjectRef
from pydantic import BaseModel, Field

from ..logging import get_logger
from ..state import FSMState, Subtask, TaskState

log = get_logger(__name__)

PROMPT_PATH = str(
    Path(__file__).parent.parent.parent.parent.parent.parent / "knowledge-base" / "prompts" / "planner.system.j2"
)


async def plan_node(
    state: TaskState,
    llm: Any = None,
    metadata_server: Any = None,
) -> dict[str, Any]:
    """Декомпозировать задачу на подзадачи через LLM.

    Sprint 3: LLM planner с structured_output.
    Если LLM недоступен — fallback на single subtask.
    Stage 4 (TD-S6-01): metadata_server DI (ADR-0005 compliance).

    Args:
        state: текущее состояние pipeline.
        llm: LLM инстанс. Если None — создаётся из env.
        metadata_server: MetadataServer инстанс для структурного анализа
            (dependency graph). Если None — dep_graph_summary=None.
            Stage 4: signature контракт-совместим; реальный вызов — когда
            planner научится определять target object из description (future).

    Returns:
        dict с subtasks, plan_result, fsm_state.
    """
    log.info("plan_start", task_id=state.task_id, description=state.description[:100])

    subtasks: list[Subtask] = []
    strategy: str = "single"
    rationale: str = ""

    try:
        if llm is None:
            from ..llm import create_llm

            llm = create_llm()

        # Stage 4 (TD-S6-01): dep_graph_summary через metadata_server.
        # Пока None — planner не знает target object на этом этапе.
        # Future: LLM tool calling или pre-parsing description для object_ref.
        dep_graph_summary: str | None = None
        if metadata_server is not None:
            # Заглушка: signature контракт-совместим, реальный вызов — future.
            log.debug("plan_metadata_available", hint="metadata_server ready for future use")

        # Рендерим промпт
        from ..llm import render_prompt

        prompt_text = render_prompt(
            PROMPT_PATH,
            task_description=state.description,
            config_name=state.config_name,
            config_version=state.config_version,
            dep_graph_summary=dep_graph_summary,
        )

        # Вызов LLM с structured_output
        from langchain_core.messages import HumanMessage, SystemMessage

        llm_with_output = llm.with_structured_output(PlanOutput)
        messages = [
            SystemMessage(content=prompt_text),
            HumanMessage(content="Декомпозируй задачу на подзадачи."),
        ]
        response = await llm_with_output.ainvoke(messages)

        assert isinstance(response, PlanOutput)

        strategy = response.strategy
        rationale = response.rationale

        # Конвертируем LLM subtasks в Subtask модели
        for st_data in response.subtasks:
            try:
                target_module = _parse_object_ref(st_data.target_module)
                subtask = Subtask(
                    id=st_data.id or str(uuid4()),
                    name=st_data.name,
                    target_module=target_module,
                    description=st_data.description,
                    acceptance_criteria=st_data.acceptance_criteria,
                    max_iterations=st_data.max_iterations,
                )
                subtasks.append(subtask)
            except Exception as exc:
                log.warning("plan_subtask_parse_error", error=str(exc))

        if not subtasks:
            raise ValueError("LLM returned no valid subtasks")

        log.info(
            "plan_llm_done",
            task_id=state.task_id,
            subtask_count=len(subtasks),
            strategy=strategy,
        )

    except Exception as exc:
        log.warning("plan_llm_fallback", error=str(exc)[:200])

        # Fallback: single subtask (Sprint 2 логика)
        subtask = Subtask(
            id=str(uuid4()),
            name="ГенерацияКода",
            target_module=ObjectRef(type="CommonModule", name="СгенерированныйМодуль"),
            description=state.description,
            acceptance_criteria=[
                "Код компилируется без ошибок BSL LS",
                "Код соответствует стандартам 1С",
            ],
            max_iterations=3,
        )
        subtasks = [subtask]
        strategy = "single"
        rationale = f"Fallback (LLM unavailable): {str(exc)[:100]}"

        log.info("plan_fallback", task_id=state.task_id, subtask_count=1)

    plan_result = {
        "subtasks": [s.model_dump(mode="json") for s in subtasks],
        "decomposition_strategy": strategy,
        "rationale": rationale,
    }

    return {
        "subtasks": subtasks,
        "plan_result": plan_result,
        "fsm_state": FSMState.GATHERING,
    }


def _parse_object_ref(ref_str: str) -> ObjectRef:
    """Парсить строку вида 'Catalog.Товары' → ObjectRef.

    Если строка невалидна — возвращает CommonModule.Unknown.
    """
    if not ref_str or "." not in ref_str:
        return ObjectRef(type="CommonModule", name="Unknown")
    try:
        return ObjectRef.from_string(ref_str)
    except Exception:
        return ObjectRef(type="CommonModule", name="Unknown")


class PlanSubtaskOutput(BaseModel):
    """Подзадача в выводе LLM Planner'а."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    target_module: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    max_iterations: int = Field(default=3, ge=1, le=5)


class PlanOutput(BaseModel):
    """Structured output для Planner'а."""

    strategy: str = Field(description="feature | refactor | bugfix | single")
    rationale: str
    subtasks: list[PlanSubtaskOutput]
