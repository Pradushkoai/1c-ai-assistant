"""mcp_servers.git — git operations (4 tools).

Контракты: CreateBranch, Commit, OpenPr, Diff.
Реализация: GitServer — subprocess git/gh CLI.
"""

from __future__ import annotations

from .contracts import GIT_TOOLS
from .server import (
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

__all__ = [
    "GIT_TOOLS",
    "GitServer",
    # Tool implementations
    "CreateBranchImplementation",
    "CommitImplementation",
    "OpenPrImplementation",
    "DiffImplementation",
    # Errors
    "GitValidationError",
    "GitCommandError",
    "GitTimeoutError",
    "SecretDetectedError",
]
