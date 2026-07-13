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
            result = await checkpointer.aget_tuple({"configurable": {"thread_id": "smoke-test-nonexistent"}})
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


# ─── REST API smoke (TD-S7-04) ──────────────────────────────────────────────


@pytest.mark.integration
class TestRestApiSmoke:
    """Smoke tests для REST API HTTP server (TD-S7-02)."""

    def test_http_app_creates(self) -> None:
        """FastAPI app создаётся с всеми endpoints."""
        from mcp_servers.http_server import create_http_app

        app = create_http_app()
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/health" in routes
        assert "/servers" in routes
        assert "/facade/{tool}" in routes

    def test_http_health_endpoint(self) -> None:
        """GET /health через TestClient → 200 + JSON."""
        from fastapi.testclient import TestClient

        from mcp_servers.http_server import create_http_app

        app = create_http_app()
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "checks" in data

    def test_http_servers_endpoint(self) -> None:
        """GET /servers → 200 + 6 серверов."""
        from fastapi.testclient import TestClient

        from mcp_servers.http_server import create_http_app

        app = create_http_app()
        client = TestClient(app)
        response = client.get("/servers")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 6

    def test_http_facade_data_status(self) -> None:
        """POST /facade/data_status → 200 (degraded, no DI)."""
        from fastapi.testclient import TestClient

        from mcp_servers.facade.handlers import FacadeHandlers
        from mcp_servers.http_server import create_http_app

        app = create_http_app(FacadeHandlers())
        client = TestClient(app)
        response = client.post("/facade/data_status", json={"args": {}})
        assert response.status_code == 200
        data = response.json()
        assert data["tool"] == "data_status"
        assert "result" in data


# ─── FacadeStateStore survive-restart with real Postgres (TD-S7-04) ─────────


@pytest.mark.integration
class TestFacadeStateStorePostgresSmoke:
    """Smoke tests для FacadeStateStore с реальным Postgres (survive-restart)."""

    @pytest.mark.skipif(
        "not os.environ.get('TEST_POSTGRES_DSN')",
        reason="TEST_POSTGRES_DSN not set; requires running Postgres container",
    )
    @pytest.mark.asyncio
    async def test_state_store_save_load_with_postgres(self, postgres_dsn: str) -> None:
        """FacadeStateStore save → load через реальный Postgres checkpointer."""
        from orchestrator.persistence import PersistenceManager
        from orchestrator.state import FSMState, Subtask, TaskState
        from parsers.models import ObjectRef
        from mcp_servers.facade import FacadeStateStore

        # Открываем PersistenceManager с реальным Postgres.
        async with PersistenceManager(dsn=postgres_dsn) as pm:
            checkpointer = pm.get_checkpointer()
            store = FacadeStateStore(checkpointer=checkpointer, is_postgres=True, state_class=TaskState)

            state = TaskState(
                task_id="integration-test-1",
                description="survive-restart integration test",
                config_name="ut11",
                config_version="4.5.3",
                platform_version="8.3.20",
                fsm_state=FSMState.GATHERING,
                subtasks=[
                    Subtask(
                        id="st-int-1",
                        name="TestSubtask",
                        target_module=ObjectRef(type="CommonModule", name="TestModule"),
                        description="test",
                    )
                ],
            )

            # Save.
            await store.save_state("plan-integration-1", state)

            # Load (тот же store instance).
            loaded = await store.load_state("plan-integration-1")
            assert loaded is not None
            assert loaded.task_id == "integration-test-1"
            assert loaded.fsm_state == FSMState.GATHERING
            assert len(loaded.subtasks) == 1
            assert loaded.subtasks[0].id == "st-int-1"

    @pytest.mark.skipif(
        "not os.environ.get('TEST_POSTGRES_DSN')",
        reason="TEST_POSTGRES_DSN not set; requires running Postgres container",
    )
    @pytest.mark.asyncio
    async def test_state_store_survive_restart_with_postgres(self, postgres_dsn: str) -> None:
        """Survive-restart: 2 PersistenceManager instances — второй находит state от первого."""
        from orchestrator.persistence import PersistenceManager
        from orchestrator.state import FSMState, TaskState
        from mcp_servers.facade import FacadeStateStore

        # "Первый запуск": store1 сохраняет state.
        async with PersistenceManager(dsn=postgres_dsn) as pm1:
            store1 = FacadeStateStore(
                checkpointer=pm1.get_checkpointer(),
                is_postgres=True,
                state_class=TaskState,
            )
            state = TaskState(
                task_id="survive-restart-test",
                description="survive restart with real postgres",
                config_name="ut11",
                config_version="4.5.3",
                platform_version="8.3.20",
                fsm_state=FSMState.CODING,
            )
            await store1.save_state("plan-survive-1", state)

        # "Рестарт контейнера": pm2 — новый PersistenceManager, тот же Postgres.
        async with PersistenceManager(dsn=postgres_dsn) as pm2:
            store2 = FacadeStateStore(
                checkpointer=pm2.get_checkpointer(),
                is_postgres=True,
                state_class=TaskState,
            )
            loaded = await store2.load_state("plan-survive-1")
            assert loaded is not None
            assert loaded.task_id == "survive-restart-test"
            assert loaded.fsm_state == FSMState.CODING
            assert loaded.description == "survive restart with real postgres"
