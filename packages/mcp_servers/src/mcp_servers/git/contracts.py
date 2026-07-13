"""git-server: git operations.

Рантайм: Python + git CLI (subprocess)
Stateless

См. ADR-0010 (MCP tool contracts).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ─── Inputs ──────────────────────────────────────────────────────────────────


class CreateBranchInput(BaseModel):
    """Input для git.create_branch."""

    repo_path: str
    branch_name: str = Field(description="feature/add-posting-handler-для-реализации")


class CommitInput(BaseModel):
    """Input для git.commit."""

    repo_path: str
    message: str = Field(description="feat(Реализация): add posting handler")
    files: list[str] = Field(description="Пути относительно repo_path")
    branch: str | None = None  # None = current


class OpenPrInput(BaseModel):
    """Input для git.open_pr."""

    repo_path: str
    branch: str
    title: str
    body: str
    base: str = "main"
    labels: list[str] = Field(default_factory=list)


class DiffInput(BaseModel):
    """Input для git.diff."""

    repo_path: str
    branch_a: str
    branch_b: str
    paths: list[str] | None = None


# ─── Outputs ─────────────────────────────────────────────────────────────────


class CreateBranchOutput(BaseModel):
    """Output для git.create_branch."""

    branch_name: str
    base: str


class CommitOutput(BaseModel):
    """Output для git.commit."""

    commit_sha: str
    files_changed: list[str]


class OpenPrOutput(BaseModel):
    """Output для git.open_pr."""

    pr_number: int
    pr_url: str
    branch: str


class DiffOutput(BaseModel):
    """Output для git.diff."""

    diff: str
    stats: dict[str, int]


# ─── Tool contracts ──────────────────────────────────────────────────────────


class CreateBranch:
    """git.create_branch — создать ветку."""

    name: str = "git.create_branch"
    description: str = "Создать ветку в репозитории."
    input_schema: dict[str, Any] = CreateBranchInput.model_json_schema()
    output_model: type[BaseModel] = CreateBranchOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "exception"
    timeout: int = 10
    idempotent: bool = False
    required_role: str = "COMMITTER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("git.create_branch — вызовите через CreateBranchImplementation")


class Commit:
    """git.commit — закоммитить файлы."""

    name: str = "git.commit"
    description: str = "Закоммитить файлы в текущей (или указанной) ветке."
    input_schema: dict[str, Any] = CommitInput.model_json_schema()
    output_model: type[BaseModel] = CommitOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "exception"
    timeout: int = 15
    idempotent: bool = False
    required_role: str = "COMMITTER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("git.commit — вызовите через CommitImplementation")


class OpenPr:
    """git.open_pr — открыть Pull Request."""

    name: str = "git.open_pr"
    description: str = "Открыть Pull Request через `gh` CLI."
    input_schema: dict[str, Any] = OpenPrInput.model_json_schema()
    output_model: type[BaseModel] = OpenPrOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "exception"
    timeout: int = 30
    idempotent: bool = False
    required_role: str = "COMMITTER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("git.open_pr — вызовите через OpenPrImplementation")


class Diff:
    """git.diff — получить diff между ветками."""

    name: str = "git.diff"
    description: str = "Получить diff между двумя ветками."
    input_schema: dict[str, Any] = DiffInput.model_json_schema()
    output_model: type[BaseModel] = DiffOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "exception"
    timeout: int = 10
    idempotent: bool = True
    required_role: str = "COMMITTER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("git.diff — вызовите через DiffImplementation")


GIT_TOOLS: list[type[Any]] = [CreateBranch, Commit, OpenPr, Diff]
