"""validate node — детерминированный gate (parallel subgraph).

Sprint 3: bsl_ls.lint + kb.check_antipatterns (2 валидатора).
Sprint 3.1 (2026-07-12): + kb.check_method_availability (3-й валидатор).
  Парсит BSL-код на вызовы методов платформы, для каждого метода
  проверяет доступность в target_context. Critical finding если метод
  недоступен (например, серверный метод на клиенте).

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

import re
from typing import Any

from ..contracts import ValidateResult, ValidationFinding
from ..logging import get_logger
from ..state import FSMState, TaskState

log = get_logger(__name__)

# Regex для поиска вызовов методов в BSL: ИмяМетода(аргументы)
# Имя метода: кириллица/латиница/_, начинается с буквы
# Скобки: обязательны (это вызов, не определение)
_METHOD_CALL_RE = re.compile(
    r"\b([A-Za-zА-Яа-я_][A-Za-zА-Яа-я0-9_]*)\s*\(",
    re.MULTILINE,
)

# Ключевые слова BSL, которые не являются вызовами методов
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
    """Запустить валидаторы параллельно.

    Sprint 3.1 (2026-07-12): 3 валидатора:
      1. bsl_ls.lint — статический анализатор BSL LS (через HTTP)
      2. kb.check_antipatterns — regex-проверка на антипаттерны из YAML
      3. kb.check_method_availability — вызовы серверных методов на клиенте

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

    # Sprint 3.2.1: серверы должны передаваться через DI.
    # Создание серверов — ответственность agent/facade, не orchestrator.
    if bsl_ls_server is None:
        log.warning("validate_bsl_ls_not_provided", hint="Use build_graph(bsl_ls_server=...)")
    if kb_server is None:
        log.warning("validate_kb_not_provided", hint="Use build_graph(kb_server=...)")

    # Target context из subtask.constraints (default='server')
    target_context = "server"
    if subtask.constraints is not None:
        target_context = subtask.constraints.target_context

    # Запускаем валидаторы
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

    # Method availability (3-й валидатор)
    method_findings: list[ValidationFinding] = []
    if kb_server is not None:
        method_findings = _check_methods_availability(
            code=code,
            kb_server=kb_server,
            target_context=target_context,
            platform_version=state.platform_version,
        )

    # Объединяем findings
    findings = bsl_ls_findings + kb_findings + method_findings

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
        method_findings=len(method_findings),
    )

    return {
        "validate_result": validate_result.model_dump(mode="json"),
        "validation_passed": passed,
        "fsm_state": FSMState.REVIEWING,
    }


def _check_methods_availability(
    code: str,
    kb_server: Any,
    target_context: str,
    platform_version: str,
) -> list[ValidationFinding]:
    """Проверить вызовы методов платформы в коде на доступность в контексте.

    Парсит BSL-код на вызовы вида ИмяМетода(...) и для каждого уникального имени
    вызывает kb.check_method_availability. Если метод недоступен — finding.

    Args:
        code: BSL-код для проверки.
        kb_server: KbServer с подключённой KB.
        target_context: 'server' | 'thin_client' | 'mobile_client' | 'web_client'
            | 'external_connection'.
        platform_version: версия платформы 1С.

    Returns:
        Список ValidationFinding (severity=critical) для недоступных методов.
    """
    findings: list[ValidationFinding] = []
    seen_methods: set[str] = set()

    for match in _METHOD_CALL_RE.finditer(code):
        method_name = match.group(1)
        if method_name in _BSL_KEYWORDS:
            continue
        if method_name in seen_methods:
            continue
        seen_methods.add(method_name)

        # Линия вызова (для finding)
        line = code[: match.start()].count("\n") + 1

        try:
            result = kb_server.kb.check_method_availability(
                method_name=method_name,
                target_context=target_context,
                platform_version=platform_version,
            )
            if not result["available"]:
                findings.append(
                    ValidationFinding(
                        severity="critical",
                        code=f"METHOD-CONTEXT-{method_name}",
                        message=result.get("reason") or (
                            f"Метод '{method_name}' недоступен в контексте '{target_context}'"
                        ),
                        line=line,
                        column=None,
                        source="kb_antipatterns",  # переиспользуем источник KB
                        fix_hint=(
                            f"Перенесите вызов '{method_name}' в серверный контекст "
                            "или используйте клиентский аналог"
                        ),
                    )
                )
        except Exception as exc:
            log.warning(
                "validate_method_availability_error",
                method=method_name,
                error=str(exc)[:100],
            )

    return findings
