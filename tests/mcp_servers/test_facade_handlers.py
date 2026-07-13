"""tests/mcp_servers/test_facade_handlers.py — FacadeHandlers (TD-S5-02).

Покрытие:
- 8 handlers: happy path (mock nodes) + input validation + next_action correctness
  + state propagation между вызовами + error cases.
- DI через конструктор: state_factory + node_* callables + kb_server/bsl_ls_server/etc.
- In-memory state dict (plan_id → state).

См. ADR-0013, D-2026-07-13-07.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_servers.facade.handlers import (
    FacadeHandlers,
    FacadeNotConfiguredError,
    _find_subtask_idx,
    _parse_artifact_id,
    _validate_plan_id,
)


# ─── Test doubles ────────────────────────────────────────────────────────────


class _FakeSubtask:
    """Имитация Subtask (frozen, с id)."""

    def __init__(self, id: str) -> None:
        self.id = id
        self.constraints = None

    def model_dump(self) -> dict[str, Any]:
        return {"id": self.id}


class _FakeIteration:
    """Имитация Iteration."""

    def __init__(self, number: int, code: str) -> None:
        self.number = number
        self.code = code
        self.llm_response = {"explanation": f"explanation for iter {number}", "patterns_applied": ["p1"]}


class _FakeState:
    """Имитация TaskState (frozen-like, с model_copy)."""

    def __init__(
        self,
        task_id: str,
        description: str,
        config_name: str,
        config_version: str,
        platform_version: str,
        fsm_state: str = "planning",
    ) -> None:
        self.task_id = task_id
        self.description = description
        self.config_name = config_name
        self.config_version = config_version
        self.platform_version = platform_version
        self.fsm_state = fsm_state
        self.subtasks: list[_FakeSubtask] = []
        self.current_subtask_idx = 0
        self.current_iteration = 0
        self.iterations: list[_FakeIteration] = []
        self.validation_passed = False
        self.review_passed = False
        self.critical_findings = 0
        self.plan_result: dict[str, Any] | None = None
        self.gather_result: dict[str, Any] | None = None
        self.validate_result: dict[str, Any] | None = None
        self.review_result: dict[str, Any] | None = None
        self.commit_result: dict[str, Any] | None = None

    def model_copy(self, *, update: dict[str, Any] | None = None) -> _FakeState:
        """Создать копию с обновлениями (имитация Pydantic model_copy)."""
        new = _FakeState(
            task_id=self.task_id,
            description=self.description,
            config_name=self.config_name,
            config_version=self.config_version,
            platform_version=self.platform_version,
            fsm_state=self.fsm_state,
        )
        new.subtasks = list(self.subtasks)
        new.current_subtask_idx = self.current_subtask_idx
        new.current_iteration = self.current_iteration
        new.iterations = list(self.iterations)
        new.validation_passed = self.validation_passed
        new.review_passed = self.review_passed
        new.critical_findings = self.critical_findings
        new.plan_result = self.plan_result
        new.gather_result = self.gather_result
        new.validate_result = self.validate_result
        new.review_result = self.review_result
        new.commit_result = self.commit_result
        if update:
            for k, v in update.items():
                setattr(new, k, v)
        return new

    def model_dump_json(self) -> str:
        """Сериализация в JSON (имитация Pydantic model_dump_json, для FacadeStateStore)."""
        import json

        return json.dumps(
            {
                "task_id": self.task_id,
                "description": self.description,
                "config_name": self.config_name,
                "config_version": self.config_version,
                "platform_version": self.platform_version,
                "fsm_state": self.fsm_state,
                "subtasks": [{"id": s.id, "constraints": None} for s in self.subtasks],
                "current_subtask_idx": self.current_subtask_idx,
                "current_iteration": self.current_iteration,
                "iterations": [
                    {
                        "number": i.number,
                        "code": i.code,
                        "llm_response": i.llm_response,
                    }
                    for i in self.iterations
                ],
                "validation_passed": self.validation_passed,
                "review_passed": self.review_passed,
                "critical_findings": self.critical_findings,
                "plan_result": self.plan_result,
                "gather_result": self.gather_result,
                "validate_result": self.validate_result,
                "review_result": self.review_result,
                "commit_result": self.commit_result,
            },
            ensure_ascii=False,
            default=str,
        )

    @classmethod
    def model_validate_json(cls, json_str: str) -> _FakeState:
        """Десериализация из JSON (имитация Pydantic model_validate_json)."""
        import json

        data = json.loads(json_str)
        state = cls(
            task_id=data["task_id"],
            description=data["description"],
            config_name=data["config_name"],
            config_version=data["config_version"],
            platform_version=data["platform_version"],
            fsm_state=data.get("fsm_state", "planning"),
        )
        state.subtasks = [_FakeSubtask(s["id"]) for s in data.get("subtasks", [])]
        state.current_subtask_idx = data.get("current_subtask_idx", 0)
        state.current_iteration = data.get("current_iteration", 0)
        state.iterations = [_FakeIteration(i["number"], i["code"]) for i in data.get("iterations", [])]
        # Восстанавливаем llm_response в Iteration.
        for it, it_data in zip(state.iterations, data.get("iterations", []), strict=False):
            it.llm_response = it_data.get("llm_response", {})
        state.validation_passed = data.get("validation_passed", False)
        state.review_passed = data.get("review_passed", False)
        state.critical_findings = data.get("critical_findings", 0)
        state.plan_result = data.get("plan_result")
        state.gather_result = data.get("gather_result")
        state.validate_result = data.get("validate_result")
        state.review_result = data.get("review_result")
        state.commit_result = data.get("commit_result")
        return state


def _state_factory(**kwargs: Any) -> _FakeState:
    """Factory для создания _FakeState (имитация TaskState)."""
    return _FakeState(**kwargs)


def _make_handlers(
    *,
    plan_result: dict[str, Any] | None = None,
    gather_result: dict[str, Any] | None = None,
    code_str: str = "Функция МояФункция() Возврат 1; КонецФункции",
    validate_passed: bool = True,
    review_decision: str = "proceed",
    kb_server: Any = None,
    bsl_ls_server: Any = None,
    llm: Any = None,
    path_manager: Any = None,
    config_registry: Any = None,
) -> FacadeHandlers:
    """Создать FacadeHandlers с mock node callables."""

    async def _plan_node(state: Any, llm: Any = None, metadata_server: Any = None) -> dict[str, Any]:
        state.subtasks = [_FakeSubtask("st-001"), _FakeSubtask("st-002")]
        return {
            "subtasks": state.subtasks,
            "plan_result": plan_result or {"strategy": "decompose", "rationale": "2 subtasks"},
            "fsm_state": "planning",
        }

    async def _gather_node(state: Any, kb_server: Any = None, metadata_server: Any = None) -> dict[str, Any]:
        return {
            "gather_result": gather_result
            or {"context_summary": "ctx", "patterns_applied": ["p1"], "mcp_calls_made": ["kb.search_kb"]},
            "fsm_state": "gathering",
        }

    async def _code_node(state: Any, llm: Any = None) -> dict[str, Any]:
        iter_num = state.current_iteration + 1
        new_iter = _FakeIteration(iter_num, code_str)
        state.iterations = list(state.iterations) + [new_iter]
        return {
            "iterations": state.iterations,
            "current_iteration": iter_num,
            "fsm_state": "coding",
        }

    async def _validate_node(state: Any, bsl_ls_server: Any = None, kb_server: Any = None) -> dict[str, Any]:
        return {
            "validation_passed": validate_passed,
            "validate_result": {
                "findings": [{"code": "X"}] if not validate_passed else [],
                "severity_breakdown": {"critical": 0, "warning": 1},
                "failed_checks": [] if validate_passed else [{"check": "bsl_ls"}],
            },
            "fsm_state": "validating",
        }

    async def _review_node(state: Any, llm: Any = None, kb_server: Any = None) -> dict[str, Any]:
        return {
            "review_passed": review_decision == "proceed",
            "review_result": {
                "decision": review_decision,
                "findings": [],
                "rationale": "looks good",
            },
            "fsm_state": "reviewing",
        }

    async def _commit_node(state: Any, git_server: Any = None, repo_path: Any = None) -> dict[str, Any]:
        return {
            "commit_result": {"files_changed": ["/tmp/x.bsl"], "pr_url": "https://example.com/pr/1"},
            "fsm_state": "committing",
        }

    # FacadeStateStore с state_class=_FakeState для round-trip в tests.
    from mcp_servers.facade import FacadeStateStore

    state_store = FacadeStateStore(state_class=_FakeState)

    return FacadeHandlers(
        state_factory=_state_factory,
        node_plan=_plan_node,
        node_gather=_gather_node,
        node_code=_code_node,
        node_validate=_validate_node,
        node_review=_review_node,
        node_commit=_commit_node,
        state_store=state_store,
        kb_server=kb_server,
        bsl_ls_server=bsl_ls_server,
        llm=llm,
        path_manager=path_manager,
        config_registry=config_registry,
    )


# ─── Helpers tests ───────────────────────────────────────────────────────────


class TestHelpers:
    """Module-level helper functions."""

    def test_validate_plan_id_ok(self) -> None:
        _validate_plan_id("plan-abc123")
        _validate_plan_id("plan_001")

    @pytest.mark.parametrize(
        "bad_id",
        [
            "",
            "plan with spaces",
            "plan/with/slashes",
            "plan;rm -rf",
            "x" * 200,  # слишком длинный
        ],
    )
    def test_validate_plan_id_rejects(self, bad_id: str) -> None:
        with pytest.raises(ValueError, match="Invalid plan_id"):
            _validate_plan_id(bad_id)

    def test_parse_artifact_id_ok(self) -> None:
        subtask_id, iteration = _parse_artifact_id("st-001#3")
        assert subtask_id == "st-001"
        assert iteration == 3

    def test_parse_artifact_id_no_hash(self) -> None:
        with pytest.raises(ValueError, match="Invalid artifact_id format"):
            _parse_artifact_id("st-001")

    def test_parse_artifact_id_bad_iteration(self) -> None:
        with pytest.raises(ValueError, match="Invalid iteration"):
            _parse_artifact_id("st-001#abc")

    def test_parse_artifact_id_zero_iteration(self) -> None:
        with pytest.raises(ValueError, match=">= 1"):
            _parse_artifact_id("st-001#0")

    def test_find_subtask_idx_found(self) -> None:
        state = _FakeState("t1", "d", "c", "v", "p")
        state.subtasks = [_FakeSubtask("st-001"), _FakeSubtask("st-002")]
        assert _find_subtask_idx(state, "st-002") == 1

    def test_find_subtask_idx_not_found(self) -> None:
        state = _FakeState("t1", "d", "c", "v", "p")
        state.subtasks = [_FakeSubtask("st-001")]
        assert _find_subtask_idx(state, "st-999") is None


# ─── handle_plan ─────────────────────────────────────────────────────────────


class TestHandlePlan:
    @pytest.mark.asyncio
    async def test_plan_creates_state_and_returns_plan_id(self) -> None:
        h = _make_handlers()
        result = await h.handle_plan(
            {
                "task": "Add posting handler",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        assert result["plan_id"].startswith("plan-")
        assert len(result["subtasks"]) == 2
        assert result["subtasks"][0]["id"] == "st-001"
        assert result["decomposition_strategy"] == "decompose"
        assert result["next_action"]["tool"] == "gather"
        assert result["next_action"]["args"]["subtask_id"] == "st-001"
        assert result["artifact_id"] == result["plan_id"]

    @pytest.mark.asyncio
    async def test_plan_missing_required_field_raises(self) -> None:
        from pydantic import ValidationError

        h = _make_handlers()
        with pytest.raises(ValidationError):
            await h.handle_plan({"task": "test"})  # нет config_name etc.

    @pytest.mark.asyncio
    async def test_plan_extra_field_raises(self) -> None:
        from pydantic import ValidationError

        h = _make_handlers()
        with pytest.raises(ValidationError):  # extra=forbid
            await h.handle_plan(
                {
                    "task": "test",
                    "config_name": "ut11",
                    "config_version": "4.5.3",
                    "platform_version": "8.3.20",
                    "extra_field": "bad",
                }
            )

    @pytest.mark.asyncio
    async def test_plan_persists_state_for_later(self) -> None:
        h = _make_handlers()
        result = await h.handle_plan(
            {
                "task": "test",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        plan_id = result["plan_id"]
        # State сохранён в state_store (in-memory fallback).
        saved_state = await h._state_store.load_state(plan_id)
        assert saved_state is not None
        assert saved_state.subtasks[0].id == "st-001"


# ─── handle_gather ───────────────────────────────────────────────────────────


class TestHandleGather:
    @pytest.mark.asyncio
    async def test_gather_after_plan(self) -> None:
        h = _make_handlers()
        plan_result = await h.handle_plan(
            {
                "task": "test",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        plan_id = plan_result["plan_id"]

        result = await h.handle_gather({"plan_id": plan_id, "subtask_id": "st-001"})
        assert result["subtask_id"] == "st-001"
        assert result["context_summary"] == "ctx"
        assert result["patterns_applied"] == ["p1"]
        assert result["next_action"]["tool"] == "generate"
        assert result["artifact_id"] == f"{plan_id}#st-001"

    @pytest.mark.asyncio
    async def test_gather_unknown_plan_id_raises(self) -> None:
        h = _make_handlers()
        with pytest.raises(KeyError, match="not found"):
            await h.handle_gather({"plan_id": "plan-unknown", "subtask_id": "st-001"})

    @pytest.mark.asyncio
    async def test_gather_unknown_subtask_id_raises(self) -> None:
        h = _make_handlers()
        plan_result = await h.handle_plan(
            {
                "task": "test",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        with pytest.raises(KeyError, match="not found in plan"):
            await h.handle_gather({"plan_id": plan_result["plan_id"], "subtask_id": "st-999"})

    @pytest.mark.asyncio
    async def test_gather_switches_subtask_idx(self) -> None:
        h = _make_handlers()
        plan_result = await h.handle_plan(
            {
                "task": "test",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        plan_id = plan_result["plan_id"]
        # Gather для второй подзадачи.
        await h.handle_gather({"plan_id": plan_id, "subtask_id": "st-002"})
        # State должен переключить current_subtask_idx на 1.
        saved_state = await h._state_store.load_state(plan_id)
        assert saved_state.current_subtask_idx == 1


# ─── handle_generate ─────────────────────────────────────────────────────────


class TestHandleGenerate:
    @pytest.mark.asyncio
    async def test_generate_after_plan_and_gather(self) -> None:
        h = _make_handlers()
        plan_result = await h.handle_plan(
            {
                "task": "test",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        plan_id = plan_result["plan_id"]
        await h.handle_gather({"plan_id": plan_id, "subtask_id": "st-001"})

        result = await h.handle_generate({"plan_id": plan_id, "subtask_id": "st-001", "iteration": 1})
        assert result["subtask_id"] == "st-001"
        assert result["iteration"] == 1
        assert "МояФункция" in result["code"]
        assert result["next_action"]["tool"] == "validate"
        assert result["artifact_id"] == "st-001#1"

    @pytest.mark.asyncio
    async def test_generate_increments_iteration(self) -> None:
        h = _make_handlers()
        plan_result = await h.handle_plan(
            {
                "task": "test",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        plan_id = plan_result["plan_id"]
        await h.handle_gather({"plan_id": plan_id, "subtask_id": "st-001"})

        # Первый generate.
        r1 = await h.handle_generate({"plan_id": plan_id, "subtask_id": "st-001", "iteration": 1})
        assert r1["iteration"] == 1
        # Второй generate (retry).
        r2 = await h.handle_generate({"plan_id": plan_id, "subtask_id": "st-001", "iteration": 2})
        assert r2["iteration"] == 2


# ─── handle_validate ─────────────────────────────────────────────────────────


class TestHandleValidate:
    @pytest.mark.asyncio
    async def test_validate_passed(self) -> None:
        h = _make_handlers(validate_passed=True)
        plan_result = await h.handle_plan(
            {
                "task": "test",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        plan_id = plan_result["plan_id"]
        await h.handle_gather({"plan_id": plan_id, "subtask_id": "st-001"})
        await h.handle_generate({"plan_id": plan_id, "subtask_id": "st-001", "iteration": 1})

        result = await h.handle_validate({"artifact_id": "st-001#1"})
        assert result["passed"] is True
        assert result["next_action"]["tool"] == "review"

    @pytest.mark.asyncio
    async def test_validate_failed(self) -> None:
        h = _make_handlers(validate_passed=False)
        plan_result = await h.handle_plan(
            {
                "task": "test",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        plan_id = plan_result["plan_id"]
        await h.handle_gather({"plan_id": plan_id, "subtask_id": "st-001"})
        await h.handle_generate({"plan_id": plan_id, "subtask_id": "st-001", "iteration": 1})

        result = await h.handle_validate({"artifact_id": "st-001#1"})
        assert result["passed"] is False
        assert result["next_action"]["tool"] == "generate"
        assert result["next_action"]["args"]["iteration"] == 2
        assert len(result["failed_checks"]) > 0

    @pytest.mark.asyncio
    async def test_validate_bad_artifact_id_format(self) -> None:
        h = _make_handlers()
        with pytest.raises(ValueError, match="Invalid artifact_id format"):
            await h.handle_validate({"artifact_id": "no-hash"})

    @pytest.mark.asyncio
    async def test_validate_unknown_subtask(self) -> None:
        h = _make_handlers()
        with pytest.raises(KeyError, match="not in cache"):
            await h.handle_validate({"artifact_id": "st-unknown#1"})


# ─── handle_review ───────────────────────────────────────────────────────────


class TestHandleReview:
    @pytest.mark.asyncio
    async def test_review_proceed_triggers_commit(self) -> None:
        h = _make_handlers(review_decision="proceed")
        plan_result = await h.handle_plan(
            {
                "task": "test",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        plan_id = plan_result["plan_id"]
        await h.handle_gather({"plan_id": plan_id, "subtask_id": "st-001"})
        await h.handle_generate({"plan_id": plan_id, "subtask_id": "st-001", "iteration": 1})
        await h.handle_validate({"artifact_id": "st-001#1"})

        result = await h.handle_review({"artifact_id": "st-001#1"})
        assert result["decision"] == "proceed"
        # proceed → commit_node вызван → pr_url.
        assert result["pr_url"] == "https://example.com/pr/1"
        # Есть следующая подзадача → next_action=gather st-002.
        assert result["next_action"]["tool"] == "gather"
        assert result["next_action"]["args"]["subtask_id"] == "st-002"

    @pytest.mark.asyncio
    async def test_review_proceed_last_subtask(self) -> None:
        h = _make_handlers(review_decision="proceed")
        plan_result = await h.handle_plan(
            {
                "task": "test",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        plan_id = plan_result["plan_id"]
        # Gather/generate/validate для ПОСЛЕДНЕЙ подзадачи (st-002).
        await h.handle_gather({"plan_id": plan_id, "subtask_id": "st-002"})
        await h.handle_generate({"plan_id": plan_id, "subtask_id": "st-002", "iteration": 1})
        await h.handle_validate({"artifact_id": "st-002#1"})

        result = await h.handle_review({"artifact_id": "st-002#1"})
        assert result["decision"] == "proceed"
        # Нет следующей подзадачи → next_action=data_status.
        assert result["next_action"]["tool"] == "data_status"

    @pytest.mark.asyncio
    async def test_review_retry(self) -> None:
        h = _make_handlers(review_decision="retry")
        plan_result = await h.handle_plan(
            {
                "task": "test",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        plan_id = plan_result["plan_id"]
        await h.handle_gather({"plan_id": plan_id, "subtask_id": "st-001"})
        await h.handle_generate({"plan_id": plan_id, "subtask_id": "st-001", "iteration": 1})
        await h.handle_validate({"artifact_id": "st-001#1"})

        result = await h.handle_review({"artifact_id": "st-001#1"})
        assert result["decision"] == "retry"
        assert result["next_action"]["tool"] == "generate"
        assert result["next_action"]["args"]["iteration"] == 2
        # retry → commit_node НЕ вызван → pr_url is None.
        assert result["pr_url"] is None

    @pytest.mark.asyncio
    async def test_review_escalate(self) -> None:
        h = _make_handlers(review_decision="escalate")
        plan_result = await h.handle_plan(
            {
                "task": "test",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        plan_id = plan_result["plan_id"]
        await h.handle_gather({"plan_id": plan_id, "subtask_id": "st-001"})
        await h.handle_generate({"plan_id": plan_id, "subtask_id": "st-001", "iteration": 1})
        await h.handle_validate({"artifact_id": "st-001#1"})

        result = await h.handle_review({"artifact_id": "st-001#1"})
        assert result["decision"] == "escalate"
        assert result["next_action"]["tool"] == "data_status"


# ─── handle_explain ──────────────────────────────────────────────────────────


class TestHandleExplain:
    @pytest.mark.asyncio
    async def test_explain_without_kb_server(self) -> None:
        h = _make_handlers()
        result = await h.handle_explain({"query": "Как сделать обработку проведения?"})
        assert "KB сервер не настроен" in result["explanation"]
        assert result["related_patterns"] == []

    @pytest.mark.asyncio
    async def test_explain_with_kb_server(self) -> None:
        # Mock kb_server.search_kb.
        kb_server = MagicMock()
        search_output = MagicMock()
        search_output.results = [
            {"id": "p1", "category": "pattern"},
            {"id": "ap1", "category": "antipattern"},
        ]
        kb_server.search_kb = AsyncMock(return_value=search_output)

        h = _make_handlers(kb_server=kb_server)
        result = await h.handle_explain({"query": "test query"})
        assert "KB: найдено 2" in result["explanation"]
        assert len(result["related_patterns"]) == 1
        assert len(result["related_antipatterns"]) == 1

    @pytest.mark.asyncio
    async def test_explain_kb_failure_degrades(self) -> None:
        kb_server = MagicMock()
        kb_server.search_kb = AsyncMock(side_effect=RuntimeError("kb down"))

        h = _make_handlers(kb_server=kb_server)
        result = await h.handle_explain({"query": "test"})
        assert "KB недоступен" in result["explanation"]

    @pytest.mark.asyncio
    async def test_explain_no_query_no_code(self) -> None:
        h = _make_handlers()
        result = await h.handle_explain({})
        # Нет query, нет code → KB search не вызывается.
        assert "не настроен" in result["explanation"]


# ─── handle_run_cli ──────────────────────────────────────────────────────────


class TestHandleRunCli:
    @pytest.mark.asyncio
    async def test_run_cli_kb_proxy(self) -> None:
        kb_server = MagicMock()
        kb_server.search_kb = AsyncMock()
        kb_server.search_kb.return_value = MagicMock()
        kb_server.search_kb.return_value.model_dump = MagicMock(return_value={"results": []})

        h = _make_handlers(kb_server=kb_server)
        result = await h.handle_run_cli({"tool_name": "kb.search_kb", "args": {"query": "test", "top_k": 3}})
        assert result["tool_name"] == "kb.search_kb"
        assert result["warning"] is None
        assert result["result"] == {"results": []}
        kb_server.search_kb.assert_called_once_with(query="test", top_k=3)

    @pytest.mark.asyncio
    async def test_run_cli_bsl_ls_proxy(self) -> None:
        bsl_ls_server = MagicMock()
        bsl_ls_server.lint = AsyncMock()
        bsl_ls_server.lint.return_value = MagicMock()
        bsl_ls_server.lint.return_value.model_dump = MagicMock(return_value={"total": 0})

        h = _make_handlers(bsl_ls_server=bsl_ls_server)
        result = await h.handle_run_cli({"tool_name": "bsl_ls.lint", "args": {"code": "x = 1;"}})
        assert result["warning"] is None
        assert result["result"] == {"total": 0}

    @pytest.mark.asyncio
    async def test_run_cli_unknown_tool_warning(self) -> None:
        h = _make_handlers()
        result = await h.handle_run_cli({"tool_name": "metadata.get_metadata", "args": {"object_ref": "Catalog.X"}})
        assert result["warning"] is not None
        assert "not available" in result["warning"]
        assert result["result"] == {}

    @pytest.mark.asyncio
    async def test_run_cli_unknown_kb_method_raises_warning(self) -> None:
        kb_server = MagicMock()
        h = _make_handlers(kb_server=kb_server)
        result = await h.handle_run_cli({"tool_name": "kb.unknown_method", "args": {}})
        assert result["warning"] is not None
        assert "failed" in result["warning"]

    @pytest.mark.asyncio
    async def test_run_cli_missing_required_field(self) -> None:
        from pydantic import ValidationError

        h = _make_handlers()
        with pytest.raises(ValidationError):
            await h.handle_run_cli({"args": {}})  # нет tool_name


# ─── handle_data_status ──────────────────────────────────────────────────────


class TestHandleDataStatus:
    @pytest.mark.asyncio
    async def test_data_status_without_path_manager(self) -> None:
        h = _make_handlers()
        result = await h.handle_data_status({})
        assert result["paths"] == {}
        assert any("PathManager" in m for m in result["missing_prerequisites"])
        assert any("ConfigRegistry" in m for m in result["missing_prerequisites"])

    @pytest.mark.asyncio
    async def test_data_status_with_path_manager(self) -> None:
        path_manager = MagicMock()
        path_manager.validate = MagicMock(return_value={"data_dir": True, "derived_dir": True, "missing_dir": False})
        path_manager.freshness_check = MagicMock(return_value={"unified_metadata": True, "api_reference": True})

        config_registry = MagicMock()
        entry1 = MagicMock()
        entry1.name = "ut11"
        entry1.version = "4.5.3"
        entry1.is_fresh = True
        config_registry.list = MagicMock(return_value=iter([entry1]))

        h = _make_handlers(path_manager=path_manager, config_registry=config_registry)
        result = await h.handle_data_status({})
        assert result["paths"]["data_dir"] is True
        assert result["paths"]["missing_dir"] is False
        assert any("missing_dir" in m for m in result["missing_prerequisites"])
        assert len(result["configs"]) == 1
        assert result["configs"][0]["name"] == "ut11"
        assert "ut11:4.5.3" in result["indexes_freshness"]

    @pytest.mark.asyncio
    async def test_data_status_rejects_args(self) -> None:
        h = _make_handlers()
        with pytest.raises(ValueError, match="no arguments"):
            await h.handle_data_status({"unexpected": "arg"})


# ─── Full workflow ───────────────────────────────────────────────────────────


class TestFullWorkflow:
    """End-to-end: plan → gather → generate → validate → review (proceed)."""

    @pytest.mark.asyncio
    async def test_full_workflow_single_subtask(self) -> None:
        h = _make_handlers(
            review_decision="proceed",
            validate_passed=True,
            code_str="Функция ОбработкаПроведения() КонецФункции",
        )

        # 1. plan
        plan_out = await h.handle_plan(
            {
                "task": "Add posting handler",
                "config_name": "ut11",
                "config_version": "4.5.3",
                "platform_version": "8.3.20",
            }
        )
        plan_id = plan_out["plan_id"]
        assert plan_out["next_action"]["tool"] == "gather"
        st1 = plan_out["next_action"]["args"]["subtask_id"]

        # 2. gather
        gather_out = await h.handle_gather({"plan_id": plan_id, "subtask_id": st1})
        assert gather_out["next_action"]["tool"] == "generate"

        # 3. generate
        gen_out = await h.handle_generate({"plan_id": plan_id, "subtask_id": st1, "iteration": 1})
        artifact_id = gen_out["artifact_id"]
        assert gen_out["next_action"]["tool"] == "validate"
        assert gen_out["next_action"]["args"]["artifact_id"] == artifact_id

        # 4. validate
        val_out = await h.handle_validate({"artifact_id": artifact_id})
        assert val_out["passed"] is True
        assert val_out["next_action"]["tool"] == "review"

        # 5. review (proceed → commit)
        rev_out = await h.handle_review({"artifact_id": artifact_id})
        assert rev_out["decision"] == "proceed"
        assert rev_out["pr_url"] is not None
        # Была одна подзадача из plan, но _make_handlers создаёт 2 (st-001, st-002).
        # После st-001 → следующая st-002.
        assert rev_out["next_action"]["tool"] == "gather"
        assert rev_out["next_action"]["args"]["subtask_id"] == "st-002"
