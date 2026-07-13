"""tests/agent/test_cli_health.py — `1c-ai health` команда (TD-S5-04).

Покрытие:
- MemorySaver (no DATABASE_URL) → status=ok, exit 0.
- PostgresSaver health_check True → status=ok, exit 0.
- PostgresSaver health_check False → status=failed, exit 1.
- PersistenceError → status=failed, exit 1.
- BSL LS HTTP 200 → status=ok.
- BSL LS HTTP 500 → status=failed.
- BSL LS not set → skipped.
- JSON output format.
- `1c-ai health` CLI registration (click runner).

См. ADR-0015, D-2026-07-13-04, D-2026-07-13-09.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── cmd_health unit tests ───────────────────────────────────────────────────


class TestCmdHealth:
    """Прямые тесты cmd_health() (sync — вызывает asyncio.run внутри)."""

    def test_memory_saver_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Без DATABASE_URL — MemorySaver, status=ok."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("BSL_LS_HTTP_URL", raising=False)

        from agent.cli_commands.health import cmd_health

        exit_code = cmd_health()
        assert exit_code == 0

    def test_postgres_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PostgresSaver health_check True → status=ok, exit 0."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://agent:agent@host:5432/db")
        monkeypatch.delenv("BSL_LS_HTTP_URL", raising=False)

        mock_pm = MagicMock()
        mock_pm.is_postgres = True
        mock_pm.health_check = AsyncMock(return_value=True)

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_pm)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("orchestrator.persistence.PersistenceManager.from_env", return_value=mock_cm):
            from agent.cli_commands.health import cmd_health

            exit_code = cmd_health()
        assert exit_code == 0

    def test_postgres_health_check_failed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PostgresSaver health_check False → status=failed, exit 1."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://agent:agent@host:5432/db")
        monkeypatch.delenv("BSL_LS_HTTP_URL", raising=False)

        mock_pm = MagicMock()
        mock_pm.is_postgres = True
        mock_pm.health_check = AsyncMock(return_value=False)

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_pm)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("orchestrator.persistence.PersistenceManager.from_env", return_value=mock_cm):
            from agent.cli_commands.health import cmd_health

            exit_code = cmd_health()
        assert exit_code == 1

    def test_persistence_error_exit_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PersistenceError при инициализации → status=failed, exit 1."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://agent:agent@bad:5432/db")
        monkeypatch.delenv("BSL_LS_HTTP_URL", raising=False)

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(side_effect=Exception("Cannot connect"))
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("orchestrator.persistence.PersistenceManager.from_env", return_value=mock_cm):
            from agent.cli_commands.health import cmd_health

            exit_code = cmd_health()
        assert exit_code == 1

    def test_bsl_ls_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """BSL LS HTTP 200 → status=ok."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("BSL_LS_HTTP_URL", "http://1c-ai-bsl-ls:8080")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"bsl_ls_available": True}

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            from agent.cli_commands.health import cmd_health

            exit_code = cmd_health()
        assert exit_code == 0

    def test_bsl_ls_http_500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """BSL LS HTTP 500 → status=failed, exit 1."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("BSL_LS_HTTP_URL", "http://1c-ai-bsl-ls:8080")

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            from agent.cli_commands.health import cmd_health

            exit_code = cmd_health()
        assert exit_code == 1

    def test_bsl_ls_connection_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """BSL LS connection error → status=failed, exit 1."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("BSL_LS_HTTP_URL", "http://1c-ai-bsl-ls:8080")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            from agent.cli_commands.health import cmd_health

            exit_code = cmd_health()
        assert exit_code == 1

    def test_bsl_ls_skipped_when_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """BSL_LS_HTTP_URL не задан → bsl_ls skipped, persistence ok → exit 0."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("BSL_LS_HTTP_URL", raising=False)

        from agent.cli_commands.health import cmd_health

        exit_code = cmd_health()
        assert exit_code == 0


# ─── JSON output format ──────────────────────────────────────────────────────


class TestHealthJsonOutput:
    """Проверка JSON формата вывода (sync тесты)."""

    def test_json_output_structure(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
        """JSON output содержит status + checks {persistence, bsl_ls}."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("BSL_LS_HTTP_URL", raising=False)

        from agent.cli_commands.health import cmd_health

        exit_code = cmd_health()
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert "status" in data
        assert "checks" in data
        assert "persistence" in data["checks"]
        assert "bsl_ls" in data["checks"]
        assert data["status"] == "ok"
        assert data["checks"]["persistence"]["status"] == "ok"
        assert data["checks"]["persistence"]["type"] == "memory"
        assert data["checks"]["bsl_ls"]["status"] == "skipped"
        assert exit_code == 0

    def test_json_output_failed(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
        """Failed persistence → JSON содержит error."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://agent:agent@bad:5432/db")
        monkeypatch.delenv("BSL_LS_HTTP_URL", raising=False)

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(side_effect=RuntimeError("conn refused"))
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("orchestrator.persistence.PersistenceManager.from_env", return_value=mock_cm):
            from agent.cli_commands.health import cmd_health

            exit_code = cmd_health()
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert data["status"] == "failed"
        assert data["checks"]["persistence"]["status"] == "failed"
        assert "error" in data["checks"]["persistence"]
        assert "RuntimeError" in data["checks"]["persistence"]["error"]
        assert exit_code == 1


# ─── CLI registration ────────────────────────────────────────────────────────


class TestHealthCliRegistration:
    """`1c-ai health` зарегистрирована в CLI."""

    def test_health_command_exists(self) -> None:
        """Команда health есть в CLI."""
        from agent.cli import main

        # click Group имеет command 'health'.
        assert "health" in main.commands

    def test_health_command_help(self) -> None:
        """--help показывает health."""
        from click.testing import CliRunner

        from agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "health" in result.output

    def test_health_command_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`1c-ai health` выполняется (MemorySaver, exit 0)."""
        from click.testing import CliRunner

        from agent.cli import main

        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("BSL_LS_HTTP_URL", raising=False)

        runner = CliRunner()
        result = runner.invoke(main, ["health"])
        assert result.exit_code == 0
        # JSON output.
        assert '"status": "ok"' in result.output


# ─── _mask_dsn ───────────────────────────────────────────────────────────────


class TestMaskDsn:
    """Маскирование DSN для логов."""

    def test_masks_password(self) -> None:
        from agent.cli_commands.health import _mask_dsn

        assert _mask_dsn("postgresql://agent:secret@host:5432/db") == "postgresql://agent:***@host:5432/db"

    def test_no_password_unchanged(self) -> None:
        from agent.cli_commands.health import _mask_dsn

        assert _mask_dsn("postgresql://host:5432/db") == "postgresql://host:5432/db"

    def test_empty(self) -> None:
        from agent.cli_commands.health import _mask_dsn

        assert _mask_dsn("") == ""
