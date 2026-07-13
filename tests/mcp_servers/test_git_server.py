"""tests/mcp_servers/test_git_server.py — GitServer (TD-S5-03).

Покрытие:
- 4 tools (create_branch, commit, open_pr, diff): happy path (mock subprocess).
- Безопасность: branch name validation, repo_path validation, relative paths
  validation, secrets in diff scan.
- Errors: GitValidationError, GitCommandError, GitTimeoutError, SecretDetectedError,
  FileNotFoundError (gh not installed).
- Tool Implementations (CreateBranchImplementation etc.) — обёртки.
- Integration (skip-if TEST_GIT_REPO not set): real git repo roundtrip.

См. ADR-0010, D-2026-07-13-08.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_servers.git import (
    CommitImplementation,
    CreateBranchImplementation,
    DiffImplementation,
    GitCommandError,
    GitServer,
    GitTimeoutError,
    GitValidationError,
    OpenPrImplementation,
    SecretDetectedError,
)
from mcp_servers.git.server import (
    _parse_diff_stat,
    _scan_diff_for_secrets,
    _validate_branch_name,
    _validate_relative_paths,
    _validate_repo_path,
)


# ─── Test doubles ────────────────────────────────────────────────────────────


class _FakeProc:
    """Имитация asyncio.subprocess.Process."""

    def __init__(
        self,
        returncode: int = 0,
        stdout: bytes = b"",
        stderr: bytes = b"",
        delay: float = 0.0,
    ) -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._delay = delay
        self._killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._stdout, self._stderr

    def kill(self) -> None:
        self._killed = True

    async def wait(self) -> int:
        return self.returncode


def _make_subprocess_patch(proc: _FakeProc) -> Any:
    """Создать patch для asyncio.create_subprocess_exec, возвращающий proc."""

    async def _fake(*args: Any, **kwargs: Any) -> _FakeProc:
        return proc

    return _fake


# ─── Validations ─────────────────────────────────────────────────────────────


class TestValidations:
    """Security validators."""

    @pytest.mark.parametrize(
        "good",
        [
            "main",
            "feature/add-posting",
            "feature_add_posting",
            "bugfix-123",
            "release.v2.0",
            "wip",
        ],
    )
    def test_valid_branch_names(self, good: str) -> None:
        _validate_branch_name(good)

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "-leading-dash",
            "has..double",
            "has space",
            "has:colon",
            "has~tilde",
            "has^caret",
            "x" * 201,  # too long
            "кириллица",  # non-ASCII
        ],
    )
    def test_invalid_branch_names(self, bad: str) -> None:
        with pytest.raises(GitValidationError):
            _validate_branch_name(bad)

    def test_validate_repo_path_ok(self, tmp_path: Path) -> None:
        result = _validate_repo_path(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_validate_repo_path_nonexistent(self) -> None:
        with pytest.raises(GitValidationError, match="does not exist"):
            _validate_repo_path("/nonexistent/path/xyz")

    def test_validate_repo_path_not_dir(self, tmp_path: Path) -> None:
        file_path = tmp_path / "file.txt"
        file_path.write_text("x")
        with pytest.raises(GitValidationError, match="not a directory"):
            _validate_repo_path(str(file_path))

    def test_validate_relative_paths_ok(self) -> None:
        _validate_relative_paths(["src/module.bsl", "tests/test_x.py"])

    @pytest.mark.parametrize(
        "bad_files",
        [
            ["/absolute/path.bsl"],
            ["../traversal.bsl"],
            ["src/../../etc/passwd"],
            [""],
            ["valid.bsl", "../invalid.bsl"],
        ],
    )
    def test_validate_relative_paths_rejects(self, bad_files: list[str]) -> None:
        with pytest.raises(GitValidationError):
            _validate_relative_paths(bad_files)


class TestSecretScan:
    """Secret detection in diff."""

    @pytest.mark.parametrize(
        "secret",
        [
            "github_pat_FAKEFAKEFAKEFAKE_fake_token_for_testing_only_NOT_REAL_xxxxxxxx",
            "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
            "AKIAIOSFODNN7EXAMPLE",
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----BEGIN OPENSSH PRIVATE KEY-----",
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "xoxb-1234567890-abcdef",
        ],
    )
    def test_detects_secrets(self, secret: str) -> None:
        with pytest.raises(SecretDetectedError) as exc_info:
            _scan_diff_for_secrets(f"+TOKEN = {secret}")
        assert exc_info.value.pattern_name

    def test_clean_diff_passes(self) -> None:
        diff = "+Функция МояФункция()\n+    Возврат 1;\n+КонецФункции"
        _scan_diff_for_secrets(diff)  # не должно поднять исключение

    def test_secret_error_masks_snippet(self) -> None:
        with pytest.raises(SecretDetectedError) as exc_info:
            _scan_diff_for_secrets("github_pat_11CGTUK6Y0EDoe3IIuCHyF_test_secret_here")
        # Snippet не должен содержать полный секрет.
        assert "***" in exc_info.value.snippet
        assert "11CGTUK6Y0EDoe3IIuCHyF_test_secret_here" not in exc_info.value.snippet


class TestParseDiffStat:
    """Парсер `git diff --stat` вывода."""

    def test_parse_full(self) -> None:
        stat = " src/x.bsl | 10 +++++-----\n 1 file changed, 5 insertions(+), 5 deletions(-)"
        result = _parse_diff_stat(stat)
        assert result == {"files_changed": 1, "insertions": 5, "deletions": 5}

    def test_parse_multi_files(self) -> None:
        stat = (
            " src/x.bsl | 10 +++++-----\n"
            " src/y.bsl |  3 ++\n"
            " 2 files changed, 7 insertions(+), 5 deletions(-)"
        )
        result = _parse_diff_stat(stat)
        assert result == {"files_changed": 2, "insertions": 7, "deletions": 5}

    def test_parse_empty(self) -> None:
        result = _parse_diff_stat("")
        assert result == {"files_changed": 0, "insertions": 0, "deletions": 0}

    def test_parse_only_insertions(self) -> None:
        stat = " src/x.bsl | 3 ++\n 1 file changed, 3 insertions(+)"
        result = _parse_diff_stat(stat)
        assert result == {"files_changed": 1, "insertions": 3, "deletions": 0}


# ─── create_branch ───────────────────────────────────────────────────────────


class TestCreateBranch:
    @pytest.mark.asyncio
    async def test_create_branch_happy_path(self, tmp_path: Path) -> None:
        # git rev-parse --abbrev-ref HEAD → "main"; git checkout -b → ok.
        proc1 = _FakeProc(returncode=0, stdout=b"main\n", stderr=b"")
        proc2 = _FakeProc(returncode=0, stdout=b"", stderr=b"Switched to a new branch")

        call_count = 0

        async def _fake_subprocess(*args: Any, **kwargs: Any) -> _FakeProc:
            nonlocal call_count
            call_count += 1
            return proc1 if call_count == 1 else proc2

        with patch("mcp_servers.git.server.asyncio.create_subprocess_exec", side_effect=_fake_subprocess):
            server = GitServer()
            result = await server.create_branch(
                repo_path=str(tmp_path), branch_name="feature/test"
            )
        assert result.branch_name == "feature/test"
        assert result.base == "main"

    @pytest.mark.asyncio
    async def test_create_branch_invalid_name(self, tmp_path: Path) -> None:
        server = GitServer()
        with pytest.raises(GitValidationError, match="Invalid branch_name"):
            await server.create_branch(repo_path=str(tmp_path), branch_name="-bad")

    @pytest.mark.asyncio
    async def test_create_branch_nonexistent_repo(self) -> None:
        server = GitServer()
        with pytest.raises(GitValidationError, match="does not exist"):
            await server.create_branch(
                repo_path="/nonexistent/xyz", branch_name="feature/test"
            )

    @pytest.mark.asyncio
    async def test_create_branch_git_error(self, tmp_path: Path) -> None:
        proc = _FakeProc(returncode=1, stdout=b"", stderr=b"fatal: already exists")
        with patch(
            "mcp_servers.git.server.asyncio.create_subprocess_exec",
            side_effect=_make_subprocess_patch(proc),
        ):
            server = GitServer()
            # rev-parse OK, checkout fails.
            proc1 = _FakeProc(returncode=0, stdout=b"main\n", stderr=b"")
            proc2 = _FakeProc(returncode=1, stdout=b"", stderr=b"fatal: already exists")
            call_count = 0

            async def _fake(*args: Any, **kwargs: Any) -> _FakeProc:
                nonlocal call_count
                call_count += 1
                return proc1 if call_count == 1 else proc2

            with patch(
                "mcp_servers.git.server.asyncio.create_subprocess_exec", side_effect=_fake
            ):
                with pytest.raises(GitCommandError, match="git checkout -b"):
                    await server.create_branch(
                        repo_path=str(tmp_path), branch_name="feature/test"
                    )


# ─── commit ──────────────────────────────────────────────────────────────────


class TestCommit:
    @pytest.mark.asyncio
    async def test_commit_happy_path(self, tmp_path: Path) -> None:
        # git add → ok; git commit → ok; git rev-parse HEAD → sha.
        procs = [
            _FakeProc(returncode=0, stdout=b"", stderr=b""),  # git add
            _FakeProc(returncode=0, stdout=b"", stderr=b"[main abc1234]"),  # git commit
            _FakeProc(returncode=0, stdout=b"abc1234567\n", stderr=b""),  # rev-parse HEAD
        ]
        call_count = 0

        async def _fake(*args: Any, **kwargs: Any) -> _FakeProc:
            nonlocal call_count
            proc = procs[call_count]
            call_count += 1
            return proc

        with patch(
            "mcp_servers.git.server.asyncio.create_subprocess_exec", side_effect=_fake
        ):
            server = GitServer()
            result = await server.commit(
                repo_path=str(tmp_path),
                message="feat: add x",
                files=["src/x.bsl"],
            )
        assert result.commit_sha == "abc1234567"
        assert result.files_changed == ["src/x.bsl"]

    @pytest.mark.asyncio
    async def test_commit_empty_message(self, tmp_path: Path) -> None:
        server = GitServer()
        with pytest.raises(GitValidationError, match="message cannot be empty"):
            await server.commit(repo_path=str(tmp_path), message="", files=["x.bsl"])

    @pytest.mark.asyncio
    async def test_commit_empty_files(self, tmp_path: Path) -> None:
        server = GitServer()
        with pytest.raises(GitValidationError, match="files cannot be empty"):
            await server.commit(repo_path=str(tmp_path), message="m", files=[])

    @pytest.mark.asyncio
    async def test_commit_absolute_path_rejected(self, tmp_path: Path) -> None:
        server = GitServer()
        with pytest.raises(GitValidationError, match="absolute path"):
            await server.commit(
                repo_path=str(tmp_path),
                message="m",
                files=["/etc/passwd"],
            )

    @pytest.mark.asyncio
    async def test_commit_traversal_rejected(self, tmp_path: Path) -> None:
        server = GitServer()
        with pytest.raises(GitValidationError, match=r"'\.\.' traversal"):
            await server.commit(
                repo_path=str(tmp_path),
                message="m",
                files=["../outside.bsl"],
            )

    @pytest.mark.asyncio
    async def test_commit_with_branch_checkout(self, tmp_path: Path) -> None:
        procs = [
            _FakeProc(returncode=0, stdout=b"", stderr=b"Switched to branch"),  # checkout
            _FakeProc(returncode=0, stdout=b"", stderr=b""),  # add
            _FakeProc(returncode=0, stdout=b"", stderr=b""),  # commit
            _FakeProc(returncode=0, stdout=b"sha123\n", stderr=b""),  # rev-parse
        ]
        call_count = 0

        async def _fake(*args: Any, **kwargs: Any) -> _FakeProc:
            nonlocal call_count
            proc = procs[call_count]
            call_count += 1
            return proc

        with patch(
            "mcp_servers.git.server.asyncio.create_subprocess_exec", side_effect=_fake
        ):
            server = GitServer()
            result = await server.commit(
                repo_path=str(tmp_path),
                message="m",
                files=["x.bsl"],
                branch="feature/test",
            )
        assert result.commit_sha == "sha123"


# ─── open_pr ─────────────────────────────────────────────────────────────────


class TestOpenPr:
    @pytest.mark.asyncio
    async def test_open_pr_happy_path(self, tmp_path: Path) -> None:
        proc = _FakeProc(
            returncode=0,
            stdout=b"https://github.com/owner/repo/pull/42\n",
            stderr=b"",
        )
        with patch(
            "mcp_servers.git.server.asyncio.create_subprocess_exec",
            side_effect=_make_subprocess_patch(proc),
        ):
            with patch("mcp_servers.git.server.shutil.which", return_value="/usr/bin/gh"):
                server = GitServer()
                result = await server.open_pr(
                    repo_path=str(tmp_path),
                    branch="feature/test",
                    title="Add x",
                    body="body",
                )
        assert result.pr_number == 42
        assert "pull/42" in result.pr_url
        assert result.branch == "feature/test"

    @pytest.mark.asyncio
    async def test_open_pr_gh_not_installed(self, tmp_path: Path) -> None:
        with patch("mcp_servers.git.server.shutil.which", return_value=None):
            server = GitServer()
            with pytest.raises(FileNotFoundError, match="gh CLI not installed"):
                await server.open_pr(
                    repo_path=str(tmp_path),
                    branch="feature/test",
                    title="x",
                    body="y",
                )

    @pytest.mark.asyncio
    async def test_open_pr_with_labels(self, tmp_path: Path) -> None:
        proc = _FakeProc(
            returncode=0,
            stdout=b"https://github.com/owner/repo/pull/1\n",
            stderr=b"",
        )
        captured_args: list[list[str]] = []

        async def _fake(*args: Any, **kwargs: Any) -> _FakeProc:
            captured_args.append(list(args))
            return proc

        with patch(
            "mcp_servers.git.server.asyncio.create_subprocess_exec", side_effect=_fake
        ):
            with patch("mcp_servers.git.server.shutil.which", return_value="/usr/bin/gh"):
                server = GitServer()
                await server.open_pr(
                    repo_path=str(tmp_path),
                    branch="feature/test",
                    title="x",
                    body="y",
                    labels=["bug", "priority"],
                )
        # Проверяем, что --label передан для каждого label.
        flat = captured_args[0]
        assert "--label" in flat
        # Должно быть 2 вхождения --label.
        assert flat.count("--label") == 2
        assert "bug" in flat
        assert "priority" in flat

    @pytest.mark.asyncio
    async def test_open_pr_gh_error(self, tmp_path: Path) -> None:
        proc = _FakeProc(returncode=1, stdout=b"", stderr=b"error: not authenticated")
        with patch(
            "mcp_servers.git.server.asyncio.create_subprocess_exec",
            side_effect=_make_subprocess_patch(proc),
        ):
            with patch("mcp_servers.git.server.shutil.which", return_value="/usr/bin/gh"):
                server = GitServer()
                with pytest.raises(GitCommandError, match="gh pr create"):
                    await server.open_pr(
                        repo_path=str(tmp_path),
                        branch="feature/test",
                        title="x",
                        body="y",
                    )


# ─── diff ────────────────────────────────────────────────────────────────────


class TestDiff:
    @pytest.mark.asyncio
    async def test_diff_happy_path(self, tmp_path: Path) -> None:
        # git diff → ok (clean); git diff --stat → stats.
        diff_output = "+Функция МояФункция()\n+    Возврат 1;\n+КонецФункции"
        stat_output = " src/x.bsl | 3 ++\n 1 file changed, 3 insertions(+)"
        procs = [
            _FakeProc(returncode=0, stdout=diff_output.encode(), stderr=b""),
            _FakeProc(returncode=0, stdout=stat_output.encode(), stderr=b""),
        ]
        call_count = 0

        async def _fake(*args: Any, **kwargs: Any) -> _FakeProc:
            nonlocal call_count
            proc = procs[call_count]
            call_count += 1
            return proc

        with patch(
            "mcp_servers.git.server.asyncio.create_subprocess_exec", side_effect=_fake
        ):
            server = GitServer()
            result = await server.diff(
                repo_path=str(tmp_path),
                branch_a="main",
                branch_b="feature/test",
            )
        assert "МояФункция" in result.diff
        assert result.stats == {"files_changed": 1, "insertions": 3, "deletions": 0}

    @pytest.mark.asyncio
    async def test_diff_secret_detected(self, tmp_path: Path) -> None:
        secret_diff = (
            "+TOKEN = 'github_pat_11CGTUK6Y0EDoe3IIuCHyF_test_secret_here'"
        )
        proc = _FakeProc(returncode=0, stdout=secret_diff.encode(), stderr=b"")
        with patch(
            "mcp_servers.git.server.asyncio.create_subprocess_exec",
            side_effect=_make_subprocess_patch(proc),
        ):
            server = GitServer()
            with pytest.raises(SecretDetectedError) as exc_info:
                await server.diff(
                    repo_path=str(tmp_path),
                    branch_a="main",
                    branch_b="feature/test",
                )
        assert "github_pat" in exc_info.value.pattern_name

    @pytest.mark.asyncio
    async def test_diff_with_paths(self, tmp_path: Path) -> None:
        diff_output = "+x"
        proc = _FakeProc(returncode=0, stdout=diff_output.encode(), stderr=b"")
        captured: list[list[str]] = []

        async def _fake(*args: Any, **kwargs: Any) -> _FakeProc:
            captured.append(list(args))
            return proc

        with patch(
            "mcp_servers.git.server.asyncio.create_subprocess_exec", side_effect=_fake
        ):
            server = GitServer()
            await server.diff(
                repo_path=str(tmp_path),
                branch_a="main",
                branch_b="feature/test",
                paths=["src/x.bsl"],
            )
        # Первая команда — git diff main..feature/test -- src/x.bsl.
        first_cmd = captured[0]
        assert "main..feature/test" in first_cmd
        assert "--" in first_cmd
        assert "src/x.bsl" in first_cmd

    @pytest.mark.asyncio
    async def test_diff_invalid_branch(self, tmp_path: Path) -> None:
        server = GitServer()
        with pytest.raises(GitValidationError):
            await server.diff(
                repo_path=str(tmp_path),
                branch_a="-bad",
                branch_b="feature/test",
            )


# ─── Timeout ─────────────────────────────────────────────────────────────────


class TestTimeout:
    @pytest.mark.asyncio
    async def test_subprocess_timeout(self, tmp_path: Path) -> None:
        # proc с задержкой > timeout.
        proc = _FakeProc(returncode=0, stdout=b"main\n", stderr=b"", delay=2.0)
        with patch(
            "mcp_servers.git.server.asyncio.create_subprocess_exec",
            side_effect=_make_subprocess_patch(proc),
        ):
            server = GitServer(default_timeout=1)
            with pytest.raises(GitTimeoutError, match="timed out"):
                await server.create_branch(
                    repo_path=str(tmp_path), branch_name="feature/test"
                )


# ─── Tool Implementations ────────────────────────────────────────────────────


class TestImplementations:
    """Обёртки CreateBranchImplementation / etc."""

    @pytest.mark.asyncio
    async def test_create_branch_implementation(self, tmp_path: Path) -> None:
        proc1 = _FakeProc(returncode=0, stdout=b"main\n", stderr=b"")
        proc2 = _FakeProc(returncode=0, stdout=b"", stderr=b"")
        call_count = 0

        async def _fake(*args: Any, **kwargs: Any) -> _FakeProc:
            nonlocal call_count
            call_count += 1
            return proc1 if call_count == 1 else proc2

        with patch(
            "mcp_servers.git.server.asyncio.create_subprocess_exec", side_effect=_fake
        ):
            impl = CreateBranchImplementation()
            result = await impl(
                repo_path=str(tmp_path),
                branch_name="feature/test",
            )
        assert result["branch_name"] == "feature/test"
        assert result["base"] == "main"

    @pytest.mark.asyncio
    async def test_commit_implementation_validates_input(self) -> None:
        impl = CommitImplementation()
        # Pydantic принимает пустые message/files; валидация в GitServer.commit.
        with pytest.raises(GitValidationError, match="message cannot be empty"):
            await impl(repo_path="/tmp", message="", files=[])

    @pytest.mark.asyncio
    async def test_diff_implementation_secret_detection(self, tmp_path: Path) -> None:
        secret_diff = "+AKIAIOSFODNN7EXAMPLE"
        proc = _FakeProc(returncode=0, stdout=secret_diff.encode(), stderr=b"")
        # diff вызывает subprocess дважды (diff + stat), но secret detect падает на первом.
        with patch(
            "mcp_servers.git.server.asyncio.create_subprocess_exec",
            side_effect=_make_subprocess_patch(proc),
        ):
            impl = DiffImplementation()
            with pytest.raises(SecretDetectedError):
                await impl(
                    repo_path=str(tmp_path),
                    branch_a="main",
                    branch_b="feature/test",
                )


# ─── Integration (skip-if TEST_GIT_REPO not set) ────────────────────────────


@pytest.mark.skipif(
    "not os.environ.get('TEST_GIT_REPO')",
    reason="TEST_GIT_REPO not set; requires a real git repo path",
)
class TestGitIntegration:
    """Integration с реальным git репозиторием.

    Запуск::

        TEST_GIT_REPO=/path/to/repo uv run pytest \\
            tests/mcp_servers/test_git_server.py::TestGitIntegration -v
    """

    @pytest.mark.asyncio
    async def test_create_branch_and_diff_roundtrip(self) -> None:
        repo = os.environ["TEST_GIT_REPO"]
        server = GitServer()

        # Создаём ветку.
        result = await server.create_branch(repo_path=repo, branch_name="test-facade-tmp")
        assert result.branch_name == "test-facade-tmp"
        assert result.base  # base не пустой

        # Возвращаемся на base и удаляем ветку (cleanup).
        await server._run_subprocess(["git", "checkout", result.base], cwd=Path(repo).resolve())
        await server._run_subprocess(
            ["git", "branch", "-D", "test-facade-tmp"], cwd=Path(repo).resolve()
        )
