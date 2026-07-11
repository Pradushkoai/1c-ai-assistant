"""Тесты для agent.cli — CLI 1c-ai."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from agent.cli import main


@pytest.fixture
def runner() -> CliRunner:
    """Click CliRunner для тестирования CLI."""
    return CliRunner()


@pytest.fixture
def project_env(tmp_path: Path, monkeypatch) -> Path:
    """Создаёт paths.env в tmp_path и делает tmp_path текущей директорией.

    Возвращает tmp_path (корень проекта для тестов).
    """
    env_content = f"""
DATA_DIR={tmp_path}/data
DERIVED_DIR={tmp_path}/derived
RUNTIME_DIR={tmp_path}/runtime
KNOWLEDGE_BASE_DIR={tmp_path}/kb
VENDOR_DIR={tmp_path}/vendor
"""
    env_path = tmp_path / "paths.env"
    env_path.write_text(env_content.strip(), encoding="utf-8")

    # Меняем текущую директорию на tmp_path (PathManager использует Path.cwd())
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ─── Smoke ─────────────────────────────────────────────────────────────────


class TestCliSmoke:
    """Базовые тесты CLI."""

    @pytest.mark.smoke
    def test_help(self, runner: CliRunner):
        """`1c-ai --help` показывает помощь."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "1C AI Assistant" in result.output

    def test_version(self, runner: CliRunner):
        """`1c-ai --version` показывает версию."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_no_args_shows_help(self, runner: CliRunner):
        """`1c-ai` без аргументов показывает помощь."""
        result = runner.invoke(main, [])
        assert result.exit_code == 0
        assert "Usage:" in result.output

    def test_init_help(self, runner: CliRunner):
        result = runner.invoke(main, ["init", "--help"])
        assert result.exit_code == 0
        assert "структуру директорий" in result.output.lower() or "directories" in result.output.lower()

    def test_config_help(self, runner: CliRunner):
        result = runner.invoke(main, ["config", "--help"])
        assert result.exit_code == 0
        assert "add" in result.output
        assert "build" in result.output
        assert "list" in result.output
        assert "remove" in result.output


# ─── init ──────────────────────────────────────────────────────────────────


class TestInitCommand:
    """`1c-ai init` — создание директорий."""

    @pytest.mark.smoke
    def test_init_creates_dirs(self, runner: CliRunner, project_env: Path):
        result = runner.invoke(main, ["init"])
        assert result.exit_code == 0
        assert (project_env / "data").exists()
        assert (project_env / "derived").exists()
        assert (project_env / "runtime").exists()

    def test_init_creates_subdirs(self, runner: CliRunner, project_env: Path):
        """init создаёт конкретные поддиректории."""
        result = runner.invoke(main, ["init"])
        assert result.exit_code == 0
        assert (project_env / "data" / "archives").exists()
        assert (project_env / "data" / "hbk").exists()
        assert (project_env / "data" / "configs").exists()
        assert (project_env / "derived" / "platform").exists()

    def test_init_idempotent(self, runner: CliRunner, project_env: Path):
        """Повторный init не падает."""
        result1 = runner.invoke(main, ["init"])
        assert result1.exit_code == 0
        result2 = runner.invoke(main, ["init"])
        assert result2.exit_code == 0

    def test_init_quiet(self, runner: CliRunner, project_env: Path):
        """--quiet подавляет вывод."""
        result = runner.invoke(main, ["init", "--quiet"])
        assert result.exit_code == 0
        assert "✅" not in result.output

    def test_init_missing_paths_env(self, runner: CliRunner, tmp_path: Path, monkeypatch):
        """Если paths.env нет — понятная ошибка."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(main, ["init"])
        assert result.exit_code == 1
        assert "paths.env" in result.output


# ─── validate ──────────────────────────────────────────────────────────────


class TestValidateCommand:
    """`1c-ai validate` — preflight check."""

    def test_validate_before_init(self, runner: CliRunner, project_env: Path):
        """До init — validate показывает отсутствие директорий."""
        result = runner.invoke(main, ["validate"])
        assert result.exit_code == 1  # не готово
        assert "❌" in result.output

    def test_validate_after_init(self, runner: CliRunner, project_env: Path):
        """После init — validate проходит."""
        runner.invoke(main, ["init"])
        result = runner.invoke(main, ["validate"])
        assert result.exit_code == 0
        assert "готово" in result.output.lower() or "ready" in result.output.lower()


# ─── config add ────────────────────────────────────────────────────────────


class TestConfigAddCommand:
    """`1c-ai config add` — добавление конфигурации."""

    @pytest.mark.smoke
    def test_add_from_zip(
        self,
        runner: CliRunner,
        project_env: Path,
        mini_config_zip: Path,
    ):
        """Добавление конфигурации из ZIP-архива."""
        result = runner.invoke(
            main,
            [
                "config",
                "add",
                "--name",
                "mini",
                "--version",
                "1.0",
                "--zip",
                str(mini_config_zip),
            ],
        )
        assert result.exit_code == 0, f"Output: {result.output}"
        assert "добавлена" in result.output

        # Проверяем, что конфигурация распакована
        config_dir = project_env / "data" / "configs" / "mini" / "1.0"
        assert (config_dir / "Configuration.xml").exists()

    def test_add_creates_registry_entry(
        self,
        runner: CliRunner,
        project_env: Path,
        mini_config_zip: Path,
    ):
        result = runner.invoke(
            main,
            [
                "config",
                "add",
                "--name",
                "mini",
                "--version",
                "1.0",
                "--zip",
                str(mini_config_zip),
            ],
        )
        assert result.exit_code == 0

        registry_path = project_env / "runtime" / "config-registry.json"
        assert registry_path.exists()

        import json

        data = json.loads(registry_path.read_text(encoding="utf-8"))
        assert len(data["entries"]) == 1
        assert data["entries"][0]["name"] == "mini"

    def test_add_duplicate_fails(
        self,
        runner: CliRunner,
        project_env: Path,
        mini_config_zip: Path,
    ):
        """Повторное add с тем же name/version — ошибка."""
        runner.invoke(
            main,
            ["config", "add", "--name", "mini", "--version", "1.0", "--zip", str(mini_config_zip)],
        )
        result = runner.invoke(
            main,
            ["config", "add", "--name", "mini", "--version", "1.0", "--zip", str(mini_config_zip)],
        )
        assert result.exit_code == 1
        assert "уже существует" in result.output

    def test_add_invalid_zip(
        self,
        runner: CliRunner,
        project_env: Path,
        tmp_path: Path,
    ):
        """Повреждённый ZIP — ошибка."""
        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_text("not a zip file", encoding="utf-8")

        result = runner.invoke(
            main,
            ["config", "add", "--name", "x", "--version", "1.0", "--zip", str(bad_zip)],
        )
        assert result.exit_code == 1

    def test_add_zip_without_configuration(
        self,
        runner: CliRunner,
        project_env: Path,
        tmp_path: Path,
    ):
        """ZIP без Configuration.xml — ошибка."""
        empty_zip = tmp_path / "empty.zip"
        with zipfile.ZipFile(empty_zip, "w") as zf:
            zf.writestr("readme.txt", "no Configuration.xml here")

        result = runner.invoke(
            main,
            ["config", "add", "--name", "x", "--version", "1.0", "--zip", str(empty_zip)],
        )
        assert result.exit_code == 1
        assert "Configuration.xml" in result.output


# ─── config build ──────────────────────────────────────────────────────────


class TestConfigBuildCommand:
    """`1c-ai config build` — построение индексов."""

    @pytest.mark.smoke
    def test_build_after_add(
        self,
        runner: CliRunner,
        project_env: Path,
        mini_config_zip: Path,
    ):
        """Полный цикл: add → build."""
        runner.invoke(
            main,
            ["config", "add", "--name", "mini", "--version", "1.0", "--zip", str(mini_config_zip)],
        )

        result = runner.invoke(main, ["config", "build", "--name", "mini"])
        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Объектов: 3" in result.output

        # Индекс создан
        index_path = project_env / "derived" / "configs" / "mini" / "1.0" / "unified-metadata-index.json"
        assert index_path.exists()

    def test_build_with_version(
        self,
        runner: CliRunner,
        project_env: Path,
        mini_config_zip: Path,
    ):
        runner.invoke(
            main,
            ["config", "add", "--name", "mini", "--version", "1.0", "--zip", str(mini_config_zip)],
        )

        result = runner.invoke(main, ["config", "build", "--name", "mini", "--version", "1.0"])
        assert result.exit_code == 0

    def test_build_nonexistent_config(self, runner: CliRunner, project_env: Path):
        result = runner.invoke(main, ["config", "build", "--name", "nonexistent"])
        assert result.exit_code == 1
        assert "не найдена" in result.output

    def test_build_check_freshness_stale(
        self,
        runner: CliRunner,
        project_env: Path,
        mini_config_zip: Path,
    ):
        """check-freshness до build — все stale."""
        runner.invoke(
            main,
            ["config", "add", "--name", "mini", "--version", "1.0", "--zip", str(mini_config_zip)],
        )

        result = runner.invoke(main, ["config", "build", "--name", "mini", "--check-freshness"])
        assert result.exit_code == 0
        assert "stale" in result.output

    def test_build_check_freshness_after_build(
        self,
        runner: CliRunner,
        project_env: Path,
        mini_config_zip: Path,
    ):
        """check-freshness после build — все fresh."""
        runner.invoke(
            main,
            ["config", "add", "--name", "mini", "--version", "1.0", "--zip", str(mini_config_zip)],
        )
        runner.invoke(main, ["config", "build", "--name", "mini"])

        result = runner.invoke(main, ["config", "build", "--name", "mini", "--check-freshness"])
        assert result.exit_code == 0
        assert "fresh" in result.output

    def test_build_skips_when_already_fresh(
        self,
        runner: CliRunner,
        project_env: Path,
        mini_config_zip: Path,
    ):
        """Без --force свежие индексы не перестраиваются."""
        import time

        runner.invoke(
            main,
            ["config", "add", "--name", "mini", "--version", "1.0", "--zip", str(mini_config_zip)],
        )
        runner.invoke(main, ["config", "build", "--name", "mini"])

        # Небольшая пауза, чтобы mtime index был гарантированно раньше следующих проверок
        time.sleep(0.1)

        # Второй build без --force — пропускает
        result = runner.invoke(main, ["config", "build", "--name", "mini"])
        assert result.exit_code == 0
        assert "уже свежие" in result.output

    def test_build_force_rebuilds(
        self,
        runner: CliRunner,
        project_env: Path,
        mini_config_zip: Path,
    ):
        """--force перестраивает даже свежие."""
        runner.invoke(
            main,
            ["config", "add", "--name", "mini", "--version", "1.0", "--zip", str(mini_config_zip)],
        )
        runner.invoke(main, ["config", "build", "--name", "mini"])

        result = runner.invoke(main, ["config", "build", "--name", "mini", "--force"])
        assert result.exit_code == 0
        assert "Индексация" in result.output


# ─── config list ───────────────────────────────────────────────────────────


class TestConfigListCommand:
    """`1c-ai config list` — список конфигураций."""

    def test_list_empty(self, runner: CliRunner, project_env: Path):
        """Пустой список — подсказка."""
        runner.invoke(main, ["init"])  # создать runtime/
        result = runner.invoke(main, ["config", "list"])
        assert result.exit_code == 0
        assert "не загружены" in result.output

    def test_list_shows_added(
        self,
        runner: CliRunner,
        project_env: Path,
        mini_config_zip: Path,
    ):
        runner.invoke(
            main,
            ["config", "add", "--name", "mini", "--version", "1.0", "--zip", str(mini_config_zip)],
        )

        result = runner.invoke(main, ["config", "list"])
        assert result.exit_code == 0
        assert "mini" in result.output
        assert "1.0" in result.output

    def test_list_shows_index_status(
        self,
        runner: CliRunner,
        project_env: Path,
        mini_config_zip: Path,
    ):
        """После build list показывает индекс."""
        runner.invoke(
            main,
            ["config", "add", "--name", "mini", "--version", "1.0", "--zip", str(mini_config_zip)],
        )
        runner.invoke(main, ["config", "build", "--name", "mini"])

        result = runner.invoke(main, ["config", "list"])
        assert result.exit_code == 0
        assert "Индекс:" in result.output
        assert "КБ" in result.output


# ─── config remove ─────────────────────────────────────────────────────────


class TestConfigRemoveCommand:
    """`1c-ai config remove` — удаление конфигурации."""

    def test_remove_with_confirmation(
        self,
        runner: CliRunner,
        project_env: Path,
        mini_config_zip: Path,
    ):
        runner.invoke(
            main,
            ["config", "add", "--name", "mini", "--version", "1.0", "--zip", str(mini_config_zip)],
        )

        # --yes пропускает confirmation prompt
        result = runner.invoke(
            main,
            ["config", "remove", "--name", "mini", "--version", "1.0", "--yes"],
        )
        assert result.exit_code == 0
        assert "удалена" in result.output

        # Директория версии удалена (data/configs/mini/1.0/)
        version_dir = project_env / "data" / "configs" / "mini" / "1.0"
        assert not version_dir.exists()

    def test_remove_keep_data(
        self,
        runner: CliRunner,
        project_env: Path,
        mini_config_zip: Path,
    ):
        """--keep-data не удаляет файлы."""
        runner.invoke(
            main,
            ["config", "add", "--name", "mini", "--version", "1.0", "--zip", str(mini_config_zip)],
        )

        result = runner.invoke(
            main,
            ["config", "remove", "--name", "mini", "--version", "1.0", "--keep-data", "--yes"],
        )
        assert result.exit_code == 0

        # Директория осталась
        config_dir = project_env / "data" / "configs" / "mini"
        assert config_dir.exists()

    def test_remove_nonexistent(self, runner: CliRunner, project_env: Path):
        result = runner.invoke(
            main,
            ["config", "remove", "--name", "x", "--version", "1.0", "--yes"],
        )
        assert result.exit_code == 1


# ─── hbk load ──────────────────────────────────────────────────────────────


class TestHbkLoadCommand:
    """`1c-ai hbk load` — загрузка .hbk файлов (минимальная версия)."""

    def test_hbk_load_no_files(self, runner: CliRunner, project_env: Path, tmp_path: Path):
        """Если .hbk файлов нет — предупреждение."""
        empty_dir = tmp_path / "hbk_empty"
        empty_dir.mkdir()

        result = runner.invoke(
            main,
            ["hbk", "load", "--version", "8.3.20", "--path", str(empty_dir)],
        )
        assert result.exit_code == 1
        assert "не найдены" in result.output

    def test_hbk_load_creates_db(
        self,
        runner: CliRunner,
        project_env: Path,
        tmp_path: Path,
    ):
        """С .hbk файлами — создаётся БД."""
        hbk_dir = tmp_path / "hbk_test"
        hbk_dir.mkdir()
        # Создаём фиктивный .hbk файл
        (hbk_dir / "shcntx_ru.hbk").write_bytes(b"\x00\x01\x02\x03")

        result = runner.invoke(
            main,
            ["hbk", "load", "--version", "8.3.20", "--path", str(hbk_dir)],
        )
        assert result.exit_code == 0, f"Output: {result.output}"
        assert "БД создана" in result.output

        db_path = project_env / "derived" / "platform" / "8.3.20" / "platform-methods.db"
        assert db_path.exists()

        # Проверяем содержимое БД
        import sqlite3

        with sqlite3.connect(db_path) as conn:
            cur = conn.execute("SELECT value FROM platform_meta WHERE key = 'platform_version'")
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "8.3.20"


# ─── End-to-end ────────────────────────────────────────────────────────────


class TestEndToEnd:
    """Полный цикл: init → add → build → list → validate."""

    @pytest.mark.smoke
    def test_full_workflow(
        self,
        runner: CliRunner,
        project_env: Path,
        mini_config_zip: Path,
    ):
        """Полный workflow от init до list с индексом."""
        # 1. Init
        result = runner.invoke(main, ["init"])
        assert result.exit_code == 0

        # 2. Validate (готово, но конфигов нет)
        result = runner.invoke(main, ["validate"])
        assert result.exit_code == 0

        # 3. Add
        result = runner.invoke(
            main,
            ["config", "add", "--name", "mini", "--version", "1.0", "--zip", str(mini_config_zip)],
        )
        assert result.exit_code == 0

        # 4. Build
        result = runner.invoke(main, ["config", "build", "--name", "mini"])
        assert result.exit_code == 0
        assert "Объектов: 3" in result.output

        # 5. List (показывает конфигурацию с индексом)
        result = runner.invoke(main, ["config", "list"])
        assert result.exit_code == 0
        assert "mini" in result.output
        assert "КБ" in result.output

        # 6. check-freshness
        result = runner.invoke(
            main,
            ["config", "build", "--name", "mini", "--check-freshness"],
        )
        assert result.exit_code == 0
        assert "fresh" in result.output

        # 7. Validate
        result = runner.invoke(main, ["validate"])
        assert result.exit_code == 0
        assert "mini" in result.output
