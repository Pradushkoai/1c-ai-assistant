"""tests/agent/test_cli_mcp.py — `1c-ai mcp serve` CLI (TD-S6-03).

Покрытие:
- `1c-ai mcp serve --list` показывает 6 серверов.
- `1c-ai mcp serve --server facade` создаёт Server (mock run).
- `--server unknown` → error (click Choice validation).
- `create_domain_server()` для каждого имени → Server instance.
- `SERVER_NAMES` содержит 6 имён.
- `AVAILABLE_SERVERS` корректные tools counts.
- `list_servers()` format.

См. ADR-0003, D-2026-07-13-12.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner


# ─── server_factory unit tests ───────────────────────────────────────────────


class TestServerFactory:
    """Прямые тесты server_factory."""

    def test_server_names_contains_6(self) -> None:
        from mcp_servers import SERVER_NAMES

        assert frozenset(
            {"facade", "metadata", "codebase", "kb", "bsl_ls", "git"}
        ) == SERVER_NAMES

    def test_available_servers_counts(self) -> None:
        from mcp_servers import AVAILABLE_SERVERS

        assert AVAILABLE_SERVERS == {
            "bsl_ls": 2,
            "codebase": 4,
            "facade": 8,
            "git": 4,
            "kb": 7,
            "metadata": 4,
        }

    def test_list_servers_format(self) -> None:
        from mcp_servers import list_servers

        output = list_servers()
        assert "Available MCP servers:" in output
        assert "facade" in output
        assert "metadata" in output
        assert "tools" in output

    @pytest.mark.parametrize("name", ["facade", "metadata", "codebase", "kb", "bsl_ls", "git"])
    def test_create_domain_server_returns_server(self, name: str) -> None:
        """create_domain_server для каждого имени возвращает Server."""
        from mcp.server import Server

        from mcp_servers import create_domain_server

        server = create_domain_server(name)
        assert isinstance(server, Server)

    def test_create_domain_server_unknown_raises(self) -> None:
        from mcp_servers import create_domain_server

        with pytest.raises(ValueError, match="Unknown server name"):
            create_domain_server("unknown_server")

    def test_create_domain_server_with_handlers_for_facade(self) -> None:
        """facade принимает handlers kwarg."""
        from mcp_servers import create_domain_server
        from mcp_servers.facade import FacadeHandlers

        handlers = FacadeHandlers()
        server = create_domain_server("facade", handlers=handlers)
        from mcp.server import Server

        assert isinstance(server, Server)


# ─── CLI registration tests ──────────────────────────────────────────────────


class TestMcpCliRegistration:
    """`1c-ai mcp` зарегистрирован в CLI."""

    def test_mcp_group_exists(self) -> None:
        from agent.cli import main

        assert "mcp" in main.commands

    def test_mcp_serve_subcommand_exists(self) -> None:
        from agent.cli import main

        mcp_group = main.commands["mcp"]
        assert "serve" in mcp_group.commands

    def test_main_help_shows_mcp(self) -> None:
        from agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "mcp" in result.output

    def test_mcp_help_shows_serve(self) -> None:
        from agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["mcp", "--help"])
        assert result.exit_code == 0
        assert "serve" in result.output


# ─── `1c-ai mcp serve --list` ────────────────────────────────────────────────


class TestMcpServeList:
    def test_list_shows_6_servers(self) -> None:
        from agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["mcp", "serve", "--list"])
        assert result.exit_code == 0
        assert "facade" in result.output
        assert "metadata" in result.output
        assert "codebase" in result.output
        assert "kb" in result.output
        assert "bsl_ls" in result.output
        assert "git" in result.output
        assert "tools" in result.output

    def test_list_shows_tool_counts(self) -> None:
        from agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["mcp", "serve", "--list"])
        assert "8 tools" in result.output  # facade
        assert "4 tools" in result.output  # metadata/codebase/git
        assert "2 tools" in result.output  # bsl_ls
        assert "7 tools" in result.output  # kb


# ─── `1c-ai mcp serve --server NAME` ────────────────────────────────────────


class TestMcpServeServer:
    def test_unknown_server_rejected_by_click_choice(self) -> None:
        """click.Choice отклоняет неизвестное имя."""
        from agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["mcp", "serve", "--server", "unknown"])
        assert result.exit_code != 0

    @pytest.mark.parametrize("name", ["facade", "metadata", "codebase", "kb", "bsl_ls", "git"])
    def test_serve_creates_server_and_runs(self, name: str) -> None:
        """`1c-ai mcp serve --server NAME` создаёт Server и запускает (mock run)."""
        from agent.cli import main

        # Mock run_domain_server чтобы не запускать реальный stdio loop.
        with patch("mcp_servers.run_domain_server") as mock_run:
            import asyncio

            async def _mock_run(server_name: str, **kwargs: object) -> None:
                return None

            mock_run.side_effect = _mock_run
            runner = CliRunner()
            result = runner.invoke(main, ["mcp", "serve", "--server", name])
            assert result.exit_code == 0
            # facade получает handlers kwarg (DI из facade_entry); остальные — без kwargs.
            if name == "facade":
                mock_run.assert_called_once()
                call_args = mock_run.call_args
                assert call_args[0] == (name,) or call_args[0] == ()
                assert "handlers" in call_args[1] or call_args[0] == (name,)
            else:
                mock_run.assert_called_once_with(name)

    def test_serve_without_server_and_without_list_errors(self) -> None:
        """Без --server и без --list → error (cmd_mcp_serve проверяет server="")."""
        from agent.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["mcp", "serve"])
        # cmd_mcp_serve(server="", list_only=False) → unknown server error.
        assert result.exit_code == 1
        assert "Unknown server" in result.output or "Usage" in result.output

    def test_serve_run_domain_server_exception_exit_1(self) -> None:
        """run_domain_server упал → exit 1."""
        from agent.cli import main

        with patch("mcp_servers.run_domain_server") as mock_run:
            mock_run.side_effect = RuntimeError("stdio error")
            runner = CliRunner()
            result = runner.invoke(main, ["mcp", "serve", "--server", "facade"])
            assert result.exit_code == 1
            assert "MCP server error" in result.output


# ─── cmd_mcp_serve unit tests ────────────────────────────────────────────────


class TestCmdMcpServe:
    """Прямые тесты cmd_mcp_serve."""

    def test_list_only_returns_0(self) -> None:
        from agent.cli_commands.mcp import cmd_mcp_serve

        exit_code = cmd_mcp_serve(server="", list_only=True)
        assert exit_code == 0

    def test_unknown_server_returns_1(self) -> None:
        from agent.cli_commands.mcp import cmd_mcp_serve

        exit_code = cmd_mcp_serve(server="unknown", list_only=False)
        assert exit_code == 1

    def test_valid_server_runs(self) -> None:
        from agent.cli_commands.mcp import cmd_mcp_serve

        with patch("mcp_servers.run_domain_server") as mock_run:
            import asyncio

            async def _mock_run(server_name: str, **kwargs: object) -> None:
                return None

            mock_run.side_effect = _mock_run
            exit_code = cmd_mcp_serve(server="kb", list_only=False)
            assert exit_code == 0
            mock_run.assert_called_once_with("kb")
