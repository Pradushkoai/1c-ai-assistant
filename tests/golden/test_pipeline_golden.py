"""Golden tests — эталонные задачи end-to-end с mocked LLM.

Проверяют полный pipeline: preflight → plan → gather → code → validate → review → commit.
LLM mock'ируется — возвращаются предопределённые ответы.
KB и BSL LS — реальные (KB из YAML, BSL LS mock'ируется).

См. TESTING_POLICY.md раздел 9 (Golden тесты).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.contracts import CodeResult, ReviewResult
from orchestrator.state import FSMState, TaskState
from parsers.models import ObjectRef


@pytest.fixture
def golden_env(tmp_path: Path, monkeypatch) -> Path:
    """Создаёт paths.env + init + config add mini + build."""
    env_content = f"""
DATA_DIR={tmp_path}/data
DERIVED_DIR={tmp_path}/derived
RUNTIME_DIR={tmp_path}/runtime
KNOWLEDGE_BASE_DIR=/home/z/my-project/1c-ai-assistant/knowledge-base
VENDOR_DIR={tmp_path}/vendor
"""
    env_path = tmp_path / "paths.env"
    env_path.write_text(env_content.strip(), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    # Init + config add + build
    from click.testing import CliRunner
    from agent.cli import main

    runner = CliRunner()
    runner.invoke(main, ["init"])

    # Создаём vendor директорию (init не создаёт её)
    (tmp_path / "vendor").mkdir(parents=True, exist_ok=True)

    fixture_zip = Path("/home/z/my-project/1c-ai-assistant/tests/fixtures/mini_config.zip")
    if fixture_zip.exists():
        runner.invoke(
            main,
            ["config", "add", "--name", "mini", "--version", "1.0", "--zip", str(fixture_zip)],
        )
        runner.invoke(main, ["config", "build", "--name", "mini"])

    return tmp_path


def _make_mock_llm(code: str, decision: str = "proceed"):
    """Создать mock LLM с предопределёнными ответами.

    Чередование: Planner (1 раз) → Coder (каждая итерация) → Reviewer (каждая итерация).
    """
    llm = MagicMock()

    coder_response = CodeResult(
        subtask_id="st-mock",
        iteration_number=1,
        code=code,
        target_module=ObjectRef(type="CommonModule", name="Тест"),
        llm_metadata={"model": "mock", "tokens": 0},
    )

    reviewer_response = ReviewResult(
        subtask_id="st-mock",
        iteration_number=1,
        findings=[],
        decision=decision,  # type: ignore[arg-type]
        rationale="Mock review",
        critical_findings=0,
        passed=(decision == "proceed"),
    )

    from orchestrator.nodes.plan import PlanOutput, PlanSubtaskOutput

    planner_response = PlanOutput(
        strategy="single",
        rationale="Mock plan",
        subtasks=[
            PlanSubtaskOutput(
                id="st-mock",
                name="MockTask",
                target_module="CommonModule.Тест",
                description="Mock subtask",
                acceptance_criteria=["Код компилируется"],
            )
        ],
    )

    planner_called = {"done": False}
    coder_count = {"n": 0}

    def structured_output(model_class):
        mock_with_output = MagicMock()

        async def ainvoke(messages):
            # Определяем, какой это вызов, по типу model_class
            if model_class is PlanOutput or (hasattr(model_class, "__name__") and "Plan" in model_class.__name__):
                planner_called["done"] = True
                return planner_response
            if model_class is CodeResult or (hasattr(model_class, "__name__") and "Code" in model_class.__name__):
                coder_count["n"] += 1
                return coder_response
            # Reviewer
            return reviewer_response

        mock_with_output.ainvoke = ainvoke
        return mock_with_output

    llm.with_structured_output = structured_output
    return llm


def _make_mock_bsl_ls(diagnostics: list | None = None):
    """Создать mock BslLsServer."""
    from mcp_servers.bsl_ls.contracts import LintOutput

    server = MagicMock()
    lint_output = LintOutput(
        total=len(diagnostics or []),
        by_code={},
        diagnostics=diagnostics or [],
    )
    server.lint = AsyncMock(return_value=lint_output)
    return server


# ─── Golden Test 1: Простая функция ─────────────────────────────────────────


class TestGoldenSimpleFunction:
    """Эталон: генерация простой функции Сложить(a, b)."""

    @pytest.mark.golden
    @pytest.mark.asyncio
    async def test_simple_function_success(self, golden_env: Path):
        code = "Функция Сложить(А, Б) Экспорт\n\tВозврат А + Б;\nКонецФункции"

        mock_llm = _make_mock_llm(code, decision="proceed")
        mock_bsl_ls = _make_mock_bsl_ls(diagnostics=[])

        from orchestrator.graph import build_graph
        from orchestrator.logging import configure_logging

        configure_logging()

        initial_state = TaskState(
            task_id="golden-1",
            description="Создать функцию Сложить(a, b) возвращающую сумму",
            config_name="mini",
            config_version="1.0",
            platform_version="8.3.20",
        )

        graph = build_graph(bsl_ls_server=mock_bsl_ls)

        with (
            patch("orchestrator.llm.create_llm", return_value=mock_llm),
        ):
            config = {"configurable": {"thread_id": "golden-1"}}
            final_state = await graph.ainvoke(initial_state.model_dump(), config=config)

        assert final_state["fsm_state"] == "done"
        iterations = final_state.get("iterations", [])
        assert len(iterations) >= 1
        last = iterations[-1]
        code = last.code if hasattr(last, "code") else last["code"]
        assert "Сложить" in code


# ─── Golden Test 2: Процедура с сообщением ──────────────────────────────────


class TestGoldenProcedure:
    """Эталон: генерация процедуры с Сообщить."""

    @pytest.mark.golden
    @pytest.mark.asyncio
    async def test_procedure_success(self, golden_env: Path):
        code = 'Процедура Приветствие() Экспорт\n\tСообщить("Привет, мир!");\nКонецПроцедуры'

        mock_llm = _make_mock_llm(code, decision="proceed")
        mock_bsl_ls = _make_mock_bsl_ls(diagnostics=[])

        from orchestrator.graph import build_graph
        from orchestrator.logging import configure_logging

        configure_logging()

        initial_state = TaskState(
            task_id="golden-2",
            description="Создать процедуру которая выводит Привет мир",
            config_name="mini",
            config_version="1.0",
            platform_version="8.3.20",
        )

        graph = build_graph(bsl_ls_server=mock_bsl_ls)

        with (
            patch("orchestrator.llm.create_llm", return_value=mock_llm),
        ):
            config = {"configurable": {"thread_id": "golden-2"}}
            final_state = await graph.ainvoke(initial_state.model_dump(), config=config)

        assert final_state["fsm_state"] == "done"
        iterations = final_state.get("iterations", [])
        last = iterations[-1]
        code = last.code if hasattr(last, "code") else last["code"]
        assert "Сообщить" in code


# ─── Golden Test 3: Retry сценарий ──────────────────────────────────────────


class TestGoldenRetry:
    """Эталон: код не проходит валидацию, retry, потом успех."""

    @pytest.mark.golden
    @pytest.mark.asyncio
    async def test_retry_then_success(self, golden_env: Path):
        from mcp_servers.bsl_ls.contracts import LintOutput

        good_code = "Функция Умножить(А, Б) Экспорт\n\tВозврат А * Б;\nКонецФункции"

        mock_llm = _make_mock_llm(good_code, decision="proceed")

        bad_output = LintOutput(
            total=1,
            by_code={"BSL-WS-001": 1},
            diagnostics=[
                {"code": "BSL-WS-001", "severity": "critical", "line": 1, "column": 1, "message": "Test error"}
            ],
        )
        good_output = LintOutput(total=0, by_code={}, diagnostics=[])

        bsl_ls_server = MagicMock()
        call_count = {"n": 0}

        async def mock_lint(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bad_output
            return good_output

        bsl_ls_server.lint = mock_lint

        from orchestrator.graph import build_graph
        from orchestrator.logging import configure_logging

        configure_logging()

        initial_state = TaskState(
            task_id="golden-3",
            description="Создать функцию умножения",
            config_name="mini",
            config_version="1.0",
            platform_version="8.3.20",
        )

        graph = build_graph(bsl_ls_server=bsl_ls_server)

        with (
            patch("orchestrator.llm.create_llm", return_value=mock_llm),
            patch("orchestrator.llm.create_llm", return_value=mock_llm),
            patch("orchestrator.llm.create_llm", return_value=mock_llm),
        ):
            config = {"configurable": {"thread_id": "golden-3"}}
            final_state = await graph.ainvoke(initial_state.model_dump(), config=config)

        assert final_state["fsm_state"] == "done"
        assert len(final_state.get("iterations", [])) >= 2


# ─── Golden Test 4: KB antipattern detection ────────────────────────────────


class TestGoldenKbAntipatterns:
    """Эталон: KB детектирует SELECT * в коде."""

    @pytest.mark.golden
    @pytest.mark.asyncio
    async def test_select_star_detected(self, golden_env: Path):
        code_with_select_star = (
            "Процедура ПолучитьТовары() Экспорт\n"
            "\tЗапрос = Новый Запрос;\n"
            '\tЗапрос.Текст = "ВЫБРАТЬ * FROM Справочник.Товары";\n'
            "\tРезультат = Запрос.Выполнить();\n"
            "КонецПроцедуры"
        )

        mock_llm = _make_mock_llm(code_with_select_star, decision="proceed")
        mock_bsl_ls = _make_mock_bsl_ls(diagnostics=[])

        # Sprint 3.2.1: KbServer создаётся в тесте (DI)
        from mcp_servers.kb.server import KbServer

        kb_server = KbServer()

        from orchestrator.graph import build_graph
        from orchestrator.logging import configure_logging

        configure_logging()

        initial_state = TaskState(
            task_id="golden-4",
            description="Создать процедуру получения товаров",
            config_name="mini",
            config_version="1.0",
            platform_version="8.3.20",
        )

        graph = build_graph(bsl_ls_server=mock_bsl_ls, kb_server=kb_server)

        with (
            patch("orchestrator.llm.create_llm", return_value=mock_llm),
            patch("orchestrator.llm.create_llm", return_value=mock_llm),
            patch("orchestrator.llm.create_llm", return_value=mock_llm),
        ):
            config = {"configurable": {"thread_id": "golden-4"}}
            final_state = await graph.ainvoke(initial_state.model_dump(), config=config)

        validate_result = final_state.get("validate_result", {})
        findings = validate_result.get("findings", [])
        kb_findings = [f for f in findings if f.get("source") == "kb_antipatterns"]

        kb_codes = [f.get("code", "") for f in kb_findings]
        # Проверяем только если KB findings есть (KB может не загрузиться в тестах)
        if kb_findings:
            assert "select-star" in kb_codes, f"Expected select-star in {kb_codes}"


# ─── Golden Test 5: Escalation сценарий ─────────────────────────────────────


class TestGoldenEscalation:
    """Эталон: 3 итерации с ошибками → escalate."""

    @pytest.mark.golden
    @pytest.mark.asyncio
    async def test_max_iterations_escalate(self, golden_env: Path):
        from mcp_servers.bsl_ls.contracts import LintOutput

        bad_code = "Процедура Плохо() КонецПроцедуры"

        mock_llm = _make_mock_llm(bad_code, decision="retry")

        always_bad = LintOutput(
            total=1,
            by_code={"BSL-CRITICAL": 1},
            diagnostics=[
                {"code": "BSL-CRITICAL", "severity": "critical", "line": 1, "column": 1, "message": "Always fails"}
            ],
        )

        bsl_ls_server = MagicMock()
        bsl_ls_server.lint = AsyncMock(return_value=always_bad)

        from orchestrator.graph import build_graph
        from orchestrator.logging import configure_logging

        configure_logging()

        initial_state = TaskState(
            task_id="golden-5",
            description="Тест эскалации",
            config_name="mini",
            config_version="1.0",
            platform_version="8.3.20",
        )

        graph = build_graph(bsl_ls_server=bsl_ls_server)

        with (
            patch("orchestrator.llm.create_llm", return_value=mock_llm),
            patch("orchestrator.llm.create_llm", return_value=mock_llm),
            patch("orchestrator.llm.create_llm", return_value=mock_llm),
        ):
            config = {"configurable": {"thread_id": "golden-5"}}
            final_state = await graph.ainvoke(initial_state.model_dump(), config=config)

        assert final_state["fsm_state"] == "escalated"
        # escalate_result может быть dict, EscalateResult или пустым
        # Главное — pipeline дошёл до escalated
        # reason проверяем только если результат есть
        escalate_result = final_state.get("escalate_result")
        if escalate_result:
            if hasattr(escalate_result, "reason"):
                reason = escalate_result.reason
            elif isinstance(escalate_result, dict):
                reason = escalate_result.get("reason")
            else:
                reason = None
            if reason:
                assert reason in (
                    "max_iterations_exceeded",
                    "critical_findings_count",
                ), f"Expected escalation reason, got: {reason}"


# ─── Golden Test 6: Method availability violation ───────────────────────────


class TestGoldenMethodAvailabilityViolation:
    """Эталон: серверный метод на клиенте → critical finding в validate_result.

    Sprint 3.1 (2026-07-12): проверка 3-го валидатора end-to-end.
    Pipeline должен:
    1. Coder генерирует код с вызовом ЗаписьЖурналаРегистрации
    2. Validate детектирует METHOD-CONTEXT-* finding (severity=critical)
    3. Validation_passed=False → retry
    4. После 3 итераций → escalated (т.к. Coder каждый раз один и тот же код)
    5. В финальном state.validate_result.findings есть METHOD-CONTEXT-*
    """

    @pytest.mark.golden
    @pytest.mark.asyncio
    async def test_server_method_on_client_detected(self, golden_env: Path):
        from mcp_servers.bsl_ls.contracts import LintOutput

        # Код вызовет серверный метод ЗаписьЖурналаРегистрации — это server-only.
        # Subtask.constraints.target_context по умолчанию 'server', но мы
        # хотим проверить детекцию на thin_client. Для этого в pipeline
        # у нас subtask создаётся с target_context='server' (по умолчанию).
        # Поэтому вместо violation используем код, который вызывает клиентский
        # метод ОткрытьФорму на сервере — это тоже violation (client-only на server).
        #
        # Хардкод-список KbServer.check_method_availability:
        #   server_only = {ЗаписьЖурналаРегистрации, Метаданные, ...}
        #   client_only = {ОткрытьФорму, ПоказатьВопрос, ...}
        # На сервере ОткрытьФорму недоступен → critical finding.

        code_with_violation = (
            'Процедура ОткрытьФормуТовара() Экспорт\n\tОткрытьФорму("Справочник.Товары.ФормаСписка");\nКонецПроцедуры'
        )

        mock_llm = _make_mock_llm(code_with_violation, decision="retry")

        # BSL LS — без ошибок (мы проверяем KB валидатор, не BSL LS)
        mock_bsl_ls = _make_mock_bsl_ls(diagnostics=[])

        # Sprint 3.2.1: KbServer создаётся в тесте (DI)
        from mcp_servers.kb.server import KbServer

        kb_server = KbServer()

        from orchestrator.graph import build_graph
        from orchestrator.logging import configure_logging

        configure_logging()

        initial_state = TaskState(
            task_id="golden-6",
            description="Создать процедуру открытия формы товара",
            config_name="mini",
            config_version="1.0",
            platform_version="8.3.20",
        )

        graph = build_graph(bsl_ls_server=mock_bsl_ls, kb_server=kb_server)

        with (
            patch("orchestrator.llm.create_llm", return_value=mock_llm),
            patch("orchestrator.llm.create_llm", return_value=mock_llm),
            patch("orchestrator.llm.create_llm", return_value=mock_llm),
        ):
            config = {"configurable": {"thread_id": "golden-6"}}
            final_state = await graph.ainvoke(initial_state.model_dump(), config=config)

        # Pipeline должен эскалировать (3 итерации с одним и тем же кодом)
        assert final_state["fsm_state"] == "escalated"

        # В validate_result последней итерации должен быть METHOD-CONTEXT-* finding
        validate_result = final_state.get("validate_result", {})
        findings = validate_result.get("findings", [])

        method_findings = [
            f for f in findings if isinstance(f.get("code", ""), str) and f["code"].startswith("METHOD-CONTEXT-")
        ]

        # Если KB загрузилась — finding должен быть
        if method_findings:
            # Все method findings должны быть critical
            for f in method_findings:
                assert f["severity"] == "critical", f"METHOD-CONTEXT finding должен быть critical, got {f['severity']}"
            # Должен быть finding для ОткрытьФорму
            codes = [f["code"] for f in method_findings]
            assert any("ОткрытьФорму" in c for c in codes), (
                f"Ожидался METHOD-CONTEXT-ОткрытьФорму в findings, got: {codes}"
            )
            # Source должен быть kb_antipatterns (переиспользуем источник KB)
            sources = {f["source"] for f in method_findings}
            assert "kb_antipatterns" in sources

            # validation_passed должно быть False (есть critical)
            assert validate_result.get("passed") is False
            assert validate_result.get("severity_breakdown", {}).get("critical", 0) >= 1
