"""tests/integration/conftest.py — fixtures для integration tests (TD-S6-04).

Все fixtures skip'аются если соответствующий env var не задан.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(scope="session")
def postgres_dsn() -> str | None:
    """DSN для реального Postgres (env TEST_POSTGRES_DSN)."""
    return os.environ.get("TEST_POSTGRES_DSN")


@pytest.fixture(scope="session")
def bsl_ls_url() -> str | None:
    """URL BSL LS HTTP server (env BSL_LS_HTTP_URL)."""
    return os.environ.get("BSL_LS_HTTP_URL")


@pytest.fixture(scope="session")
def git_repo_path() -> str | None:
    """Путь к git-репозиторию (env TEST_GIT_REPO)."""
    return os.environ.get("TEST_GIT_REPO")


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Создать временный git-репозиторий для тестов (init + initial commit)."""
    import subprocess

    repo = tmp_path / "test-repo"
    repo.mkdir()
    # git init + initial commit (нужен user.name/email для commit).
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    # Initial commit (empty).
    (repo / "README.md").write_text("# Test repo", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo
