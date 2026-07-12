"""PathManager — единый источник правды для всех путей проекта.

Все пути строятся по шаблонам с ${VAR} подстановкой из paths.env.
Никакой другой код не должен формировать пути к data/derived/runtime/ вручную.

См. ADR-0008 (PathManager — единый источник путей).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class PathManagerProtocol(Protocol):
    """Контракт PathManager.

    Реализация — PathManager. MCP-серверы и orchestrator зависят от Protocol,
    не от конкретного класса (для тестируемости с mock).
    """

    def data_config_dir(self, name: str, version: str) -> Path: ...
    def data_library_dir(self, name: str, version: str) -> Path: ...
    def data_archive_path(self, archive_name: str) -> Path: ...
    def data_hbk_dir(self, platform_version: str) -> Path: ...
    def derived_config_dir(self, name: str, version: str) -> Path: ...
    def derived_library_dir(self, name: str, version: str) -> Path: ...
    def derived_platform_dir(self, platform_version: str) -> Path: ...
    def unified_metadata_index(self, name: str, version: str) -> Path: ...
    def api_reference_index(self, name: str, version: str) -> Path: ...
    def call_graph_index(self, name: str, version: str) -> Path: ...
    def dependency_graph_index(self, name: str, version: str) -> Path: ...
    def codebase_embeddings_dir(self, name: str, version: str) -> Path: ...
    def library_metadata_index(self, name: str, version: str) -> Path: ...
    def library_api_reference_index(self, name: str, version: str) -> Path: ...
    def library_call_graph_index(self, name: str, version: str) -> Path: ...
    def platform_methods_db(self, platform_version: str) -> Path: ...
    def runtime_dir(self) -> Path: ...
    def config_registry_path(self) -> Path: ...
    def library_registry_path(self) -> Path: ...
    def session_state_path(self) -> Path: ...
    def soul_path(self) -> Path: ...
    def user_profile_path(self) -> Path: ...
    def project_context_path(self) -> Path: ...
    def session_resume_path(self) -> Path: ...
    def bsl_baseline_path(self, name: str, version: str) -> Path: ...
    def knowledge_base_dir(self) -> Path: ...
    def kb_index_path(self) -> Path: ...
    def kb_patterns_dir(self) -> Path: ...
    def kb_antipatterns_dir(self) -> Path: ...
    def kb_prompts_dir(self) -> Path: ...
    def kb_schemas_dir(self) -> Path: ...
    def vendor_dir(self) -> Path: ...
    def bsl_parser_grammar_dir(self) -> Path: ...

    def validate(self) -> dict[str, bool]: ...
    def freshness_check(self, name: str, version: str) -> dict[str, bool]: ...
    def ensure_dirs(self) -> None: ...


class PathManager:
    """Реализация PathManagerProtocol с ${VAR} подстановкой из paths.env.

    paths.env содержит переменные окружения для путей. OS env vars
    переопределяют значения из paths.env (полезно для CI/Docker).

    Args:
        env_path: путь к paths.env. По умолчанию — paths.env в текущей
            рабочей директории.

    Raises:
        FileNotFoundError: если paths.env не существует.

    Examples:
        >>> pm = PathManager()  # читает ./paths.env
        >>> pm.data_config_dir("ut11", "4.5.3")
        PosixPath('/path/to/project/data/configs/ut11/4.5.3')
    """

    def __init__(self, env_path: Path | None = None) -> None:
        env_path = env_path or Path.cwd() / "paths.env"
        self._env = self._load_env(env_path)
        self._project_root = env_path.parent

    def _load_env(self, env_path: Path) -> dict[str, str]:
        """Загрузить переменные из paths.env, OS env vars имеют приоритет.

        Raises:
            FileNotFoundError: если paths.env не существует.
        """
        if not env_path.exists():
            raise FileNotFoundError(f"paths.env not found: {env_path}")

        env: dict[str, str] = {}
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()

        # OS env vars override paths.env
        for key in list(env.keys()):
            if key in os.environ:
                env[key] = os.environ[key]

        return env

    def _resolve(self, template: str, **kwargs: str) -> Path:
        """Подставить ${VAR} из env, затем {key} из kwargs.

        Args:
            template: строка с ${VAR} и {kwarg} плейсхолдерами.
            **kwargs: значения для {kwarg} плейсхолдеров.

        Returns:
            Path — абсолютный путь (относительные пути ресолвятся от
            project_root = env_path.parent).

        Raises:
            KeyError: если в template есть ${VAR} без значения в env.
        """
        # Сначала ${VAR} из env
        for key, value in self._env.items():
            template = template.replace(f"${{{key}}}", value)
        # Проверка неразрешённых ${VAR}
        unresolved = re.findall(r"\$\{(\w+)\}", template)
        if unresolved:
            raise KeyError(
                f"Unresolved env vars in path template: {unresolved}. "
                f"Check paths.env — required vars: DATA_DIR, DERIVED_DIR, "
                f"RUNTIME_DIR, KNOWLEDGE_BASE_DIR, VENDOR_DIR."
            )
        # Затем {kwarg} — в Path
        formatted = template.format(**kwargs)
        # Path / "/abs/path" → "/abs/path" (Path semantics)
        return self._project_root / formatted

    # ─── data/ (пользовательский ввод) ──────────────────────────────────────

    def data_config_dir(self, name: str, version: str) -> Path:
        """data/configs/{name}/{version}/ — распакованная конфигурация 1С."""
        return self._resolve("${DATA_DIR}/configs/{name}/{version}", name=name, version=version)

    def data_library_dir(self, name: str, version: str) -> Path:
        """data/libraries/{name}/{version}/ — распакованная библиотека (БСП, БПО)."""
        return self._resolve("${DATA_DIR}/libraries/{name}/{version}", name=name, version=version)

    def data_archive_path(self, archive_name: str) -> Path:
        """data/archives/{archive_name} — ZIP архивы."""
        return self._resolve("${DATA_DIR}/archives/{archive}", archive=archive_name)

    def data_hbk_dir(self, platform_version: str) -> Path:  # noqa: D102
        """data/hbk/{platform_version}/ — .hbk файлы синтакс-помощника."""
        return self._resolve(
            "${DATA_DIR}/hbk/{platform_version}",
            platform_version=platform_version,
        )

    # ─── derived/ (сгенерированные индексы) ─────────────────────────────────

    def derived_config_dir(self, name: str, version: str) -> Path:  # noqa: D102
        """derived/configs/{name}/{version}/ — индексы конфигурации."""
        return self._resolve("${DERIVED_DIR}/configs/{name}/{version}", name=name, version=version)

    def derived_library_dir(self, name: str, version: str) -> Path:
        """derived/libraries/{name}/{version}/ — индексы библиотеки (БСП, БПО)."""
        return self._resolve("${DERIVED_DIR}/libraries/{name}/{version}", name=name, version=version)

    def derived_platform_dir(self, platform_version: str) -> Path:
        """derived/platform/{platform_version}/ — индексы платформы (SQLite)."""
        return self._resolve(
            "${DERIVED_DIR}/platform/{platform_version}",
            platform_version=platform_version,
        )

    def unified_metadata_index(self, name: str, version: str) -> Path:
        """derived/configs/{name}/{version}/unified-metadata-index.json."""
        return self.derived_config_dir(name, version) / "unified-metadata-index.json"

    def api_reference_index(self, name: str, version: str) -> Path:
        """derived/configs/{name}/{version}/api-reference.json."""
        return self.derived_config_dir(name, version) / "api-reference.json"

    def call_graph_index(self, name: str, version: str) -> Path:
        """derived/configs/{name}/{version}/call-graph.json."""
        return self.derived_config_dir(name, version) / "call-graph.json"

    def dependency_graph_index(self, name: str, version: str) -> Path:
        """derived/configs/{name}/{version}/dependency-graph.json."""
        return self.derived_config_dir(name, version) / "dependency-graph.json"

    # ─── Library indexes (БСП, БПО) ────────────────────────────────────────

    def library_metadata_index(self, name: str, version: str) -> Path:
        """derived/libraries/{name}/{version}/unified-metadata-index.json."""
        return self.derived_library_dir(name, version) / "unified-metadata-index.json"

    def library_api_reference_index(self, name: str, version: str) -> Path:
        """derived/libraries/{name}/{version}/api-reference.json."""
        return self.derived_library_dir(name, version) / "api-reference.json"

    def library_call_graph_index(self, name: str, version: str) -> Path:
        """derived/libraries/{name}/{version}/call-graph.json."""
        return self.derived_library_dir(name, version) / "call-graph.json"

    def codebase_embeddings_dir(self, name: str, version: str) -> Path:
        """derived/configs/{name}/{version}/embeddings/ — Qdrant snapshots."""
        return self.derived_config_dir(name, version) / "embeddings"

    def platform_methods_db(self, platform_version: str) -> Path:
        """derived/platform/{platform_version}/platform-methods.db."""
        return self.derived_platform_dir(platform_version) / "platform-methods.db"

    # ─── runtime/ (состояние сессий) ────────────────────────────────────────

    def runtime_dir(self) -> Path:
        """runtime/ — состояние сессий, реестр конфигов."""
        return self._resolve("${RUNTIME_DIR}")

    def config_registry_path(self) -> Path:
        """runtime/config-registry.json — ConfigRegistry."""
        return self.runtime_dir() / "config-registry.json"

    def library_registry_path(self) -> Path:
        """runtime/library-registry.json — LibraryRegistry (БСП, БПО)."""
        return self.runtime_dir() / "library-registry.json"

    def session_state_path(self) -> Path:
        """runtime/session-state.json — SessionManager."""
        return self.runtime_dir() / "session-state.json"

    def soul_path(self) -> Path:
        """runtime/soul.md — материализованный persona template."""
        return self.runtime_dir() / "soul.md"

    def user_profile_path(self) -> Path:
        """runtime/user-profile.md."""
        return self.runtime_dir() / "user-profile.md"

    def project_context_path(self) -> Path:
        """runtime/project-context.md."""
        return self.runtime_dir() / "project-context.md"

    def session_resume_path(self) -> Path:
        """runtime/session-resume.md."""
        return self.runtime_dir() / "session-resume.md"

    def bsl_baseline_path(self, name: str, version: str) -> Path:
        """derived/configs/{name}/{version}/bsl-baseline.json — BSL LS baseline."""
        return self.derived_config_dir(name, version) / "bsl-baseline.json"

    # ─── knowledge_base/ (KB-as-code, в git) ────────────────────────────────

    def knowledge_base_dir(self) -> Path:
        """knowledge-base/ — KB-as-code (YAML + Markdown)."""
        return self._resolve("${KNOWLEDGE_BASE_DIR}")

    def kb_index_path(self) -> Path:
        """knowledge-base/index.json — реестр всех элементов KB."""
        return self.knowledge_base_dir() / "index.json"

    def kb_patterns_dir(self) -> Path:
        """knowledge-base/patterns/ — YAML-эталоны."""
        return self.knowledge_base_dir() / "patterns"

    def kb_antipatterns_dir(self) -> Path:
        """knowledge-base/antipatterns/ — YAML с detect-паттернами."""
        return self.knowledge_base_dir() / "antipatterns"

    def kb_prompts_dir(self) -> Path:
        """knowledge-base/prompts/ — Jinja2 системные промпты."""
        return self.knowledge_base_dir() / "prompts"

    def kb_schemas_dir(self) -> Path:
        """knowledge-base/schemas/ — JSON Schemas."""
        return self.knowledge_base_dir() / "schemas"

    # ─── vendor/ (git submodules) ───────────────────────────────────────────

    def vendor_dir(self) -> Path:
        """vendor/ — git submodules."""
        return self._resolve("${VENDOR_DIR}")

    def bsl_parser_grammar_dir(self) -> Path:
        """vendor/bsl-parser-grammar/ — 1c-syntax/bsl-parser (LGPL-3.0)."""
        return self.vendor_dir() / "bsl-parser-grammar"

    # ─── валидация ──────────────────────────────────────────────────────────

    def validate(self) -> dict[str, bool]:
        """Preflight check перед запуском pipeline.

        Returns:
            Карта {path_name: exists_bool}. Ключи:
            - data_dir, derived_dir, runtime_dir, knowledge_base_dir, vendor_dir
            - config_registry, kb_index

        Используется CLI `1c-ai validate` и `data_status` MCP tool.
        """
        return {
            "data_dir": self._resolve("${DATA_DIR}").exists(),
            "derived_dir": self._resolve("${DERIVED_DIR}").exists(),
            "runtime_dir": self.runtime_dir().exists(),
            "knowledge_base_dir": self.knowledge_base_dir().exists(),
            "vendor_dir": self.vendor_dir().exists(),
            "config_registry": self.config_registry_path().exists(),
            "kb_index": self.kb_index_path().exists(),
        }

    def freshness_check(self, name: str, version: str) -> dict[str, bool]:
        """Проверка актуальности индексов для конфигурации.

        Args:
            name: имя конфигурации.
            version: версия конфигурации.

        Returns:
            Карта {index_name: is_fresh_bool}. Ключи:
            - unified_metadata, api_reference, call_graph, dependency_graph

            True = индекс свежий (mtime source <= mtime index).
            False = устарел, требуется `1c-ai config build --force`.
        """
        from .freshness import is_fresh

        result: dict[str, bool] = {}
        config_dir = self.data_config_dir(name, version)
        if not config_dir.exists():
            return {
                "unified_metadata": False,
                "api_reference": False,
                "call_graph": False,
                "dependency_graph": False,
            }

        for index_name, index_path in [
            ("unified_metadata", self.unified_metadata_index(name, version)),
            ("api_reference", self.api_reference_index(name, version)),
            ("call_graph", self.call_graph_index(name, version)),
            ("dependency_graph", self.dependency_graph_index(name, version)),
        ]:
            result[index_name] = is_fresh(config_dir, index_path)
        return result

    def ensure_dirs(self) -> None:
        """Создать основные директории, если отсутствуют.

        Вызывается при `1c-ai init` и первом запуске.
        НЕ создаёт data/configs/ — они создаются при `config add`.
        """
        for path in [
            self._resolve("${DATA_DIR}/archives"),
            self._resolve("${DATA_DIR}/hbk"),
            self._resolve("${DATA_DIR}/configs"),
            self._resolve("${DERIVED_DIR}/configs"),
            self._resolve("${DERIVED_DIR}/platform"),
            self.runtime_dir(),
        ]:
            path.mkdir(parents=True, exist_ok=True)
