"""Тесты для data_layer.path_manager — PathManager.

См. TESTING_POLICY.md и docs/architecture/03-paths-protocol.md.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from data_layer import PathManager
from data_layer.path_manager import PathManagerProtocol


# ─── Smoke тесты ─────────────────────────────────────────────────────────────


class TestPathManagerCreation:
    """Создание PathManager и загрузка paths.env."""

    @pytest.mark.smoke
    def test_create_with_explicit_env(self, tmp_path: Path):
        env = tmp_path / "paths.env"
        env.write_text("DATA_DIR=./data\nDERIVED_DIR=./derived\n", encoding="utf-8")
        pm = PathManager(env_path=env)
        assert pm is not None

    def test_create_missing_env_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="paths.env not found"):
            PathManager(env_path=tmp_path / "nonexistent.env")

    def test_protocol_compliance(self, tmp_paths: PathManager):
        """PathManager реализует PathManagerProtocol."""
        assert isinstance(tmp_paths, PathManagerProtocol)


class TestPathManagerEnvLoading:
    """Загрузка paths.env и OS env override."""

    def test_env_comments_ignored(self, tmp_path: Path):
        env = tmp_path / "paths.env"
        env.write_text(
            "# Comment line\n"
            "DATA_DIR=./data\n"
            "# Another comment\n"
            "DERIVED_DIR=./derived\n"
            "RUNTIME_DIR=./runtime\n"
            "KNOWLEDGE_BASE_DIR=./kb\n"
            "VENDOR_DIR=./vendor\n",
            encoding="utf-8",
        )
        pm = PathManager(env_path=env)
        # path = tmp_path/data/configs/x/1 → "data" в str(path)
        path_str = str(pm.data_config_dir("x", "1"))
        assert "/data/" in path_str or "/data\\" in path_str or path_str.endswith("/data/configs/x/1")

    def test_env_blank_lines_ignored(self, tmp_path: Path):
        env = tmp_path / "paths.env"
        env.write_text(
            "\nDATA_DIR=./data\n\n\nDERIVED_DIR=./derived\n\n"
            "RUNTIME_DIR=./runtime\nKNOWLEDGE_BASE_DIR=./kb\nVENDOR_DIR=./vendor\n",
            encoding="utf-8",
        )
        pm = PathManager(env_path=env)
        assert pm.runtime_dir() is not None

    def test_env_lines_without_equals_ignored(self, tmp_path: Path):
        env = tmp_path / "paths.env"
        env.write_text(
            "INVALID_LINE\n"
            "DATA_DIR=./data\n"
            "DERIVED_DIR=./derived\n"
            "RUNTIME_DIR=./runtime\n"
            "KNOWLEDGE_BASE_DIR=./kb\n"
            "VENDOR_DIR=./vendor\n",
            encoding="utf-8",
        )
        pm = PathManager(env_path=env)
        assert pm.data_config_dir("x", "1") is not None

    def test_os_env_override(self, tmp_path: Path, monkeypatch):
        """OS env vars переопределяют paths.env."""
        env = tmp_path / "paths.env"
        env.write_text(
            "DATA_DIR=./default_data\n"
            "DERIVED_DIR=./derived\n"
            "RUNTIME_DIR=./runtime\n"
            "KNOWLEDGE_BASE_DIR=./kb\n"
            "VENDOR_DIR=./vendor\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("DATA_DIR", "/custom/data")
        pm = PathManager(env_path=env)
        # Path / "/abs" = "/abs" (Path semantics)
        assert "/custom/data" in str(pm.data_config_dir("x", "1"))


# ─── data/ paths ────────────────────────────────────────────────────────────


class TestDataPaths:
    """Пути к пользовательским данным."""

    @pytest.mark.smoke
    def test_data_config_dir(self, tmp_paths: PathManager):
        path = tmp_paths.data_config_dir("ut11", "4.5.3")
        assert path.name == "4.5.3"
        assert path.parent.name == "ut11"
        assert "configs" in str(path)

    def test_data_config_dir_cyrillic(self, tmp_paths: PathManager):
        """Кириллические имена должны работать."""
        path = tmp_paths.data_config_dir("УТ11", "4.5.3")
        assert "УТ11" in str(path)

    def test_data_archive_path(self, tmp_paths: PathManager):
        path = tmp_paths.data_archive_path("ut11-4.5.3.zip")
        assert path.name == "ut11-4.5.3.zip"
        assert "archives" in str(path)

    def test_data_hbk_dir(self, tmp_paths: PathManager):
        path = tmp_paths.data_hbk_dir("8.3.20")
        assert path.name == "8.3.20"
        assert "hbk" in str(path)


# ─── derived/ paths ─────────────────────────────────────────────────────────


class TestDerivedPaths:
    """Пути к сгенерированным индексам."""

    @pytest.mark.smoke
    def test_derived_config_dir(self, tmp_paths: PathManager):
        path = tmp_paths.derived_config_dir("ut11", "4.5.3")
        assert path.name == "4.5.3"
        assert path.parent.name == "ut11"

    def test_unified_metadata_index(self, tmp_paths: PathManager):
        path = tmp_paths.unified_metadata_index("ut11", "4.5.3")
        assert path.name == "unified-metadata-index.json"
        assert path.parent.name == "4.5.3"

    def test_api_reference_index(self, tmp_paths: PathManager):
        path = tmp_paths.api_reference_index("ut11", "4.5.3")
        assert path.name == "api-reference.json"

    def test_call_graph_index(self, tmp_paths: PathManager):
        path = tmp_paths.call_graph_index("ut11", "4.5.3")
        assert path.name == "call-graph.json"

    def test_dependency_graph_index(self, tmp_paths: PathManager):
        path = tmp_paths.dependency_graph_index("ut11", "4.5.3")
        assert path.name == "dependency-graph.json"

    def test_codebase_embeddings_dir(self, tmp_paths: PathManager):
        path = tmp_paths.codebase_embeddings_dir("ut11", "4.5.3")
        assert path.name == "embeddings"

    def test_platform_methods_db(self, tmp_paths: PathManager):
        path = tmp_paths.platform_methods_db("8.3.20")
        assert path.name == "platform-methods.db"
        assert "8.3.20" in str(path)
        assert "platform" in str(path)

    def test_bsl_baseline_path(self, tmp_paths: PathManager):
        path = tmp_paths.bsl_baseline_path("ut11", "4.5.3")
        assert path.name == "bsl-baseline.json"


# ─── runtime/ paths ─────────────────────────────────────────────────────────


class TestRuntimePaths:
    """Пути к состоянию сессий."""

    def test_runtime_dir(self, tmp_paths: PathManager):
        path = tmp_paths.runtime_dir()
        assert "runtime" in str(path)

    def test_config_registry_path(self, tmp_paths: PathManager):
        path = tmp_paths.config_registry_path()
        assert path.name == "config-registry.json"

    def test_session_state_path(self, tmp_paths: PathManager):
        path = tmp_paths.session_state_path()
        assert path.name == "session-state.json"

    def test_soul_path(self, tmp_paths: PathManager):
        path = tmp_paths.soul_path()
        assert path.name == "soul.md"

    def test_user_profile_path(self, tmp_paths: PathManager):
        path = tmp_paths.user_profile_path()
        assert path.name == "user-profile.md"

    def test_project_context_path(self, tmp_paths: PathManager):
        path = tmp_paths.project_context_path()
        assert path.name == "project-context.md"

    def test_session_resume_path(self, tmp_paths: PathManager):
        path = tmp_paths.session_resume_path()
        assert path.name == "session-resume.md"


# ─── knowledge_base/ paths ──────────────────────────────────────────────────


class TestKBPaths:
    """Пути к KB-as-code."""

    def test_knowledge_base_dir(self, tmp_paths: PathManager):
        path = tmp_paths.knowledge_base_dir()
        assert "kb" in str(path)

    def test_kb_index_path(self, tmp_paths: PathManager):
        path = tmp_paths.kb_index_path()
        assert path.name == "index.json"

    def test_kb_patterns_dir(self, tmp_paths: PathManager):
        path = tmp_paths.kb_patterns_dir()
        assert path.name == "patterns"

    def test_kb_antipatterns_dir(self, tmp_paths: PathManager):
        path = tmp_paths.kb_antipatterns_dir()
        assert path.name == "antipatterns"

    def test_kb_prompts_dir(self, tmp_paths: PathManager):
        path = tmp_paths.kb_prompts_dir()
        assert path.name == "prompts"

    def test_kb_schemas_dir(self, tmp_paths: PathManager):
        path = tmp_paths.kb_schemas_dir()
        assert path.name == "schemas"


# ─── vendor/ paths ──────────────────────────────────────────────────────────


class TestVendorPaths:
    """Пути к git submodules."""

    def test_vendor_dir(self, tmp_paths: PathManager):
        path = tmp_paths.vendor_dir()
        assert "vendor" in str(path)

    def test_bsl_parser_grammar_dir(self, tmp_paths: PathManager):
        path = tmp_paths.bsl_parser_grammar_dir()
        assert path.name == "bsl-parser-grammar"


# ─── validate() ─────────────────────────────────────────────────────────────


class TestValidate:
    """PathManager.validate() — preflight check."""

    @pytest.mark.smoke
    def test_validate_missing_dirs(self, tmp_paths: PathManager):
        """Когда директории не созданы — все False."""
        result = tmp_paths.validate()
        assert isinstance(result, dict)
        assert result["data_dir"] is False
        assert result["derived_dir"] is False
        assert result["runtime_dir"] is False
        assert result["knowledge_base_dir"] is False
        assert result["vendor_dir"] is False
        assert result["config_registry"] is False
        assert result["kb_index"] is False

    def test_validate_after_ensure_dirs(self, tmp_paths: PathManager):
        """После ensure_dirs() основные директории существуют."""
        tmp_paths.ensure_dirs()
        result = tmp_paths.validate()
        # data_dir существует (создан через archives/, hbk/, configs/)
        assert result["data_dir"] is True
        assert result["derived_dir"] is True
        assert result["runtime_dir"] is True
        # config_registry НЕ создан — это файл, ensure_dirs создаёт только директории
        assert result["config_registry"] is False

    def test_validate_returns_all_required_keys(self, tmp_paths: PathManager):
        """validate() возвращает все обязательные ключи."""
        result = tmp_paths.validate()
        required_keys = {
            "data_dir",
            "derived_dir",
            "runtime_dir",
            "knowledge_base_dir",
            "vendor_dir",
            "config_registry",
            "kb_index",
        }
        assert set(result.keys()) == required_keys


# ─── freshness_check() ─────────────────────────────────────────────────────


class TestFreshnessCheck:
    """PathManager.freshness_check() — проверка свежести индексов."""

    def test_freshness_check_missing_config(self, tmp_paths: PathManager):
        """Если конфигурации нет — все индексы False."""
        result = tmp_paths.freshness_check("ut11", "4.5.3")
        assert all(v is False for v in result.values())
        assert set(result.keys()) == {
            "unified_metadata",
            "api_reference",
            "call_graph",
            "dependency_graph",
        }

    def test_freshness_check_missing_index(self, tmp_paths: PathManager):
        """Конфигурация есть, индекса нет — False."""
        config_dir = tmp_paths.data_config_dir("ut11", "4.5.3")
        config_dir.mkdir(parents=True)
        (config_dir / "Configuration.xml").write_text("<root/>", encoding="utf-8")

        result = tmp_paths.freshness_check("ut11", "4.5.3")
        assert all(v is False for v in result.values())

    def test_freshness_check_fresh(self, tmp_paths: PathManager):
        """Индекс свежий, если mtime(index) >= mtime(source)."""
        config_dir = tmp_paths.data_config_dir("ut11", "4.5.3")
        config_dir.mkdir(parents=True)
        (config_dir / "Configuration.xml").write_text("<root/>", encoding="utf-8")

        # Небольшая пауза, чтобы mtime(index) > mtime(source)
        time.sleep(0.05)

        index = tmp_paths.unified_metadata_index("ut11", "4.5.3")
        index.parent.mkdir(parents=True)
        index.write_text("{}", encoding="utf-8")

        result = tmp_paths.freshness_check("ut11", "4.5.3")
        assert result["unified_metadata"] is True
        # Остальные индексы не созданы — False
        assert result["api_reference"] is False
        assert result["call_graph"] is False
        assert result["dependency_graph"] is False

    def test_freshness_check_stale(self, tmp_paths: PathManager):
        """Индекс устарел, если mtime(source) > mtime(index)."""
        # Сначала создаём индекс
        index = tmp_paths.unified_metadata_index("ut11", "4.5.3")
        index.parent.mkdir(parents=True)
        index.write_text("{}", encoding="utf-8")

        time.sleep(0.05)

        # Потом — исходник (он свежее)
        config_dir = tmp_paths.data_config_dir("ut11", "4.5.3")
        config_dir.mkdir(parents=True)
        (config_dir / "Configuration.xml").write_text("<root/>", encoding="utf-8")

        result = tmp_paths.freshness_check("ut11", "4.5.3")
        assert result["unified_metadata"] is False

    def test_freshness_check_all_indexes_fresh(self, tmp_paths: PathManager):
        """Все 4 индекса свежие."""
        config_dir = tmp_paths.data_config_dir("ut11", "4.5.3")
        config_dir.mkdir(parents=True)
        (config_dir / "Configuration.xml").write_text("<root/>", encoding="utf-8")

        time.sleep(0.05)

        for index_method in [
            tmp_paths.unified_metadata_index,
            tmp_paths.api_reference_index,
            tmp_paths.call_graph_index,
            tmp_paths.dependency_graph_index,
        ]:
            index_path = index_method("ut11", "4.5.3")
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text("{}", encoding="utf-8")

        result = tmp_paths.freshness_check("ut11", "4.5.3")
        assert all(result.values()), f"Some indexes are stale: {result}"


# ─── ensure_dirs() ──────────────────────────────────────────────────────────


class TestEnsureDirs:
    """PathManager.ensure_dirs() — создание директорий."""

    def test_ensure_dirs_creates_all(self, tmp_paths: PathManager):
        tmp_paths.ensure_dirs()

        # Проверяем, что основные директории созданы
        assert tmp_paths._resolve("${DATA_DIR}/archives").exists()
        assert tmp_paths._resolve("${DATA_DIR}/hbk").exists()
        assert tmp_paths._resolve("${DATA_DIR}/configs").exists()
        assert tmp_paths._resolve("${DERIVED_DIR}/configs").exists()
        assert tmp_paths._resolve("${DERIVED_DIR}/platform").exists()
        assert tmp_paths.runtime_dir().exists()

    def test_ensure_dirs_idempotent(self, tmp_paths: PathManager):
        """Повторный вызов ensure_dirs() не падает."""
        tmp_paths.ensure_dirs()
        tmp_paths.ensure_dirs()  # не должно падать
        assert tmp_paths.runtime_dir().exists()

    def test_ensure_dirs_does_not_create_configs_subdir(self, tmp_paths: PathManager):
        """ensure_dirs() НЕ создаёт data/configs/{name}/{version}/.

        Они создаются при `1c-ai config add`.
        """
        tmp_paths.ensure_dirs()
        config_dir = tmp_paths.data_config_dir("ut11", "4.5.3")
        assert not config_dir.exists()


# ─── Property-based тесты ────────────────────────────────────────────────────


class TestPathManagerProperty:
    """Property-based тесты для PathManager."""

    @given(
        name=st.text(
            min_size=1, max_size=30, alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="/\\:\0")
        ),
        version=st.text(
            min_size=1, max_size=20, alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="/\\:\0")
        ),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_data_config_dir_round_trip(self, tmp_paths: PathManager, name: str, version: str):
        """data_config_dir(name, version).name == version и .parent.name == name.

        Property: для любых name и version (без path-сепараторов) структура пути сохраняется.
        """
        path = tmp_paths.data_config_dir(name, version)
        assert path.name == version
        assert path.parent.name == name

    @given(
        platform_version=st.text(min_size=1, max_size=20),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_platform_methods_db_path(self, tmp_paths: PathManager, platform_version: str):
        """platform_methods_db(v).name == 'platform-methods.db'."""
        path = tmp_paths.platform_methods_db(platform_version)
        assert path.name == "platform-methods.db"
        assert platform_version in str(path)


# ─── Интеграция с paths.env из проекта ──────────────────────────────────────


class TestProjectPathsEnv:
    """Тест что paths.env из проекта валиден."""

    @pytest.mark.smoke
    def test_project_paths_env_loads(self):
        """paths.env в корне проекта загружается без ошибок."""
        project_root = Path(__file__).parent.parent.parent
        paths_env = project_root / "paths.env"
        if not paths_env.exists():
            pytest.skip("paths.env not found in project root")

        pm = PathManager(env_path=paths_env)
        # Все основные методы должны работать
        assert pm.data_config_dir("test", "1.0") is not None
        assert pm.derived_config_dir("test", "1.0") is not None
        assert pm.runtime_dir() is not None
        assert pm.knowledge_base_dir() is not None
