"""Тесты для orchestrator.nodes.review — LLM findings прокидываются в state.

Sprint 3.1 (2026-07-12): проверка баг-фикса — ранее findings=[] терял все
LLM-замечания. Теперь response.findings прокидываются в ReviewResult.findings.

См. ADR-0009 (Pipeline contracts) и docs/architecture/10-prompts-spec.md.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.contracts import ReviewFinding, ReviewResult
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
def make_review_state():
    """Фабрика для создания TaskState в REVIEWING-состоянии с одной итерацией."""

    def _make(
        code: str = "Процедура Тест() КонецПроцедуры",
        validation_passed: bool = True,
        target_context: str = "server",
    ) -> TaskState:
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
            task_id="task-review-test-001",
            description="Test task",
            config_name="mini",
            config_version="1.0",
            platform_version="8.3.20",
            subtasks=[subtask],
            current_subtask_idx=0,
            current_iteration=1,
            iterations=[iteration],
            fsm_state=FSMState.REVIEWING,
            validation_passed=validation_passed,
        )

    return _make


def _make_mock_llm_with_findings(
    findings: list[ReviewFinding],
    decision: str = "proceed",
    rationale: str = "Mock review rationale",
    critical_findings: int = 0,
    passed: bool = True,
):
    """Создать mock LLM с заданными findings в ответе Reviewer'а.

    Args:
        findings: список ReviewFinding, которые LLM вернёт.
        decision: 'proceed' | 'retry' | 'escalate'.
        rationale: объяснение решения.
        critical_findings: количество critical findings (для рутера).
        passed: True = decision == 'proceed'.
    """
    response = ReviewResult(
        subtask_id="st-001",
        iteration_number=1,
        findings=findings,
        decision=decision,  # type: ignore[arg-type]
        rationale=rationale,
        critical_findings=critical_findings,
        passed=passed,
    )

    llm = MagicMock()
    mock_with_output = MagicMock()

    async def ainvoke(messages):
        return response

    mock_with_output.ainvoke = ainvoke
    llm.with_structured_output = MagicMock(return_value=mock_with_output)
    return llm


# ─── Тесты: LLM findings прокидываются в ReviewResult ────────────────────────


class TestReviewNodeFindingsPropagation:
    """Sprint 3.1 (2026-07-12): проверка баг-фикса.

    Раньше findings=[] терял все LLM-замечания. Теперь response.findings
    прокидываются в ReviewResult.findings и сохраняются в state.
    """

    @pytest.mark.asyncio
    async def test_llm_findings_propagated_to_state(self, make_review_state):
        """LLM возвращает 2 findings — они должны оказаться в state.review_result."""
        findings = [
            ReviewFinding(
                severity="warning",
                category="antipattern",
                code="QUERY-IN-LOOP",
                message="Запрос в цикле",
                recommendation="Вынести запрос за цикл",
            ),
            ReviewFinding(
                severity="info",
                category="style",
                code="STYLE-001",
                message="Слишком длинная функция",
                recommendation="Разбить на подфункции",
            ),
        ]
        mock_llm = _make_mock_llm_with_findings(findings, decision="proceed")

        state = make_review_state()

        from orchestrator.nodes.review import review_node

        result = await review_node(state=state, llm=mock_llm, kb_server=None)

        # review_result должен содержать 2 findings
        review_result = result["review_result"]
        assert len(review_result["findings"]) == 2
        assert review_result["findings"][0]["code"] == "QUERY-IN-LOOP"
        assert review_result["findings"][1]["code"] == "STYLE-001"

        # review_passed=True (decision=proceed)
        assert result["review_passed"] is True
        assert result["fsm_state"] == FSMState.COMMITTING

    @pytest.mark.asyncio
    async def test_llm_findings_empty_when_no_findings(self, make_review_state):
        """LLM возвращает 0 findings — findings пустой, но не None."""
        mock_llm = _make_mock_llm_with_findings([], decision="proceed")

        state = make_review_state()

        from orchestrator.nodes.review import review_node

        result = await review_node(state=state, llm=mock_llm, kb_server=None)

        review_result = result["review_result"]
        assert review_result["findings"] == []
        assert len(review_result["findings"]) == 0

    @pytest.mark.asyncio
    async def test_llm_findings_with_critical_retry(self, make_review_state):
        """LLM с critical finding → decision=retry → review_passed=False."""
        findings = [
            ReviewFinding(
                severity="critical",
                category="context_violation",
                code="METHOD-CONTEXT-ЗаписьЖурналаРегистрации",
                message="Серверный метод на клиенте",
                recommendation="Перенести в серверный контекст",
            ),
        ]
        mock_llm = _make_mock_llm_with_findings(
            findings,
            decision="retry",
            critical_findings=1,
            passed=False,
        )

        state = make_review_state()

        from orchestrator.nodes.review import review_node

        result = await review_node(state=state, llm=mock_llm, kb_server=None)

        review_result = result["review_result"]
        assert len(review_result["findings"]) == 1
        assert review_result["findings"][0]["severity"] == "critical"
        assert review_result["findings"][0]["code"] == "METHOD-CONTEXT-ЗаписьЖурналаРегистрации"

        # review_passed=False →_fsm_state = CODING (retry)
        assert result["review_passed"] is False
        assert result["fsm_state"] == FSMState.CODING

    @pytest.mark.asyncio
    async def test_llm_findings_with_multiple_categories(self, make_review_state):
        """LLM возвращает findings разных категорий — все прокидываются."""
        findings = [
            ReviewFinding(
                severity="critical",
                category="antipattern",
                code="AP-001",
                message="Антипаттерн",
                recommendation="Исправить",
            ),
            ReviewFinding(
                severity="warning",
                category="context_violation",
                code="CV-001",
                message="Нарушение контекста",
                recommendation="Проверить контекст",
            ),
            ReviewFinding(
                severity="info",
                category="pattern_mismatch",
                code="PM-001",
                message="Не соответствует паттерну",
                recommendation="Применить паттерн",
            ),
            ReviewFinding(
                severity="warning",
                category="style",
                code="ST-001",
                message="Стиль",
                recommendation="Поправить стиль",
            ),
        ]
        mock_llm = _make_mock_llm_with_findings(findings, decision="proceed")

        state = make_review_state()

        from orchestrator.nodes.review import review_node

        result = await review_node(state=state, llm=mock_llm, kb_server=None)

        review_result = result["review_result"]
        assert len(review_result["findings"]) == 4
        categories = {f["category"] for f in review_result["findings"]}
        assert categories == {"antipattern", "context_violation", "pattern_mismatch", "style"}


# ─── Тесты: fallback когда LLM недоступен ──────────────────────────────────────


class TestReviewNodeFallback:
    """Проверка fallback-логики когда LLM падает."""

    @pytest.mark.asyncio
    async def test_llm_unavailable_validation_passed_auto_proceed(self, make_review_state):
        """LLM падает, но validation_passed=True → auto-proceed с пустыми findings."""
        # Mock LLM, который бросает исключение
        llm = MagicMock()
        mock_with_output = MagicMock()

        async def ainvoke(messages):
            raise Exception("LLM unavailable")

        mock_with_output.ainvoke = ainvoke
        llm.with_structured_output = MagicMock(return_value=mock_with_output)

        state = make_review_state(validation_passed=True)

        from orchestrator.nodes.review import review_node

        result = await review_node(state=state, llm=llm, kb_server=None)

        # Auto-proceed
        assert result["review_passed"] is True
        assert result["fsm_state"] == FSMState.COMMITTING
        # findings пустые (LLM недоступен)
        review_result = result["review_result"]
        assert review_result["findings"] == []

    @pytest.mark.asyncio
    async def test_llm_unavailable_validation_failed_auto_retry(self, make_review_state):
        """LLM падает и validation_passed=False → auto-retry с пустыми findings."""
        llm = MagicMock()
        mock_with_output = MagicMock()

        async def ainvite(messages):
            raise Exception("LLM unavailable")

        mock_with_output.ainvoke = ainvite
        llm.with_structured_output = MagicMock(return_value=mock_with_output)

        state = make_review_state(validation_passed=False)

        from orchestrator.nodes.review import review_node

        result = await review_node(state=state, llm=llm, kb_server=None)

        # Auto-retry
        assert result["review_passed"] is False
        assert result["fsm_state"] == FSMState.CODING
        # findings пустые, critical_findings=1 (для роутера — чтобы не зацикливалось)
        review_result = result["review_result"]
        assert review_result["findings"] == []
        assert result["critical_findings"] == 1


# ─── Тесты: рутер-сигналы ────────────────────────────────────────────────────


class TestReviewNodeRouterSignals:
    """Проверка, что review_node корректно выставляет рутер-сигналы."""

    @pytest.mark.asyncio
    async def test_proceed_sets_committing_state(self, make_review_state):
        """decision=proceed → fsm_state=COMMITTING."""
        mock_llm = _make_mock_llm_with_findings([], decision="proceed", passed=True)
        state = make_review_state()

        from orchestrator.nodes.review import review_node

        result = await review_node(state=state, llm=mock_llm, kb_server=None)
        assert result["fsm_state"] == FSMState.COMMITTING
        assert result["review_passed"] is True

    @pytest.mark.asyncio
    async def test_retry_sets_coding_state(self, make_review_state):
        """decision=retry → fsm_state=CODING."""
        mock_llm = _make_mock_llm_with_findings(
            [],
            decision="retry",
            passed=False,
            critical_findings=1,
        )
        state = make_review_state()

        from orchestrator.nodes.review import review_node

        result = await review_node(state=state, llm=mock_llm, kb_server=None)
        assert result["fsm_state"] == FSMState.CODING
        assert result["review_passed"] is False
        assert result["critical_findings"] == 1
