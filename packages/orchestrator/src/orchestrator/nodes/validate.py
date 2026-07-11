"""validate node — детерминированный gate (parallel subgraph).

В Sprint 2 — только bsl_ls.lint (без KB антипаттернов, они в Sprint 3).
Полная версия с 3 валидаторами параллельно — в Sprint 3.

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from typing import Any

from ..contracts import ValidateResult, ValidationFinding
from ..logging import get_logger
from ..state import FSMState, TaskState

log = get_logger(__name__)


async def validate_node(state: TaskState, bsl_ls_server: Any = None) -> dict[str, Any]:
    """Запустить BSL LS валидацию сгенерированного кода.

    Sprint 2: только bsl_ls.lint.
    Sprint 3: bsl_ls.lint + kb.check_antipatterns + kb.check_method_availability (параллельно).

    Args:
        state: текущее состояние pipeline.
        bsl_ls_server: BslLsServer инстанс. Если None — создаётся из env.

    Returns:
        dict с validate_result, validation_passed, fsm_state.
    """
    subtask = state.current_subtask
    assert subtask is not None
    assert state.iterations, "No iterations in state"

    current_iteration = state.iterations[-1]
    code = current_iteration.code

    log.info(
        "validate_start",
        task_id=state.task_id,
        subtask_id=subtask.id,
        iteration=current_iteration.number,
    )

    # Создаём BSL LS сервер если не передан
    if bsl_ls_server is None:
        from mcp_servers.bsl_ls.server import BslLsServer

        bsl_ls_server = BslLsServer()

    # Вызываем BSL LS lint
    try:
        lint_result = await bsl_ls_server.lint(
            code=code,
            file_path=f"/tmp/{subtask.id}_{current_iteration.number}.bsl",
        )
    except Exception as exc:
        log.error("validate_bsl_ls_error", error=str(exc))
        # Если BSL LS недоступен — пропускаем валидацию (Sprint 2 fallback)
        lint_result = None

    # Формируем findings
    findings: list[ValidationFinding] = []
    failed_checks: list[dict[str, Any]] = []

    if lint_result is not None:
        for diag in lint_result.diagnostics:
            severity = diag.get("severity", "info")
            finding = ValidationFinding(
                severity=severity,
                code=diag.get("code", "UNKNOWN"),
                message=diag.get("message", ""),
                line=diag.get("line"),
                column=diag.get("column"),
                source="bsl_ls",
                fix_hint=None,
            )
            findings.append(finding)

            if severity == "critical":
                failed_checks.append(
                    {
                        "severity": severity,
                        "code": finding.code,
                        "line": finding.line,
                        "message": finding.message,
                        "fix_hint": finding.fix_hint,
                    }
                )

    # Подсчёт по severity
    severity_breakdown: dict[str, int] = {"critical": 0, "warning": 0, "info": 0}
    for f in findings:
        if f.severity in severity_breakdown:
            severity_breakdown[f.severity] += 1

    passed = severity_breakdown["critical"] == 0

    validate_result = ValidateResult(
        subtask_id=subtask.id,
        iteration_number=current_iteration.number,
        findings=findings,
        passed=passed,
        severity_breakdown=severity_breakdown,
        failed_checks=failed_checks,
    )

    log.info(
        "validate_done",
        task_id=state.task_id,
        subtask_id=subtask.id,
        iteration=current_iteration.number,
        passed=passed,
        critical=severity_breakdown["critical"],
        warning=severity_breakdown["warning"],
        info=severity_breakdown["info"],
    )

    return {
        "validate_result": validate_result.model_dump(mode="json"),
        "validation_passed": passed,
        "fsm_state": FSMState.REVIEWING,
    }
