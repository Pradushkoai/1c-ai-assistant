"""review node — LLM-рецензент (mini-supervisor subgraph).

Sprint 3: LLM review с антипаттернами и validate результатами.
Если LLM недоступен — fallback на auto-proceed/retry.

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contracts import ReviewResult, ValidateResult
from ..logging import get_logger
from ..state import FSMState, TaskState

log = get_logger(__name__)

PROMPT_PATH = str(
    Path(__file__).parent.parent.parent.parent.parent.parent / "knowledge-base" / "prompts" / "reviewer.system.j2"
)


async def review_node(
    state: TaskState,
    llm: Any = None,
    kb_server: Any = None,
) -> dict[str, Any]:
    """LLM-рецензент: проверить код и решить proceed/retry/escalate.

    Sprint 3: LLM review с антипаттернами.
    Если LLM недоступен — fallback на auto-proceed/retry (Sprint 2 логика).

    Args:
        state: текущее состояние pipeline.
        llm: LLM инстанс. Если None — пытается создать из env.
        kb_server: KbServer для получения описаний антипаттернов.

    Returns:
        dict с review_result, review_passed, critical_findings, fsm_state.
    """
    subtask = state.current_subtask
    assert subtask is not None
    assert state.iterations, "No iterations in state"

    current_iteration = state.iterations[-1]

    log.info(
        "review_start",
        task_id=state.task_id,
        subtask_id=subtask.id,
        iteration=current_iteration.number,
    )

    # ValidateResult из state
    validate_result: ValidateResult | None = None
    if state.validate_result:
        validate_result = ValidateResult.model_validate(state.validate_result)

    # Relevant antipatterns из validate_result
    relevant_antipatterns: list[dict[str, Any]] = []
    if validate_result:
        for finding in validate_result.findings:
            if finding.source == "kb_antipatterns":
                relevant_antipatterns.append(
                    {
                        "antipattern_id": finding.code,
                        "severity": finding.severity,
                        "message": finding.message,
                    }
                )

    # Пытаемся использовать LLM
    decision: str
    rationale: str
    review_passed: bool
    critical_findings: int

    try:
        if llm is None:
            from ..llm import create_llm

            llm = create_llm()

        # Рендерим промпт
        from ..llm import render_prompt

        prompt_text = render_prompt(
            PROMPT_PATH,
            subtask=subtask,
            iteration_number=current_iteration.number,
            code=current_iteration.code,
            validate_result=validate_result,
            relevant_antipatterns=relevant_antipatterns,
        )

        # Вызов LLM с structured_output
        from langchain_core.messages import HumanMessage, SystemMessage

        llm_with_output = llm.with_structured_output(ReviewResult)
        messages = [
            SystemMessage(content=prompt_text),
            HumanMessage(content="Проверь код и реши: proceed, retry или escalate."),
        ]
        response = await llm_with_output.ainvoke(messages)

        assert isinstance(response, ReviewResult)

        decision = response.decision
        rationale = response.rationale
        review_passed = response.passed
        critical_findings = response.critical_findings

        log.info(
            "review_llm_done",
            task_id=state.task_id,
            decision=decision,
            critical_findings=critical_findings,
        )

    except Exception as exc:
        log.warning("review_llm_fallback", error=str(exc)[:200])

        # Fallback: auto-proceed/retry (Sprint 2 логика)
        if state.validation_passed:
            decision = "proceed"
            rationale = "Fallback (LLM unavailable): auto-proceed (validation passed)"
            review_passed = True
            critical_findings = 0
        else:
            decision = "retry"
            rationale = "Fallback (LLM unavailable): auto-retry (validation failed)"
            review_passed = False
            critical_findings = 1

    review_result = ReviewResult(
        subtask_id=subtask.id,
        iteration_number=current_iteration.number,
        findings=[],  # LLM findings будут в response.findings при успехе
        decision=decision,  # type: ignore[arg-type]
        rationale=rationale,
        critical_findings=critical_findings,
        passed=review_passed,
    )

    log.info(
        "review_done",
        task_id=state.task_id,
        subtask_id=subtask.id,
        iteration=current_iteration.number,
        decision=decision,
    )

    return {
        "review_result": review_result.model_dump(mode="json"),
        "review_passed": review_passed,
        "critical_findings": critical_findings,
        "fsm_state": FSMState.COMMITTING if review_passed else FSMState.CODING,
    }
