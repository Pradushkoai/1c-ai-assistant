"""code node — LLM генерация BSL-кода (simple node, без инструментов).

Coder НЕ имеет MCP-инструментов (TOOL_GROUPS[CODER] = {}).
Получает контекст от Gatherer и только генерирует.

См. ADR-0004 (Hierarchical orchestration), ADR-0005 (Coder без инструментов),
ADR-0009 (Pipeline contracts), docs/architecture/10-prompts-spec.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contracts import GatherResult
from ..logging import get_logger
from ..state import FSMState, Iteration, TaskState

log = get_logger(__name__)

# Путь к Jinja2 промпту
PROMPT_PATH = str(Path(__file__).parent.parent.parent.parent.parent / "knowledge-base" / "prompts" / "coder.system.j2")


async def code_node(state: TaskState, llm: Any = None) -> dict[str, Any]:
    """Сгенерировать BSL-код через LLM с structured_output.

    Coder не имеет MCP-инструментов (TOOL_GROUPS[CODER] = {}).
    Получает контекст от Gatherer и только генерирует.

    Args:
        state: текущее состояние pipeline.
        llm: LLM инстанс (BaseChatModel). Если None — создаётся из env.

    Returns:
        dict с iterations (новая Iteration добавлена), current_iteration, fsm_state.

    Raises:
        RuntimeError: если LLM не сконфигурирована.
    """
    subtask = state.current_subtask
    assert subtask is not None

    iteration_number = state.current_iteration + 1

    log.info(
        "code_start",
        task_id=state.task_id,
        subtask_id=subtask.id,
        iteration=iteration_number,
    )

    # Создаём LLM если не передан
    if llm is None:
        from ..llm import create_llm

        llm = create_llm()

    # GatherResult из state
    gather_result: GatherResult | None = None
    if state.gather_result:
        gather_result = GatherResult.model_validate(state.gather_result)

    # Предыдущая итерация (для retry)
    prev_iteration = state.iterations[-1] if state.iterations else None

    # Рендерим промпт
    from ..llm import render_prompt

    prompt_text = render_prompt(
        PROMPT_PATH,
        subtask=subtask,
        gather_result=gather_result,
        prev_iteration=prev_iteration,
        constraints_reminder=state.constraints_reminder,
        applied_pattern=None,
    )

    # Вызов LLM с structured_output
    from ..contracts import CodeResult

    llm_with_output = llm.with_structured_output(CodeResult)
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [
        SystemMessage(content=prompt_text),
        HumanMessage(content="Сгенерируй BSL-код."),
    ]
    response = await llm_with_output.ainvoke(messages)

    assert isinstance(response, CodeResult)

    # Создаём Iteration
    iteration = Iteration(
        number=iteration_number,
        code=response.code,
        llm_response=response.model_dump(mode="json"),
    )

    log.info(
        "code_done",
        task_id=state.task_id,
        subtask_id=subtask.id,
        iteration=iteration_number,
        code_lines=iteration.code.count("\n") + 1,
    )

    return {
        "current_iteration": iteration_number,
        "iterations": [*state.iterations, iteration],
        "fsm_state": FSMState.VALIDATING,
    }
