"""tests/orchestrator/test_commit_node.py — commit_node (TD-S6-02).

Покрытие:
- Real git flow (mock GitServer): create_branch + commit + CommitResult с sha.
- open_pr flow (mock GitServer.open_pr, env 1C_AI_OPEN_PR=1).
- Fallback file save (git_server=None): Sprint 2 логика.
- file_path derivation: CommonModule / Catalog / Document / other.
- Commit message + PR body structure.

См. ADR-0004, ADR-0005, ADR-0010, D-2026-07-13-11.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.nodes.commit import (
    _build_commit_message,
    _build_pr_body,
    _derive_file_path,
    commit_node,
)
from orchestrator.state import FSMState, Iteration, Subtask, TaskState
from parsers.models import ObjectRef


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_state() -> TaskState:
    """TaskState с одной итерацией кода."""
    subtask = Subtask(
        id="st-001",
        name="ОбработкаПроведения",
        target_module=ObjectRef(type="CommonModule", name="ОбработкаПроведения"),
        description="Add posting handler",
        acceptance_criteria=["Код компилируется", "Движения записываются"],
        max_iterations=3,
    )
    return TaskState(
        task_id="task-test-001",
        description="Add posting handler for Реализация",
        config_name="ut11",
        config_version="4.5.3",
        platform_version="8.3.20",
        subtasks=[subtask],
        current_subtask_idx=0,
        current_iteration=1,
        iterations=[
            Iteration(
                number=1,
                code="Функция ОбработкаПроведения() Возврат Истина; КонецФункции",
                llm_response={},
            )
        ],
        fsm_state=FSMState.REVIEWING,
    )


def _mock_git_server(
    *,
    commit_sha: str = "abc1234567890",
    pr_url: str | None = None,
    pr_number: int | None = None,
) -> MagicMock:
    """Mock GitServer с async methods."""
    server = MagicMock()

    server.create_branch = AsyncMock()
    server.create_branch.return_value = MagicMock(
        branch_name="feature/task-tes-st-001",
        base="main",
    )

    server.commit = AsyncMock()
    server.commit.return_value = MagicMock(
        commit_sha=commit_sha,
        files_changed=["CommonModules/ОбработкаПроведения/Ext/Module.bsl"],
    )

    server.open_pr = AsyncMock()
    server.open_pr.return_value = MagicMock(
        pr_url=pr_url or "https://github.com/owner/repo/pull/1",
        pr_number=pr_number or 1,
        branch="feature/task-tes-st-001",
    )

    return server


# ─── Real git flow ───────────────────────────────────────────────────────────


class TestCommitNodeGitFlow:
    """Real git flow (git_server + repo_path заданы)."""

    @pytest.mark.asyncio
    async def test_git_flow_creates_branch_and_commit(
        self, sample_state: TaskState, tmp_path: Path
    ) -> None:
        git_server = _mock_git_server(commit_sha="deadbeef1234")
        repo_path = str(tmp_path)

        result = await commit_node(
            sample_state,
            git_server=git_server,
            repo_path=repo_path,
        )

        assert result["fsm_state"] == FSMState.DONE
        commit_result = result["commit_result"]
        assert commit_result["commit_sha"] == "deadbeef1234"
        assert commit_result["branch_name"] == "feature/task-tes-st-001"
        assert commit_result["pr_url"] is None  # 1C_AI_OPEN_PR не задан
        # create_branch вызван.
        git_server.create_branch.assert_called_once()
        # commit вызван с file_path.
        git_server.commit.assert_called_once()
        call_kwargs = git_server.commit.call_args.kwargs
        assert call_kwargs["repo_path"] == repo_path
        assert call_kwargs["branch"] == "feature/task-tes-st-001"
        assert "CommonModules/ОбработкаПроведения/Ext/Module.bsl" in call_kwargs["files"]
        # open_pr НЕ вызван (env не задан).
        git_server.open_pr.assert_not_called()

    @pytest.mark.asyncio
    async def test_git_flow_with_open_pr(
        self, sample_state: TaskState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("1C_AI_OPEN_PR", "1")
        git_server = _mock_git_server(pr_url="https://github.com/owner/repo/pull/42", pr_number=42)
        repo_path = str(tmp_path)

        result = await commit_node(
            sample_state,
            git_server=git_server,
            repo_path=repo_path,
        )

        commit_result = result["commit_result"]
        assert commit_result["pr_url"] == "https://github.com/owner/repo/pull/42"
        assert commit_result["pr_number"] == 42
        git_server.open_pr.assert_called_once()

    @pytest.mark.asyncio
    async def test_git_flow_open_pr_failure_continues_without_pr(
        self, sample_state: TaskState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """open_pr упал — commit остаётся, pr_url=None."""
        monkeypatch.setenv("1C_AI_OPEN_PR", "1")
        git_server = _mock_git_server()
        git_server.open_pr = AsyncMock(side_effect=RuntimeError("gh not installed"))
        repo_path = str(tmp_path)

        result = await commit_node(
            sample_state,
            git_server=git_server,
            repo_path=repo_path,
        )

        commit_result = result["commit_result"]
        assert commit_result["commit_sha"] == "abc1234567890"  # commit прошёл
        assert commit_result["pr_url"] is None  # PR не открыт
        assert commit_result["pr_number"] is None

    @pytest.mark.asyncio
    async def test_git_flow_writes_file_to_repo(
        self, sample_state: TaskState, tmp_path: Path
    ) -> None:
        """Код записывается в файл внутри repo_path."""
        git_server = _mock_git_server()
        repo_path = str(tmp_path)

        await commit_node(sample_state, git_server=git_server, repo_path=repo_path)

        # Файл должен существовать.
        expected_file = tmp_path / "CommonModules" / "ОбработкаПроведения" / "Ext" / "Module.bsl"
        assert expected_file.exists()
        assert "ОбработкаПроведения" in expected_file.read_text(encoding="utf-8")


# ─── Fallback: file save ────────────────────────────────────────────────────


class TestCommitNodeFallback:
    """Fallback: git_server=None → file save в runtime/generated/."""

    @pytest.mark.asyncio
    async def test_fallback_no_git_server(self, sample_state: TaskState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Без git_server — file fallback."""
        monkeypatch.chdir(tmp_path)
        result = await commit_node(sample_state, git_server=None, repo_path=None)

        commit_result = result["commit_result"]
        assert "file fallback" in commit_result["commit_sha"]
        assert commit_result["pr_url"] is None
        assert len(commit_result["files_changed"]) == 1
        # Файл создан в runtime/generated/.
        assert "runtime/generated" in commit_result["files_changed"][0]

    @pytest.mark.asyncio
    async def test_fallback_no_repo_path(
        self, sample_state: TaskState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """git_server задан, но repo_path=None → file fallback."""
        monkeypatch.chdir(tmp_path)
        git_server = _mock_git_server()

        result = await commit_node(sample_state, git_server=git_server, repo_path=None)

        commit_result = result["commit_result"]
        assert "file fallback" in commit_result["commit_sha"]
        # git_server не вызывался (fallback).
        git_server.create_branch.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_uses_env_repo_path(
        self, sample_state: TaskState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """repo_path из env 1C_AI_REPO_PATH если не передан явно."""
        monkeypatch.setenv("1C_AI_REPO_PATH", str(tmp_path))
        git_server = _mock_git_server()

        result = await commit_node(sample_state, git_server=git_server, repo_path=None)

        commit_result = result["commit_result"]
        # env задан → real git flow (не fallback).
        assert "file fallback" not in commit_result["commit_sha"]
        assert commit_result["commit_sha"] == "abc1234567890"
        git_server.create_branch.assert_called_once()


# ─── file_path derivation ────────────────────────────────────────────────────


class TestDeriveFilePath:
    """_derive_file_path по convention 1С."""

    def test_common_module(self) -> None:
        subtask = Subtask(
            id="st-1",
            name="X",
            target_module=ObjectRef(type="CommonModule", name="ОбщегоНазначения"),
            description="d",
        )
        assert _derive_file_path(subtask, 1) == "CommonModules/ОбщегоНазначения/Ext/Module.bsl"

    def test_catalog(self) -> None:
        subtask = Subtask(
            id="st-1",
            name="X",
            target_module=ObjectRef(type="Catalog", name="Товары"),
            description="d",
        )
        assert _derive_file_path(subtask, 1) == "Catalogs/Товары/Ext/ObjectModule.bsl"

    def test_document(self) -> None:
        subtask = Subtask(
            id="st-1",
            name="X",
            target_module=ObjectRef(type="Document", name="Продажа"),
            description="d",
        )
        assert _derive_file_path(subtask, 1) == "Documents/Продажа/Ext/ObjectModule.bsl"

    def test_other_type_fallback(self) -> None:
        subtask = Subtask(
            id="st-abc",
            name="X",
            target_module=ObjectRef(type="DataProcessor", name="Обработка"),
            description="d",
        )
        path = _derive_file_path(subtask, 2)
        assert path == "Generated/st-abc_2.bsl"


# ─── Commit message + PR body ───────────────────────────────────────────────


class TestCommitMessage:
    """_build_commit_message + _build_pr_body."""

    def test_commit_message_includes_task_and_subtask(self, sample_state: TaskState) -> None:
        subtask = sample_state.current_subtask
        msg = _build_commit_message(sample_state, subtask, 1)
        assert "feat(ОбработкаПроведения)" in msg
        assert "iter 1" in msg
        assert "task-test-001" in msg

    def test_pr_body_includes_criteria(self, sample_state: TaskState) -> None:
        subtask = sample_state.current_subtask
        body = _build_pr_body(sample_state, subtask, 1)
        assert "## Задача" in body
        assert "## Подзадача" in body
        assert "## Критерии приёмки" in body
        assert "Код компилируется" in body
        assert "ОбработкаПроведения" in body


# ─── Integration: Facade handle_review → node_commit git flow ────────────────


class TestFacadeReviewCommitGitFlow:
    """handle_review proceed → node_commit с git_server (real flow)."""

    @pytest.mark.asyncio
    async def test_facade_review_proceed_with_git_server(self, tmp_path: Path) -> None:
        """Facade передаёт git_server + repo_path в node_commit."""
        from mcp_servers.facade.handlers import FacadeHandlers

        # Mock state_factory + nodes.
        state = TaskState(
            task_id="task-1",
            description="d",
            config_name="ut11",
            config_version="4.5.3",
            platform_version="8.3.20",
            subtasks=[
                Subtask(
                    id="st-1",
                    name="X",
                    target_module=ObjectRef(type="CommonModule", name="М"),
                    description="d",
                )
            ],
            current_iteration=1,
            iterations=[Iteration(number=1, code="x", llm_response={})],
            fsm_state=FSMState.VALIDATING,
            validation_passed=True,
            review_passed=True,
        )

        git_server = _mock_git_server(commit_sha="facade123")

        async def _state_factory(**kwargs: Any) -> TaskState:
            return state

        async def _node_review(s: Any, llm: Any = None, kb_server: Any = None) -> dict[str, Any]:
            return {"review_result": {"decision": "proceed", "findings": [], "rationale": "ok"}}

        async def _node_commit(s: Any, git_server: Any = None, repo_path: Any = None) -> dict[str, Any]:
            # Проверяем что git_server проброшен.
            assert git_server is not None
            assert repo_path == str(tmp_path)
            return {
                "commit_result": {
                    "commit_sha": "facade123",
                    "branch_name": "feature/x",
                    "files_changed": ["x.bsl"],
                    "pr_url": "https://example.com/pr/1",
                },
                "fsm_state": "done",
            }

        h = FacadeHandlers(
            state_factory=_state_factory,
            node_review=_node_review,
            node_commit=_node_commit,
            git_server=git_server,
            repo_path=str(tmp_path),
        )
        # Подготовим state в in-memory dict через handle_plan-like flow.
        h._save_state("plan-x", state)

        result = await h.handle_review({"artifact_id": "st-1#1"})
        assert result["decision"] == "proceed"
        assert result["pr_url"] == "https://example.com/pr/1"
