"""GitServer — реализация 4 git MCP tools (TD-S5-03).

4 tools (ADR-0010):
1. create_branch — git checkout -b <branch>
2. commit — git add <files> + git commit -m <message>
3. open_pr — gh pr create (через gh CLI)
4. diff — git diff <a>..<b> -- <paths> (с проверкой на secrets)

Безопасность:
- Branch name validation (git ref naming rules, no shell injection).
- repo_path validation (exists, is dir).
- Relative paths validation для commit files (no absolute, no `..` traversal).
- Secrets scan в diff выводе (github_pat_*, AKIA*, bearer tokens, private keys).
- subprocess с shell=False (явные args list — нет shell-инъекций).

См. ADR-0010 (MCP tool contracts), ADR-0003 (MCP-архитектура), D-2026-07-13-08.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from pathlib import Path
from typing import Any

from .contracts import (
    CommitInput,
    CommitOutput,
    CreateBranchInput,
    CreateBranchOutput,
    DiffInput,
    DiffOutput,
    OpenPrInput,
    OpenPrOutput,
)

log = logging.getLogger(__name__)

# ─── Security: validations ───────────────────────────────────────────────────

# Git ref naming rules: не начинается с `-`, не содержит `..`, `:`, `~`, `^`,
# control chars, space. Длина ≤ 200.
_BRANCH_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,199}$")

# Secret patterns для diff scan. Regex-based — базовая защита, не идеально.
_SECRET_PATTERNS = [
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),  # GitHub fine-grained PAT
    re.compile(r"ghp_[A-Za-z0-9]{36}"),  # GitHub classic PAT
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),  # private keys
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}", re.IGNORECASE),  # bearer tokens
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),  # Slack tokens
]


class GitValidationError(ValueError):
    """Невалидный input (branch name, path, etc.)."""


class SecretDetectedError(RuntimeError):
    """В diff обнаружен секрет — операция ABORTed."""

    def __init__(self, pattern_name: str, snippet: str) -> None:
        super().__init__(f"Secret detected in diff (pattern: {pattern_name}). Snippet (masked): {snippet[:40]!r}...")
        self.pattern_name = pattern_name
        self.snippet = snippet


class GitTimeoutError(RuntimeError):
    """Subprocess git/gh превысил timeout."""


class GitCommandError(RuntimeError):
    """git/gh subprocess вернул non-zero exit code."""

    def __init__(self, cmd: str, returncode: int, stderr: str) -> None:
        super().__init__(f"git command failed: {cmd!r} (exit {returncode}): {stderr.strip()[:200]}")
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr


def _validate_branch_name(branch_name: str) -> None:
    """Валидация имени ветки по git ref naming rules.

    Raises:
        GitValidationError: если имя невалидно.
    """
    if not branch_name:
        raise GitValidationError("branch_name cannot be empty")
    if not _BRANCH_NAME_RE.match(branch_name):
        raise GitValidationError(
            f"Invalid branch_name: {branch_name!r}. Must match "
            "^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,199}$ (no leading '-', no '..' etc.)."
        )
    if ".." in branch_name:
        raise GitValidationError(f"branch_name contains '..': {branch_name!r}")


def _validate_repo_path(repo_path: str) -> Path:
    """Валидация пути репозитория. Возвращает resolved Path.

    Raises:
        GitValidationError: если путь не существует или не директория.
    """
    if not repo_path:
        raise GitValidationError("repo_path cannot be empty")
    p = Path(repo_path).resolve()
    if not p.exists():
        raise GitValidationError(f"repo_path does not exist: {p}")
    if not p.is_dir():
        raise GitValidationError(f"repo_path is not a directory: {p}")
    return p


def _validate_relative_paths(files: list[str]) -> None:
    """Валидация, что пути относительные и без `..` traversal.

    Raises:
        GitValidationError: если путь абсолютный или содержит `..`.
    """
    for f in files:
        if not f:
            raise GitValidationError("empty file path in files[]")
        if Path(f).is_absolute():
            raise GitValidationError(f"absolute path not allowed: {f!r}")
        if ".." in Path(f).parts:
            raise GitValidationError(f"'..' traversal not allowed: {f!r}")


def _scan_diff_for_secrets(diff_output: str) -> None:
    """Сканировать diff вывод на secrets.

    Raises:
        SecretDetectedError: если найден секрет.
    """
    for pattern in _SECRET_PATTERNS:
        match = pattern.search(diff_output)
        if match:
            # Mask snippet для error message.
            snippet = match.group(0)
            masked = snippet[:8] + "***" + snippet[-4:] if len(snippet) > 12 else "***"
            pattern_name = pattern.pattern[:50]
            raise SecretDetectedError(pattern_name=pattern_name, snippet=masked)


# ─── GitServer ───────────────────────────────────────────────────────────────


class GitServer:
    """Реализация 4 git MCP tools через subprocess.

    Attributes:
        default_timeout: timeout для subprocess (секунды).
    """

    def __init__(self, default_timeout: int = 30) -> None:
        self.default_timeout = default_timeout

    async def _run_subprocess(
        self,
        args: list[str],
        cwd: Path,
        timeout: int | None = None,
    ) -> tuple[int, str, str]:
        """Запустить subprocess (shell=False) и вернуть (returncode, stdout, stderr).

        Raises:
            GitTimeoutError: при timeout.
            FileNotFoundError: если executable не найден.
        """
        log.info("git_subprocess: %s (cwd=%s)", args[0] + " " + " ".join(args[1:]), cwd)
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout or self.default_timeout)
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise GitTimeoutError(f"subprocess timed out after {timeout or self.default_timeout}s: {args[0]}") from exc
        return (
            proc.returncode or 0,
            stdout_b.decode("utf-8", errors="replace"),
            stderr_b.decode("utf-8", errors="replace"),
        )

    # ─── 1. create_branch ────────────────────────────────────────────────────

    async def create_branch(
        self,
        repo_path: str,
        branch_name: str,
    ) -> CreateBranchOutput:
        """Создать ветку в репозитории.

        Args:
            repo_path: путь к git-репозиторию.
            branch_name: имя новой ветки (validated).

        Returns:
            CreateBranchOutput с именем ветки и base.

        Raises:
            GitValidationError: невалидный input.
            GitCommandError: git вернул ошибку.
        """
        _validate_branch_name(branch_name)
        cwd = _validate_repo_path(repo_path)

        # Получаем текущую ветку (base).
        rc, stdout, stderr = await self._run_subprocess(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
        if rc != 0:
            raise GitCommandError("git rev-parse", rc, stderr)
        base = stdout.strip()

        # Создаём ветку.
        rc, _, stderr = await self._run_subprocess(["git", "checkout", "-b", branch_name], cwd=cwd)
        if rc != 0:
            raise GitCommandError("git checkout -b", rc, stderr)

        return CreateBranchOutput(branch_name=branch_name, base=base)

    # ─── 2. commit ───────────────────────────────────────────────────────────

    async def commit(
        self,
        repo_path: str,
        message: str,
        files: list[str],
        branch: str | None = None,
    ) -> CommitOutput:
        """Закоммитить файлы в текущей (или указанной) ветке.

        Args:
            repo_path: путь к git-репозиторию.
            message: commit message.
            files: пути файлов относительно repo_path.
            branch: целевая ветка (None = current).

        Returns:
            CommitOutput с commit_sha и files_changed.

        Raises:
            GitValidationError: невалидный input.
            GitCommandError: git вернул ошибку.
        """
        if not message:
            raise GitValidationError("message cannot be empty")
        if not files:
            raise GitValidationError("files cannot be empty")
        _validate_relative_paths(files)
        cwd = _validate_repo_path(repo_path)

        # Переключаемся на ветку, если указана.
        if branch is not None:
            _validate_branch_name(branch)
            rc, _, stderr = await self._run_subprocess(["git", "checkout", branch], cwd=cwd)
            if rc != 0:
                raise GitCommandError("git checkout", rc, stderr)

        # git add <files>.
        rc, _, stderr = await self._run_subprocess(["git", "add", "--", *files], cwd=cwd)
        if rc != 0:
            raise GitCommandError("git add", rc, stderr)

        # git commit -m <message>.
        rc, _, stderr = await self._run_subprocess(["git", "commit", "-m", message], cwd=cwd)
        if rc != 0:
            raise GitCommandError("git commit", rc, stderr)

        # Получаем commit SHA.
        rc, stdout, stderr = await self._run_subprocess(["git", "rev-parse", "HEAD"], cwd=cwd)
        if rc != 0:
            raise GitCommandError("git rev-parse HEAD", rc, stderr)
        commit_sha = stdout.strip()

        return CommitOutput(commit_sha=commit_sha, files_changed=files)

    # ─── 3. open_pr ──────────────────────────────────────────────────────────

    async def open_pr(
        self,
        repo_path: str,
        branch: str,
        title: str,
        body: str,
        base: str = "main",
        labels: list[str] | None = None,
    ) -> OpenPrOutput:
        """Открыть Pull Request через `gh` CLI.

        Args:
            repo_path: путь к git-репозиторию.
            branch: head-ветка (feature).
            title: PR title.
            body: PR body.
            base: base-ветка (по умолчанию 'main').
            labels: список label'ов.

        Returns:
            OpenPrOutput с pr_number, pr_url, branch.

        Raises:
            GitValidationError: невалидный input.
            FileNotFoundError: gh CLI не установлен.
            GitCommandError: gh вернул ошибку.
        """
        _validate_branch_name(branch)
        _validate_branch_name(base)
        if not title:
            raise GitValidationError("title cannot be empty")
        cwd = _validate_repo_path(repo_path)

        # Проверяем, что gh установлен.
        if shutil.which("gh") is None:
            raise FileNotFoundError(
                "gh CLI not installed. Install: https://cli.github.com/. "
                "Auth: `gh auth login` или установите GH_TOKEN env var."
            )

        # gh pr create --base <base> --head <branch> --title <title> --body <body> --label <l> ...
        args = [
            "gh",
            "pr",
            "create",
            "--base",
            base,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ]
        for label in labels or []:
            args.extend(["--label", label])

        rc, stdout, stderr = await self._run_subprocess(args, cwd=cwd, timeout=60)
        if rc != 0:
            raise GitCommandError("gh pr create", rc, stderr)

        # gh pr create выводит URL PR в stdout.
        pr_url = stdout.strip().splitlines()[-1] if stdout.strip() else ""
        # Извлекаем PR number из URL (https://github.com/owner/repo/pull/123).
        pr_number = 0
        match = re.search(r"/pull/(\d+)", pr_url)
        if match:
            pr_number = int(match.group(1))

        return OpenPrOutput(pr_number=pr_number, pr_url=pr_url, branch=branch)

    # ─── 4. diff ─────────────────────────────────────────────────────────────

    async def diff(
        self,
        repo_path: str,
        branch_a: str,
        branch_b: str,
        paths: list[str] | None = None,
    ) -> DiffOutput:
        """Получить diff между двумя ветками (с проверкой на secrets).

        Args:
            repo_path: путь к git-репозиторию.
            branch_a: первая ветка.
            branch_b: вторая ветка.
            paths: ограничить diff конкретными путями (relative).

        Returns:
            DiffOutput с diff-текстом и stats.

        Raises:
            GitValidationError: невалидный input.
            GitCommandError: git вернул ошибку.
            SecretDetectedError: в diff найден секрет.
        """
        _validate_branch_name(branch_a)
        _validate_branch_name(branch_b)
        if paths:
            _validate_relative_paths(paths)
        cwd = _validate_repo_path(repo_path)

        args = ["git", "diff", f"{branch_a}..{branch_b}"]
        if paths:
            args.append("--")
            args.extend(paths)

        rc, stdout, stderr = await self._run_subprocess(args, cwd=cwd)
        if rc != 0:
            raise GitCommandError("git diff", rc, stderr)

        # Скан на secrets перед возвратом.
        _scan_diff_for_secrets(stdout)

        # Получаем stats отдельной командой (короткая, без diff содержимого).
        stats_args = ["git", "diff", "--stat", f"{branch_a}..{branch_b}"]
        if paths:
            stats_args.append("--")
            stats_args.extend(paths)
        rc, stats_stdout, _ = await self._run_subprocess(stats_args, cwd=cwd)
        stats = _parse_diff_stat(stats_stdout) if rc == 0 else {}

        return DiffOutput(diff=stdout, stats=stats)


def _parse_diff_stat(stat_output: str) -> dict[str, int]:
    """Парсить вывод `git diff --stat` в dict {files_changed, insertions, deletions}."""
    # Последняя строка: " 3 files changed, 10 insertions(+), 5 deletions(-)"
    result = {"files_changed": 0, "insertions": 0, "deletions": 0}
    if not stat_output.strip():
        return result
    last_line = stat_output.strip().splitlines()[-1]
    m = re.search(r"(\d+) files? changed", last_line)
    if m:
        result["files_changed"] = int(m.group(1))
    m = re.search(r"(\d+) insertions?\(\+\)", last_line)
    if m:
        result["insertions"] = int(m.group(1))
    m = re.search(r"(\d+) deletions?\(-\)", last_line)
    if m:
        result["deletions"] = int(m.group(1))
    return result


# ─── Tool implementations (для MCP server) ───────────────────────────────────


class CreateBranchImplementation:
    """Реализация git.create_branch tool — обёртка над GitServer.create_branch()."""

    def __init__(self, server: GitServer | None = None) -> None:
        self._server = server or GitServer()

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        input_data = CreateBranchInput.model_validate(kwargs)
        result = await self._server.create_branch(
            repo_path=input_data.repo_path,
            branch_name=input_data.branch_name,
        )
        return result.model_dump()


class CommitImplementation:
    """Реализация git.commit tool — обёртка над GitServer.commit()."""

    def __init__(self, server: GitServer | None = None) -> None:
        self._server = server or GitServer()

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        input_data = CommitInput.model_validate(kwargs)
        result = await self._server.commit(
            repo_path=input_data.repo_path,
            message=input_data.message,
            files=input_data.files,
            branch=input_data.branch,
        )
        return result.model_dump()


class OpenPrImplementation:
    """Реализация git.open_pr tool — обёртка над GitServer.open_pr()."""

    def __init__(self, server: GitServer | None = None) -> None:
        self._server = server or GitServer()

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        input_data = OpenPrInput.model_validate(kwargs)
        result = await self._server.open_pr(
            repo_path=input_data.repo_path,
            branch=input_data.branch,
            title=input_data.title,
            body=input_data.body,
            base=input_data.base,
            labels=input_data.labels,
        )
        return result.model_dump()


class DiffImplementation:
    """Реализация git.diff tool — обёртка над GitServer.diff()."""

    def __init__(self, server: GitServer | None = None) -> None:
        self._server = server or GitServer()

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        input_data = DiffInput.model_validate(kwargs)
        result = await self._server.diff(
            repo_path=input_data.repo_path,
            branch_a=input_data.branch_a,
            branch_b=input_data.branch_b,
            paths=input_data.paths,
        )
        return result.model_dump()
