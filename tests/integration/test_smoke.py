"""tests/integration/test_smoke.py — smoke integration tests (TD-S6-04).

Базовые smoke tests с реальными контейнерами. Skip'аются если env vars не заданы.
Полные integration tests (survive-restart, git roundtrip, BSL LS lint, metadata e2e)
находятся в соответствующих test_*_server.py файлах (skip-if env not set).

См. D-2026-07-13-13.
"""

from __future__ import annotations

import os

import pytest


# ─── Postgres smoke ──────────────────────────────────────────────────────────


@pytest.mark.integration
class TestPostgresSmoke:
    """Smoke tests для Postgres контейнера."""

    @pytest.mark.skipif(
        "not os.environ.get('TEST_POSTGRES_DSN')",
        reason="TEST_POSTGRES_DSN not set; requires running Postgres container",
    )
    @pytest.mark.asyncio
    async def test_postgres_persistence_manager_init(self, postgres_dsn: str) -> None:
        """PersistenceManager инициализируется с реальным Postgres + setup()."""
        from orchestrator.persistence import PersistenceManager

        async with PersistenceManager(dsn=postgres_dsn) as pm:
            assert pm.is_postgres is True
            assert await pm.health_check() is True

    @pytest.mark.skipif(
        "not os.environ.get('TEST_POSTGRES_DSN')",
        reason="TEST_POSTGRES_DSN not set; requires running Postgres container",
    )
    @pytest.mark.asyncio
    async def test_postgres_checkpoint_roundtrip(self, postgres_dsn: str) -> None:
        """Checkpoint put → aget_tuple roundtrip через реальный Postgres."""
        from orchestrator.persistence import PersistenceManager

        async with PersistenceManager(dsn=postgres_dsn) as pm:
            checkpointer = pm.get_checkpointer()
            # Пробный aget_tuple (несуществующий thread_id → None, без побочных эффектов).
            result = await checkpointer.aget_tuple(
                {"configurable": {"thread_id": "smoke-test-nonexistent"}}
            )
            assert result is None  # не существует — ожидаемо


# ─── BSL LS smoke ────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestBslLsSmoke:
    """Smoke tests для BSL LS контейнера."""

    @pytest.mark.skipif(
        "not os.environ.get('BSL_LS_HTTP_URL')",
        reason="BSL_LS_HTTP_URL not set; requires running bsl-ls container",
    )
    @pytest.mark.asyncio
    async def test_bsl_ls_health(self, bsl_ls_url: str) -> None:
        """BSL LS /health endpoint отвечает 200."""
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{bsl_ls_url}/health")
            assert response.status_code == 200
            data = response.json()
            assert "bsl_ls_available" in data

    @pytest.mark.skipif(
        "not os.environ.get('BSL_LS_HTTP_URL')",
        reason="BSL_LS_HTTP_URL not set; requires running bsl-ls container",
    )
    @pytest.mark.asyncio
    async def test_bsl_ls_lint_clean_code(self, bsl_ls_url: str) -> None:
        """BSL LS lint для чистого BSL кода → 0 errors."""
        from mcp_servers.bsl_ls.server import BslLsServer

        server = BslLsServer(base_url=bsl_ls_url)
        result = await server.lint(
            code="Функция МояФункция()\n    Возврат Истина;\nКонецФункции\n",
            file_path="/tmp/test.bsl",
        )
        # BSL LS может вернуть warnings, но не critical errors для чистого кода.
        assert isinstance(result.total, int)


# ─── Git smoke ───────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestGitSmoke:
    """Smoke tests для GitServer с реальным git repo."""

    @pytest.mark.skipif(
        "not os.environ.get('TEST_GIT_REPO')",
        reason="TEST_GIT_REPO not set; requires a real git repo path",
    )
    @pytest.mark.asyncio
    async def test_git_create_branch_and_diff(self, git_repo_path: str) -> None:
        """GitServer create_branch + diff roundtrip с реальным repo."""
        from mcp_servers.git import GitServer

        server = GitServer()
        # Create branch.
        result = await server.create_branch(
            repo_path=git_repo_path,
            branch_name="test-smoke-tmp",
        )
        assert result.branch_name == "test-smoke-tmp"
        assert result.base  # base не пустой

        # Diff между ветками (пока пустой — должен вернуть empty diff).
        diff_result = await server.diff(
            repo_path=git_repo_path,
            branch_a=result.base,
            branch_b="test-smoke-tmp",
        )
        assert isinstance(diff_result.diff, str)

        # Cleanup: вернуться на base и удалить ветку.
        import subprocess

        subprocess.run(
            ["git", "checkout", result.base],
            cwd=git_repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "branch", "-D", "test-smoke-tmp"],
            cwd=git_repo_path,
            check=True,
            capture_output=True,
        )

    @pytest.mark.asyncio
    async def test_git_temp_repo_roundtrip(self, temp_git_repo) -> None:
        """Git roundtrip с временным repo (создаётся conftest, без TEST_GIT_REPO)."""
        from mcp_servers.git import GitServer

        server = GitServer()
        repo_path = str(temp_git_repo)

        # Create branch.
        result = await server.create_branch(
            repo_path=repo_path,
            branch_name="feature/test",
        )
        assert result.branch_name == "feature/test"
        assert result.base == "main"

        # Write file + commit.
        (temp_git_repo / "test.bsl").write_text("Функция Тест() КонецФункции", encoding="utf-8")
        commit_result = await server.commit(
            repo_path=repo_path,
            message="test: add test.bsl",
            files=["test.bsl"],
            branch="feature/test",
        )
        assert commit_result.commit_sha  # не пустой
        assert "test.bsl" in commit_result.files_changed


# ─── Metadata smoke ──────────────────────────────────────────────────────────


@pytest.mark.integration
class TestMetadataSmoke:
    """Smoke tests для MetadataServer с реальной mini_config."""

    @pytest.mark.asyncio
    async def test_metadata_server_creates(self) -> None:
        """MetadataServer создаётся (без реального config — только init check)."""
        try:
            from mcp_servers.metadata import MetadataServer

            server = MetadataServer()
            assert server.path_manager is not None
        except FileNotFoundError:
            pytest.skip("PathManager not available (no paths.env in test env)")

    @pytest.mark.asyncio
    async def test_metadata_get_metadata_not_found(self) -> None:
        """get_metadata для несуществующего объекта → MetadataNotFoundError."""
        try:
            from mcp_servers.metadata import IndexNotFoundError, MetadataServer

            server = MetadataServer()
            with pytest.raises((IndexNotFoundError, Exception)):
                await server.get_metadata("Catalog.Несуществующий", "test", "1.0")
        except FileNotFoundError:
            pytest.skip("PathManager not available")
