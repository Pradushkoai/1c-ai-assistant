"""Тесты для orchestrator.nodes.validate — 3 валидатора.

Sprint 3.1 (2026-07-12): проверка, что validate_node:
  1. Вызывает все 3 валидатора (bsl_ls, kb.check_antipatterns, kb.check_method_availability)
  2. Суммирует findings
  3. Помечает validation_passed=False при наличии critical findings
  4. Использует target_context из subtask.constraints

См. ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.state import (
    FSMState,
    Iteration,
    Subtask,
    SubtaskConstraints,
    TaskState,
)
from parsers.models import ObjectRef


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def kb_dir() -> Path:
    """Путь к реальной knowledge-base/ проекта."""
    return Path(__file__).parent.parent.parent / "knowledge-base"


@pytest.fixture
def make_state_with_iteration():
    """Фабрика для создания TaskState с одной итерацией.

    Args:
        code: BSL-код итерации.
        target_context: контекст выполнения ('server' | 'thin_client' | ...).
    """

    def _make(code: str, target_context: str = "server") -> TaskState:
        subtask = Subtask(
            id="st-001",
            name="TestSubtask",
            target_module=ObjectRef.from_string("CommonModule.Тест"),
            description="Test subtask",
            max_iterations=3,
            constraints=SubtaskConstraints(target_context=target_context),
        )
        iteration = Iteration(
            number=1,
            code=code,
            llm_response={},
            created_at=datetime.now(UTC),
        )
        return TaskState(
            task_id="task-test-001",
            description="Test task",
            config_name="mini",
            config_version="1.0",
            platform_version="8.3.20",
            subtasks=[subtask],
            current_subtask_idx=0,
            current_iteration=1,
            iterations=[iteration],
            fsm_state=FSMState.VALIDATING,
        )

    return _make


def _make_mock_bsl_ls(diagnostics: list[dict] | None = None):
    """Создать mock BslLsServer с заданными diagnostics."""
    from mcp_servers.bsl_ls.contracts import LintOutput

    server = MagicMock()
    lint_output = LintOutput(
        total=len(diagnostics or []),
        by_code={},
        diagnostics=diagnostics or [],
    )
    server.lint = AsyncMock(return_value=lint_output)
    return server


def _make_real_kb_server(kb_dir: Path):
    """Создать реальный KbServer с подключённой KB (без SQLite — только хардкод)."""
    from mcp_servers.kb import KbServer

    return KbServer(kb_dir=kb_dir)


# ─── Тесты: 3 валидатора ─────────────────────────────────────────────────────


class TestValidateNodeThreeValidators:
    """Проверка, что validate_node вызывает все 3 валидатора."""

    @pytest.mark.asyncio
    async def test_clean_code_passes(
        self, kb_dir: Path, make_state_with_iteration
    ):
        """Чистый код: нет BSL LS ошибок, нет антипаттернов, нет серверных методов на клиенте."""
        code = 'Функция Сложить(А, Б) Экспорт\n\tВозврат А + Б;\nКонецФункции'
        state = make_state_with_iteration(code, target_context="server")

        mock_bsl_ls = _make_mock_bsl_ls(diagnostics=[])
        kb_server = _make_real_kb_server(kb_dir)

        from orchestrator.nodes.validate import validate_node

        result = await validate_node(
            state=state,
            bsl_ls_server=mock_bsl_ls,
            kb_server=kb_server,
        )

        assert result["validation_passed"] is True
        assert result["fsm_state"] == FSMState.REVIEWING
        validate_result = result["validate_result"]
        assert validate_result["severity_breakdown"]["critical"] == 0

    @pytest.mark.asyncio
    async def test_bsl_ls_critical_makes_fail(
        self, kb_dir: Path, make_state_with_iteration
    ):
        """BSL LS critical → validation_passed=False."""
        code = 'Процедура Тест() КонецПроцедуры'  # пустое тело — BSL LS diagnostic
        state = make_state_with_iteration(code, target_context="server")

        mock_bsl_ls = _make_mock_bsl_ls(
            diagnostics=[
                {
                    "severity": "critical",
                    "code": "BSL-WS-001",
                    "message": "Empty procedure body",
                    "line": 1,
                    "column": 1,
                }
            ]
        )
        kb_server = _make_real_kb_server(kb_dir)

        from orchestrator.nodes.validate import validate_node

        result = await validate_node(
            state=state,
            bsl_ls_server=mock_bsl_ls,
            kb_server=kb_server,
        )

        assert result["validation_passed"] is False
        assert result["fsm_state"] == FSMState.REVIEWING
        validate_result = result["validate_result"]
        assert validate_result["severity_breakdown"]["critical"] == 1

    @pytest.mark.asyncio
    async def test_kb_antipattern_detected(
        self, kb_dir: Path, make_state_with_iteration
    ):
        """Антипаттерн 'select-star' → warning finding."""
        code = 'Запрос.Текст = "ВЫБРАТЬ * FROM Справочник.Товары";'
        state = make_state_with_iteration(code, target_context="server")

        mock_bsl_ls = _make_mock_bsl_ls(diagnostics=[])
        kb_server = _make_real_kb_server(kb_dir)

        from orchestrator.nodes.validate import validate_node

        result = await validate_node(
            state=state,
            bsl_ls_server=mock_bsl_ls,
            kb_server=kb_server,
        )

        validate_result = result["validate_result"]
        # select-star = warning → validation_passed всё ещё True (нет critical)
        assert result["validation_passed"] is True
        # Но warning-finding должен быть
        codes = [f["code"] for f in validate_result["findings"]]
        assert "select-star" in codes

    @pytest.mark.asyncio
    async def test_method_availability_violation_on_client(
        self, kb_dir: Path, make_state_with_iteration
    ):
        """Серверный метод (ЗаписьЖурналаРегистрации) на thin_client → critical finding.

        Использует хардкод-список из KBCollection (без SQLite).
        """
        code = (
            'Процедура Тест()\n'
            '\tЗаписьЖурналаРегистрации("Событие", "Сообщение");\n'
            'КонецПроцедуры'
        )
        state = make_state_with_iteration(code, target_context="thin_client")

        mock_bsl_ls = _make_mock_bsl_ls(diagnostics=[])
        kb_server = _make_real_kb_server(kb_dir)

        from orchestrator.nodes.validate import validate_node

        result = await validate_node(
            state=state,
            bsl_ls_server=mock_bsl_ls,
            kb_server=kb_server,
        )

        assert result["validation_passed"] is False
        validate_result = result["validate_result"]
        assert validate_result["severity_breakdown"]["critical"] >= 1

        # Finding должен содержать имя метода
        codes = [f["code"] for f in validate_result["findings"]]
        method_findings = [c for c in codes if c.startswith("METHOD-CONTEXT-")]
        assert len(method_findings) >= 1
        assert "METHOD-CONTEXT-ЗаписьЖурналаРегистрации" in codes

    @pytest.mark.asyncio
    async def test_method_availability_ok_on_server(
        self, kb_dir: Path, make_state_with_iteration
    ):
        """Серверный метод на server → НЕТ finding (метод доступен)."""
        code = (
            'Процедура Тест()\n'
            '\tЗаписьЖурналаРегистрации("Событие", "Сообщение");\n'
            'КонецПроцедуры'
        )
        state = make_state_with_iteration(code, target_context="server")

        mock_bsl_ls = _make_mock_bsl_ls(diagnostics=[])
        kb_server = _make_real_kb_server(kb_dir)

        from orchestrator.nodes.validate import validate_node

        result = await validate_node(
            state=state,
            bsl_ls_server=mock_bsl_ls,
            kb_server=kb_server,
        )

        # На сервере метод доступен — не должно быть METHOD-CONTEXT-* findings
        validate_result = result["validate_result"]
        codes = [f["code"] for f in validate_result["findings"]]
        method_findings = [c for c in codes if c.startswith("METHOD-CONTEXT-")]
        assert len(method_findings) == 0

    @pytest.mark.asyncio
    async def test_three_validators_findings_summed(
        self, kb_dir: Path, make_state_with_iteration
    ):
        """Все 3 валидатора срабатывают одновременно — findings суммируются.

        Код содержит:
        - BSL LS critical (mocked)
        - KB antipattern: select-star (warning)
        - Method availability violation: ЗаписьЖурналаРегистрации на thin_client (critical)
        """
        code = (
            'Процедура Тест()\n'
            '\tЗапрос.Текст = "ВЫБРАТЬ * FROM Справочник.Товары";\n'
            '\tЗаписьЖурналаРегистрации("Событие");\n'
            'КонецПроцедуры'
        )
        state = make_state_with_iteration(code, target_context="thin_client")

        mock_bsl_ls = _make_mock_bsl_ls(
            diagnostics=[
                {
                    "severity": "critical",
                    "code": "BSL-WS-001",
                    "message": "Some critical issue",
                    "line": 1,
                    "column": 1,
                }
            ]
        )
        kb_server = _make_real_kb_server(kb_dir)

        from orchestrator.nodes.validate import validate_node

        result = await validate_node(
            state=state,
            bsl_ls_server=mock_bsl_ls,
            kb_server=kb_server,
        )

        assert result["validation_passed"] is False
        validate_result = result["validate_result"]
        findings = validate_result["findings"]

        # Должны быть findings от всех 3 валидаторов
        sources = {f["source"] for f in findings}
        assert "bsl_ls" in sources
        assert "kb_antipatterns" in sources  # оба: antipatterns и method-availability

        # Хотя бы 2 critical (BSL LS + method availability)
        assert validate_result["severity_breakdown"]["critical"] >= 2
        # Хотя бы 1 warning (select-star)
        assert validate_result["severity_breakdown"]["warning"] >= 1

    @pytest.mark.asyncio
    async def test_target_context_from_constraints(
        self, kb_dir: Path, make_state_with_iteration
    ):
        """target_context берётся из subtask.constraints (default='server')."""
        # Код с серверным методом — на thin_client это violation, на server — нет
        code = 'Процедура Тест()\n\tЗаписьЖурналаРегистрации("Событие");\nКонецПроцедуры'

        # thin_client → violation
        state_client = make_state_with_iteration(code, target_context="thin_client")
        mock_bsl_ls = _make_mock_bsl_ls(diagnostics=[])
        kb_server = _make_real_kb_server(kb_dir)

        from orchestrator.nodes.validate import validate_node

        result_client = await validate_node(
            state=state_client,
            bsl_ls_server=mock_bsl_ls,
            kb_server=kb_server,
        )
        assert result_client["validation_passed"] is False

        # server → OK
        state_server = make_state_with_iteration(code, target_context="server")
        result_server = await validate_node(
            state=state_server,
            bsl_ls_server=mock_bsl_ls,
            kb_server=kb_server,
        )
        assert result_server["validation_passed"] is True

    @pytest.mark.asyncio
    async def test_failed_checks_contains_only_critical_and_warning(
        self, kb_dir: Path, make_state_with_iteration
    ):
        """failed_checks содержит только critical+warning (не info)."""
        code = 'Запрос.Текст = "ВЫБРАТЬ * FROM Справочник.Товары";'
        state = make_state_with_iteration(code, target_context="server")

        # BSL LS info diagnostic — не должен попасть в failed_checks
        mock_bsl_ls = _make_mock_bsl_ls(
            diagnostics=[
                {
                    "severity": "info",
                    "code": "BSL-INFO-001",
                    "message": "Info message",
                    "line": 1,
                    "column": 1,
                }
            ]
        )
        kb_server = _make_real_kb_server(kb_dir)

        from orchestrator.nodes.validate import validate_node

        result = await validate_node(
            state=state,
            bsl_ls_server=mock_bsl_ls,
            kb_server=kb_server,
        )

        validate_result = result["validate_result"]
        for check in validate_result["failed_checks"]:
            assert check["severity"] in ("critical", "warning")


# ─── Тесты: обработка ошибок ─────────────────────────────────────────────────


class TestValidateNodeErrorHandling:
    """Проверка, что validate_node не падает при ошибках валидаторов."""

    @pytest.mark.asyncio
    async def test_bsl_ls_error_does_not_crash(
        self, kb_dir: Path, make_state_with_iteration
    ):
        """Если BSL LS падает — validate_node продолжает (без BSL LS findings)."""
        code = 'Процедура Тест() КонецПроцедуры'
        state = make_state_with_iteration(code, target_context="server")

        mock_bsl_ls = MagicMock()
        mock_bsl_ls.lint = AsyncMock(side_effect=Exception("BSL LS unavailable"))

        kb_server = _make_real_kb_server(kb_dir)

        from orchestrator.nodes.validate import validate_node

        result = await validate_node(
            state=state,
            bsl_ls_server=mock_bsl_ls,
            kb_server=kb_server,
        )

        # Не упало — прошла валидация (без BSL LS findings)
        assert result["validation_passed"] is True
        assert result["fsm_state"] == FSMState.REVIEWING

    @pytest.mark.asyncio
    async def test_kb_server_none_does_not_crash(
        self, make_state_with_iteration
    ):
        """Если kb_server=None — validate_node использует только BSL LS."""
        code = 'Процедура Тест() КонецПроцедуры'
        state = make_state_with_iteration(code, target_context="server")

        mock_bsl_ls = _make_mock_bsl_ls(diagnostics=[])

        from orchestrator.nodes.validate import validate_node

        result = await validate_node(
            state=state,
            bsl_ls_server=mock_bsl_ls,
            kb_server=None,
        )

        # Не упало — нет findings
        validate_result = result["validate_result"]
        assert len(validate_result["findings"]) == 0


# ─── Тесты: _check_methods_availability helper ────────────────────────────────


class TestCheckMethodsAvailabilityHelper:
    """Прямые тесты _check_methods_availability."""

    @pytest.mark.asyncio
    async def test_multiple_server_methods_on_client(
        self, kb_dir: Path
    ):
        """Несколько разных серверных методов на клиенте → несколько findings.

        Используем только реальные вызовы функций (со скобками).
        Метаданные/Константы — это свойства (через точку), они не парсятся
        regex'ом как вызовы (нужен AST-анализ, запланирован на Sprint 4).
        """
        from orchestrator.nodes.validate import _check_methods_availability

        kb_server = _make_real_kb_server(kb_dir)
        code = (
            'Процедура Тест()\n'
            '\tЗаписьЖурналаРегистрации("Событие");\n'
            '\tНайтиПоСсылкам(Ссылка);\n'
            '\tЗаблокировать(Объект);\n'
            'КонецПроцедуры'
        )

        findings = _check_methods_availability(
            code=code,
            kb_server=kb_server,
            target_context="thin_client",
            platform_version="8.3.20",
        )

        # Все 3 метода — server-only (в хардкод-списке) и вызываются со скобками
        codes = [f.code for f in findings]
        assert "METHOD-CONTEXT-ЗаписьЖурналаРегистрации" in codes
        assert "METHOD-CONTEXT-НайтиПоСсылкам" in codes
        assert "METHOD-CONTEXT-Заблокировать" in codes
        # Все critical
        for f in findings:
            assert f.severity == "critical"

    @pytest.mark.asyncio
    async def test_duplicate_method_one_finding(
        self, kb_dir: Path
    ):
        """Повторный вызов того же метода — только 1 finding (по первому вызову)."""
        from orchestrator.nodes.validate import _check_methods_availability

        kb_server = _make_real_kb_server(kb_dir)
        code = (
            'Процедура Тест()\n'
            '\tЗаписьЖурналаРегистрации("1");\n'
            '\tЗаписьЖурналаРегистрации("2");\n'
            '\tЗаписьЖурналаРегистрации("3");\n'
            'КонецПроцедуры'
        )

        findings = _check_methods_availability(
            code=code,
            kb_server=kb_server,
            target_context="thin_client",
            platform_version="8.3.20",
        )

        # Только 1 finding (dedup по имени метода)
        method_findings = [f for f in findings if "ЗаписьЖурналаРегистрации" in f.code]
        assert len(method_findings) == 1

    @pytest.mark.asyncio
    async def test_keywords_not_treated_as_methods(
        self, kb_dir: Path
    ):
        """Ключевые слова BSL (Если, Для, ...) не проверяются как методы."""
        from orchestrator.nodes.validate import _check_methods_availability

        kb_server = _make_real_kb_server(kb_dir)
        code = (
            'Процедура Тест()\n'
            '\tДля Каждого Стр Из Товары Цикл\n'
            '\t\tЕсли Стр.Сумма > 0 Тогда\n'
            '\t\t\tСообщить("OK");\n'
            '\t\tКонецЕсли;\n'
            '\tКонецЦикла;\n'
            'КонецПроцедуры'
        )

        findings = _check_methods_availability(
            code=code,
            kb_server=kb_server,
            target_context="thin_client",
            platform_version="8.3.20",
        )

        # Ни один keyword не должен попасть в findings как METHOD-CONTEXT
        codes = [f.code for f in findings]
        for kw in ("Для", "Цикл", "Если", "Тогда", "КонецЕсли", "КонецЦикла",
                   "Процедура", "КонецПроцедуры", "Сообщить"):
            assert f"METHOD-CONTEXT-{kw}" not in codes, (
                f"Ключевое слово '{kw}' не должно проверяться как метод"
            )
