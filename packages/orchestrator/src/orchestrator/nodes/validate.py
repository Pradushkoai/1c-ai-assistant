"""validate node — детерминированный gate (parallel fan-out через asyncio.TaskGroup).

CONCEPTUAL.md §2.1: «Внутри Validate — parallel fan-out без supervisor
(3 валидатора параллельно через asyncio.TaskGroup)»

3 валидатора:
  1. bsl_ls.lint — статический анализатор BSL LS (через HTTP)
  2. kb.check_antipatterns — regex-проверка на антипаттерны из YAML
  3. kb.check_method_availability — вызовы серверных методов на клиенте

См. ADR-0004, ADR-0009, CONCEPTUAL.md §2.1.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from ..contracts import ValidateResult, ValidationFinding
from ..logging import get_logger
from ..state import FSMState, TaskState

log = get_logger(__name__)

_METHOD_CALL_RE = re.compile(
    r"\b([A-Za-zА-Яа-я_][A-Za-zА-Яа-я0-9_]*)\s*\(",
    re.MULTILINE,
)

_BSL_KEYWORDS = {
    "Если", "Тогда", "Иначе", "ИначеЕсли", "КонецЕсли",
    "Для", "Каждого", "Из", "Цикл", "КонецЦикла",
    "Пока", "Новый", "Возврат",
    "Попытка", "Исключение", "КонецПопытки",
    "Процедура", "КонецПроцедуры",
    "Функция", "КонецФункции",
    "И", "ИЛИ", "НЕ", "Или",
    "Экспорт", "Знач", "Лок",
    "Истина", "Ложь", "Неопределено", "NULL", "Null",
    "Перем", "Переменная",
    "Else", "If", "Then", "For", "Each", "In", "Do", "EndDo",
    "Procedure", "EndProcedure", "Function", "EndFunction",
    "Try", "Exception", "EndTry",
    "New", "Return",
    "And", "Or", "Not",
    "True", "False", "Undefined",
    "Var",
}


async def validate_node(
    state: TaskState,
    bsl_ls_server: Any = None,
    kb_server: Any = None,
) -> dict[str, Any]:
    """Запустить 3 валидатора параллельно через asyncio.TaskGroup.

    Соответствует CONCEPTUAL.md §2.1: parallel fan-out без supervisor.
    Параллельное выполнение: max(t1, t2, t3) вместо sum(t1, t2, t3).
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

    if bsl_ls_server is None:
        log.warning("validate_bsl_ls_not_provided", hint="Use build_graph(bsl_ls_server=...)")
    if kb_server is None:
        log.warning("validate_kb_not_provided", hint="Use build_graph(kb_server=...)")

    target_context = "server"
    if subtask.constraints is not None:
        target_context = subtask.constraints.target_context

    # ─── Parallel fan-out через asyncio.TaskGroup ─────────────────────────────
    async with asyncio.TaskGroup() as tg:
        task_bsl_ls = tg.create_task(
            _run_bsl_ls_validator(
                bsl_ls_server=bsl_ls_server,
                code=code,
                file_path=f"/tmp/{subtask.id}_{current_iteration.number}.bsl",
            )
        )
        task_kb = tg.create_task(
            _run_kb_antipatterns_validator(
                kb_server=kb_server,
                code=code,
            )
        )
        task_methods = tg.create_task(
            _run_method_availability_validator(
                kb_server=kb_server,
                code=code,
                target_context=target_context,
                platform_version=state.platform_version,
            )
        )

    bsl_ls_findings = task_bsl_ls.result()
    kb_findings = task_kb.result()
    method_findings = task_methods.result()

    # ─── Fan-in: объединяем findings ─────────────────────────────────────────
    findings: list[ValidationFinding] = bsl_ls_findings + kb_findings + method_findings

    failed_checks: list[dict[str, Any]] = []
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
        method_findings=len(method_findings),
    )

    return {
        "validate_result": validate_result.model_dump(mode="json"),
        "validation_passed": passed,
        "fsm_state": FSMState.REVIEWING,
    }


# ─── Отдельные async-валидаторы (для parallel fan-out) ──────────────────────


async def _run_bsl_ls_validator(
    bsl_ls_server: Any,
    code: str,
    file_path: str,
) -> list[ValidationFinding]:
    """Валидатор 1: BSL LS lint через HTTP."""
    if bsl_ls_server is None:
        return []

    findings: list[ValidationFinding] = []
    try:
        lint_result = await bsl_ls_server.lint(code=code, file_path=file_path)
        for diag in lint_result.diagnostics:
            findings.append(ValidationFinding(
                severity=diag.get("severity", "info"),
                code=diag.get("code", "UNKNOWN"),
                message=diag.get("message", ""),
                line=diag.get("line"),
                column=diag.get("column"),
                source="bsl_ls",
                fix_hint=None,
            ))
    except Exception as exc:
        log.warning("validate_bsl_ls_error: %s", exc)
    return findings


async def _run_kb_antipatterns_validator(
    kb_server: Any,
    code: str,
) -> list[ValidationFinding]:
    """Валидатор 2: KB check_antipatterns (regex из YAML)."""
    if kb_server is None:
        return []

    findings: list[ValidationFinding] = []
    try:
        ap_result = await kb_server.check_antipatterns(
            code=code,
            severity_filter=["critical", "warning"],
        )
        for finding_dict in ap_result.findings:
            findings.append(ValidationFinding(
                severity=finding_dict.get("severity", "info"),
                code=finding_dict.get("antipattern_id", "UNKNOWN"),
                message=finding_dict.get("message", ""),
                line=finding_dict.get("line"),
                column=None,
                source="kb_antipatterns",
                fix_hint=None,
            ))
    except Exception as exc:
        log.warning("validate_kb_error: %s", exc)
    return findings


async def _run_method_availability_validator(
    kb_server: Any,
    code: str,
    target_context: str,
    platform_version: str,
) -> list[ValidationFinding]:
    """Валидатор 3: вызовы серверных методов на клиенте."""
    if kb_server is None:
        return []

    # Синхронная логика — в потоке, чтобы не блокировать event loop
    return await asyncio.to_thread(
        _check_methods_availability_sync,
        code=code,
        kb_server=kb_server,
        target_context=target_context,
        platform_version=platform_version,
    )


def _check_methods_availability_sync(
    code: str,
    kb_server: Any,
    target_context: str,
    platform_version: str,
) -> list[ValidationFinding]:
    """Синхронная реализация проверки method availability."""
    findings: list[ValidationFinding] = []
    seen_methods: set[str] = set()

    for match in _METHOD_CALL_RE.finditer(code):
        method_name = match.group(1)
        if method_name in _BSL_KEYWORDS:
            continue
        if method_name in seen_methods:
            continue
        seen_methods.add(method_name)

        line = code[: match.start()].count("\n") + 1

        try:
            result = kb_server.kb.check_method_availability(
                method_name=method_name,
                target_context=target_context,
                platform_version=platform_version,
            )
            if not result["available"]:
                findings.append(ValidationFinding(
                    severity="critical",
                    code=f"METHOD-CONTEXT-{method_name}",
                    message=result.get("reason") or (
                        f"Метод '{method_name}' недоступен в контексте '{target_context}'"
                    ),
                    line=line,
                    column=None,
                    source="kb_antipatterns",
                    fix_hint=(
                        f"Перенесите вызов '{method_name}' в серверный контекст "
                        "или используйте клиентский аналог"
                    ),
                ))
        except Exception as exc:
            log.warning("validate_method_availability_error: method=%s error=%s", method_name, str(exc)[:100])

    return findings
