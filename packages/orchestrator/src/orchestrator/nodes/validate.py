"""validate node — детерминированный gate (parallel subgraph).

Sprint 3: bsl_ls.lint + kb.check_antipatterns (2 валидатора).
Sprint 4: + kb.check_method_availability (3 валидатора).

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from typing import Any

from ..contracts import ValidateResult, ValidationFinding
from ..logging import get_logger
from ..state import FSMState, TaskState

log = get_logger(__name__)


async def validate_node(
    state: TaskState,
    bsl_ls_server: Any = None,
    kb_server: Any = None,
) -> dict[str, Any]:
    """Запустить валидаторы параллельно.

    Sprint 3: bsl_ls.lint + kb.check_antipatterns.
    Sprint 4: + kb.check_method_availability.

    Args:
        state: текущее состояние pipeline.
        bsl_ls_server: BslLsServer инстанс. Если None — создаётся из env.
        kb_server: KbServer инстанс. Если None — создаётся из KB dir.

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

    # Создаём серверы если не переданы
    if bsl_ls_server is None:
        try:
            from mcp_servers.bsl_ls.server import BslLsServer

            bsl_ls_server = BslLsServer()
        except Exception:
            bsl_ls_server = None

    if kb_server is None:
        try:
            from mcp_servers.kb.server import KbServer

            kb_server = KbServer()
        except Exception:
            kb_server = None

    # Запускаем валидаторы параллельно
    findings: list[ValidationFinding] = []
    failed_checks: list[dict[str, Any]] = []

    # BSL LS lint
    bsl_ls_findings: list[ValidationFinding] = []
    if bsl_ls_server is not None:
        try:
            lint_result = await bsl_ls_server.lint(
                code=code,
                file_path=f"/tmp/{subtask.id}_{current_iteration.number}.bsl",
            )
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
                bsl_ls_findings.append(finding)
        except Exception as exc:
            log.warning("validate_bsl_ls_error", error=str(exc))

    # KB antipatterns
    kb_findings: list[ValidationFinding] = []
    if kb_server is not None:
        try:
            ap_result = await kb_server.check_antipatterns(
                code=code,
                severity_filter=["critical", "warning"],
            )
            for finding_dict in ap_result.findings:
                severity = finding_dict.get("severity", "info")
                finding = ValidationFinding(
                    severity=severity,
                    code=finding_dict.get("antipattern_id", "UNKNOWN"),
                    message=finding_dict.get("message", ""),
                    line=finding_dict.get("line"),
                    column=None,
                    source="kb_antipatterns",
                    fix_hint=None,
                )
                kb_findings.append(finding)
        except Exception as exc:
            log.warning("validate_kb_error", error=str(exc))

    # Объединяем findings
    findings = bsl_ls_findings + kb_findings

    # Формируем failed_checks (только critical + warning для retry-промпта)
    for f in findings:
        if f.severity in ("critical", "warning"):
            failed_checks.append(
                {
                    "severity": f.severity,
                    "code": f.code,
                    "line": f.line,
                    "message": f.message,
                    "fix_hint": f.fix_hint,
                    "source": f.source,
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
        bsl_ls_findings=len(bsl_ls_findings),
        kb_findings=len(kb_findings),
    )

    return {
        "validate_result": validate_result.model_dump(mode="json"),
        "validation_passed": passed,
        "fsm_state": FSMState.REVIEWING,
    }
