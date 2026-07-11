"""Тесты для agent.cli generate — 1c-ai generate."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from agent.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project_env(tmp_path: Path, monkeypatch) -> Path:
    """Создаёт paths.env + init + config add mini."""
    env_content = f"""
DATA_DIR={tmp_path}/data
DERIVED_DIR={tmp_path}/derived
RUNTIME_DIR={tmp_path}/runtime
KNOWLEDGE_BASE_DIR={tmp_path}/kb
VENDOR_DIR={tmp_path}/vendor
"""
    env_path = tmp_path / "paths.env"
    env_path.write_text(env_content.strip(), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestGenerateCliSmoke:
    @pytest.mark.smoke
    def test_help(self, runner: CliRunner):
        result = runner.invoke(main, ["generate", "--help"])
        assert result.exit_code == 0
        assert "Сгенерировать BSL-код" in result.output
        assert "--task" in result.output
        assert "--config" in result.output

    def test_no_args_shows_error(self, runner: CliRunner):
        result = runner.invoke(main, ["generate"])
        assert result.exit_code != 0
        assert "Missing option" in result.output or "Error" in result.output


class TestGenerateMissingConfig:
    def test_config_not_found(self, runner: CliRunner, project_env: Path):
        runner.invoke(main, ["init"])
        result = runner.invoke(
            main,
            ["generate", "--task", "Test", "--config", "nonexistent"],
        )
        assert result.exit_code == 1
        assert "не найдена" in result.output

    def test_missing_paths_env(self, runner: CliRunner, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            main,
            ["generate", "--task", "Test", "--config", "x"],
        )
        assert result.exit_code == 1
        assert "paths.env" in result.output


class TestGenerateWithMockedPipeline:
    """Тесты с mocked pipeline — не вызывают реальный LLM."""

    @pytest.mark.asyncio
    async def test_generate_success(self, runner: CliRunner, project_env: Path):
        """Полный успех — pipeline возвращает DONE с кодом."""
        runner.invoke(main, ["init"])

        # Добавляем конфигурацию в реестр
        from data_layer import ConfigRegistry
        from datetime import UTC, datetime
        from parsers.models import ConfigRegistryEntry

        pm_path = project_env / "runtime" / "config-registry.json"
        registry = ConfigRegistry(pm_path)
        registry.add(
            ConfigRegistryEntry(
                name="mini",
                version="1.0",
                added_at=datetime.now(UTC),
                source_path=str(project_env / "data" / "configs" / "mini" / "1.0"),
                index_path=str(project_env / "derived" / "configs" / "mini" / "1.0"),
            )
        )

        # Mocked final state
        mock_final_state = {
            "fsm_state": "done",
            "iterations": [
                {
                    "number": 1,
                    "code": 'Процедура Тест()\n\tСообщить("Hello");\nКонецПроцедуры',
                    "llm_response": {},
                    "bsl_ls_diagnostics": [],
                    "review_findings": [],
                    "test_result": None,
                    "edit_distance_vs_prev": 0.0,
                    "failed_checks": [],
                    "created_at": "2026-07-11T15:00:00Z",
                }
            ],
            "commit_result": {
                "subtask_id": "st-001",
                "branch_name": "feature/test",
                "commit_sha": "abc123",
                "pr_url": None,
                "pr_number": None,
                "files_changed": ["runtime/generated/st-001_1.bsl"],
                "diff_summary": "3 lines",
            },
        }

        with patch("agent.cli_commands.generate.asyncio.run") as mock_run:
            mock_run.return_value = mock_final_state

            result = runner.invoke(
                main,
                [
                    "generate",
                    "--task",
                    "Создать функцию Тест",
                    "--config",
                    "mini",
                    "--version",
                    "1.0",
                ],
            )

        assert result.exit_code == 0
        assert "выполнена успешно" in result.output
        assert "Процедура Тест" in result.output
        assert "Итераций: 1" in result.output

    @pytest.mark.asyncio
    async def test_generate_escalated(self, runner: CliRunner, project_env: Path):
        """Эскалация — pipeline возвращает ESCALATED."""
        runner.invoke(main, ["init"])

        from data_layer import ConfigRegistry
        from datetime import UTC, datetime
        from parsers.models import ConfigRegistryEntry

        pm_path = project_env / "runtime" / "config-registry.json"
        registry = ConfigRegistry(pm_path)
        registry.add(
            ConfigRegistryEntry(
                name="mini",
                version="1.0",
                added_at=datetime.now(UTC),
                source_path=str(project_env / "data" / "configs" / "mini" / "1.0"),
                index_path=str(project_env / "derived" / "configs" / "mini" / "1.0"),
            )
        )

        mock_final_state = {
            "fsm_state": "escalated",
            "iterations": [
                {
                    "number": 3,
                    "code": "Процедура Тест() КонецПроцедуры",
                    "llm_response": {},
                    "bsl_ls_diagnostics": [],
                    "review_findings": [],
                    "test_result": None,
                    "edit_distance_vs_prev": 0.03,
                    "failed_checks": [{"code": "BSL-WS-001"}],
                    "created_at": "2026-07-11T15:00:00Z",
                }
            ],
            "escalate_result": {
                "subtask_id": "st-001",
                "reason": "max_iterations_exceeded",
                "iteration_log": [],
                "pr_url": None,
                "suggested_actions": ["Проверьте промпт", "Упростите задачу"],
            },
        }

        with patch("agent.cli_commands.generate.asyncio.run") as mock_run:
            mock_run.return_value = mock_final_state

            result = runner.invoke(
                main,
                ["generate", "--task", "Test", "--config", "mini", "--version", "1.0"],
            )

        assert result.exit_code == 1
        assert "эскалирована" in result.output
        assert "max_iterations_exceeded" in result.output
        assert "Проверьте промпт" in result.output

    def test_generate_output_to_file(self, runner: CliRunner, project_env: Path, tmp_path: Path):
        """--output сохраняет результат в файл."""
        runner.invoke(main, ["init"])

        from data_layer import ConfigRegistry
        from datetime import UTC, datetime
        from parsers.models import ConfigRegistryEntry

        pm_path = project_env / "runtime" / "config-registry.json"
        registry = ConfigRegistry(pm_path)
        registry.add(
            ConfigRegistryEntry(
                name="mini",
                version="1.0",
                added_at=datetime.now(UTC),
                source_path=str(project_env / "data" / "configs" / "mini" / "1.0"),
                index_path=str(project_env / "derived" / "configs" / "mini" / "1.0"),
            )
        )

        mock_final_state = {
            "fsm_state": "done",
            "iterations": [
                {
                    "number": 1,
                    "code": "Процедура Тест()\nКонецПроцедуры",
                    "llm_response": {},
                    "bsl_ls_diagnostics": [],
                    "review_findings": [],
                    "test_result": None,
                    "edit_distance_vs_prev": 0.0,
                    "failed_checks": [],
                    "created_at": "2026-07-11T15:00:00Z",
                }
            ],
            "commit_result": None,
        }

        output_file = tmp_path / "result.bsl"

        with patch("agent.cli_commands.generate.asyncio.run") as mock_run:
            mock_run.return_value = mock_final_state

            result = runner.invoke(
                main,
                [
                    "generate",
                    "--task",
                    "Test",
                    "--config",
                    "mini",
                    "--version",
                    "1.0",
                    "--output",
                    str(output_file),
                ],
            )

        assert result.exit_code == 0
        assert output_file.exists()
        assert "Процедура Тест" in output_file.read_text(encoding="utf-8")
