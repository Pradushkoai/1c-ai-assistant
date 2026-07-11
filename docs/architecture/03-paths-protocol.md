# Шаг 3 — Configuration & paths protocol (PathManager)

> **ADR-0008:** PathManager — единый источник правды для всех путей
> **Зависимости:** Шаг 1 (структура), Шаг 2 (`ConfigMeta`, `ConfigRegistryEntry`)
> **Артефакт:** `packages/data_layer/src/data_layer/path_manager.py` + `paths.env` + структура директорий

## 1. Зачем PathManager

В проекте 6 типов путей:
- `data/configs/{name}/{version}/` — пользовательский ввод (XML/BSL)
- `data/archives/` — ZIP архивы
- `data/hbk/{platform_version}/` — синтакс-помощник
- `derived/configs/{name}/{version}/` — индексы (JSON, SQLite)
- `derived/platform/{version}/` — platform-methods.db
- `runtime/` — состояние сессий, config-registry.json
- `knowledge-base/` — KB-as-code (в git, не gitignored)
- `vendor/bsl-parser-grammar/` — submodule

Без PathManager:
- 4 MCP-сервера формируют пути各自 → расхождения (`configs/ut11/4.5.3/` vs `configs/ut11-4.5.3/`)
- orchestrator не знает, где лежат индексы → гонки при freshness check
- CLI и MCP-facade могут по-разному понимать `1c-ai config list`
- тесты создают временные директории хаотично

С PathManager:
- один класс строит пути по темплейту
- `validate()` возвращает `{path: exists_bool}` для preflight check
- `freshness_check()` сравнивает mtime(source) vs mtime(index)
- тесты подменяют `${DATA_DIR}` на tmp_path

## 2. Контракт PathManager

```python
# packages/data_layer/src/data_layer/path_manager.py
"""PathManager — единый источник правды для всех путей проекта.

Все пути строятся по шаблонам с ${VAR} подстановкой из paths.env.
Никакой другой код не должен формировать пути к data/derived/runtime/ вручную.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol
from parsers.models import ConfigRegistryEntry


class PathManagerProtocol(Protocol):
    """Контракт PathManager. Реализация — PathManager."""

    def data_config_dir(self, name: str, version: str) -> Path: ...
    def data_hbk_dir(self, platform_version: str) -> Path: ...
    def derived_config_dir(self, name: str, version: str) -> Path: ...
    def derived_platform_dir(self, platform_version: str) -> Path: ...
    def unified_metadata_index(self, name: str, version: str) -> Path: ...
    def api_reference_index(self, name: str, version: str) -> Path: ...
    def call_graph_index(self, name: str, version: str) -> Path: ...
    def dependency_graph_index(self, name: str, version: str) -> Path: ...
    def platform_methods_db(self, platform_version: str) -> Path: ...
    def runtime_dir(self) -> Path: ...
    def config_registry_path(self) -> Path: ...
    def session_state_path(self) -> Path: ...
    def knowledge_base_dir(self) -> Path: ...

    def validate(self) -> dict[str, bool]: ...
    def freshness_check(self, name: str, version: str) -> dict[str, bool]: ...
    def ensure_dirs(self) -> None: ...


class PathManager:
    """Реализация PathManagerProtocol с ${VAR} подстановкой из paths.env."""

    def __init__(self, env_path: Path | None = None) -> None:
        """Загрузить переменные из paths.env (по умолчанию — корень проекта).

        paths.env содержит:
            DATA_DIR=./data
            DERIVED_DIR=./derived
            RUNTIME_DIR=./runtime
            KNOWLEDGE_BASE_DIR=./knowledge-base
            VENDOR_DIR=./vendor
        """
        env_path = env_path or Path.cwd() / "paths.env"
        self._env = self._load_env(env_path)
        self._project_root = env_path.parent

    def _load_env(self, env_path: Path) -> dict[str, str]:
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
        return env

    def _resolve(self, template: str, **kwargs: str) -> Path:
        """Подставить ${VAR} из env, затем {key} из kwargs."""
        # Сначала ${VAR} из env
        for key, value in self._env.items():
            template = template.replace(f"${{{key}}}", value)
        # Затем {kwarg} — в Path
        return self._project_root / template.format(**kwargs)

    # ─── data/ ────────────────────────────────────────────────────────────
    def data_config_dir(self, name: str, version: str) -> Path:
        return self._resolve("${DATA_DIR}/configs/{name}/{version}", name=name, version=version)

    def data_archive_path(self, archive_name: str) -> Path:
        return self._resolve("${DATA_DIR}/archives/{archive}", archive=archive_name)

    def data_hbk_dir(self, platform_version: str) -> Path:
        return self._resolve("${DATA_DIR}/hbk/{platform_version}", platform_version=platform_version)

    # ─── derived/ ─────────────────────────────────────────────────────────
    def derived_config_dir(self, name: str, version: str) -> Path:
        return self._resolve("${DERIVED_DIR}/configs/{name}/{version}", name=name, version=version)

    def derived_platform_dir(self, platform_version: str) -> Path:
        return self._resolve("${DERIVED_DIR}/platform/{platform_version}", platform_version=platform_version)

    def unified_metadata_index(self, name: str, version: str) -> Path:
        return self.derived_config_dir(name, version) / "unified-metadata-index.json"

    def api_reference_index(self, name: str, version: str) -> Path:
        return self.derived_config_dir(name, version) / "api-reference.json"

    def call_graph_index(self, name: str, version: str) -> Path:
        return self.derived_config_dir(name, version) / "call-graph.json"

    def dependency_graph_index(self, name: str, version: str) -> Path:
        return self.derived_config_dir(name, version) / "dependency-graph.json"

    def codebase_embeddings_dir(self, name: str, version: str) -> Path:
        """Qdrant snapshots для codebase-server."""
        return self.derived_config_dir(name, version) / "embeddings/"

    def platform_methods_db(self, platform_version: str) -> Path:
        return self.derived_platform_dir(platform_version) / "platform-methods.db"

    # ─── runtime/ ────────────────────────────────────────────────────────
    def runtime_dir(self) -> Path:
        return self._resolve("${RUNTIME_DIR}")

    def config_registry_path(self) -> Path:
        return self.runtime_dir() / "config-registry.json"

    def session_state_path(self) -> Path:
        return self.runtime_dir() / "session-state.json"

    def soul_path(self) -> Path:
        """Материализованный persona template (soul.template.md → soul.md)."""
        return self.runtime_dir() / "soul.md"

    def user_profile_path(self) -> Path:
        return self.runtime_dir() / "user-profile.md"

    def project_context_path(self) -> Path:
        return self.runtime_dir() / "project-context.md"

    def session_resume_path(self) -> Path:
        return self.runtime_dir() / "session-resume.md"

    def bsl_baseline_path(self, name: str, version: str) -> Path:
        """BSL LS baseline — известные ошибки, которые не блокируют."""
        return self.derived_config_dir(name, version) / "bsl-baseline.json"

    # ─── knowledge_base/ ──────────────────────────────────────────────────
    def knowledge_base_dir(self) -> Path:
        return self._resolve("${KNOWLEDGE_BASE_DIR}")

    def kb_index_path(self) -> Path:
        return self.knowledge_base_dir() / "index.json"

    def kb_patterns_dir(self) -> Path:
        return self.knowledge_base_dir() / "patterns"

    def kb_antipatterns_dir(self) -> Path:
        return self.knowledge_base_dir() / "antipatterns"

    def kb_prompts_dir(self) -> Path:
        return self.knowledge_base_dir() / "prompts"

    def kb_schemas_dir(self) -> Path:
        return self.knowledge_base_dir() / "schemas"

    # ─── vendor/ ──────────────────────────────────────────────────────────
    def vendor_dir(self) -> Path:
        return self._resolve("${VENDOR_DIR}")

    def bsl_parser_grammar_dir(self) -> Path:
        return self.vendor_dir() / "bsl-parser-grammar"

    # ─── валидация ────────────────────────────────────────────────────────
    def validate(self) -> dict[str, bool]:
        """Preflight check перед запуском pipeline.

        Возвращает карту {path_name: exists_bool}.
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

        True = индекс свежий (mtime source <= mtime index).
        False = устарел, требуется `1c-ai config build --force`.
        """
        result: dict[str, bool] = {}
        config_dir = self.data_config_dir(name, version)
        if not config_dir.exists():
            return {
                "unified_metadata": False,
                "api_reference": False,
                "call_graph": False,
                "dependency_graph": False,
            }

        # Самый свежий файл в data/configs/{name}/{version}/
        source_mtime = max(f.stat().st_mtime for f in config_dir.rglob("*") if f.is_file())

        for index_name, index_path in [
            ("unified_metadata", self.unified_metadata_index(name, version)),
            ("api_reference", self.api_reference_index(name, version)),
            ("call_graph", self.call_graph_index(name, version)),
            ("dependency_graph", self.dependency_graph_index(name, version)),
        ]:
            if not index_path.exists():
                result[index_name] = False
            else:
                result[index_name] = index_path.stat().st_mtime >= source_mtime
        return result

    def ensure_dirs(self) -> None:
        """Создать основные директории, если отсутствуют.

        Вызывается при `1c-ai init` и первом запуске.
        НЕ создаёт data/configs/ — они создаются при `config add`.
        """
        for path in [
            self._resolve("${DATA_DIR}/archives"),
            self._resolve("${DATA_DIR}/hbk"),
            self.runtime_dir(),
            self._resolve("${DERIVED_DIR}/platform"),
        ]:
            path.mkdir(parents=True, exist_ok=True)
```

## 3. `paths.env`

```env
# paths.env — переменные окружения для PathManager.
# Можно переопределить через реальные env vars (для CI/Docker).

DATA_DIR=./data
DERIVED_DIR=./derived
RUNTIME_DIR=./runtime
KNOWLEDGE_BASE_DIR=./knowledge-base
VENDOR_DIR=./vendor
```

Для CI/test:

```bash
# .github/workflows/test.yml
env:
  DATA_DIR: ${{ runner.temp }}/1c-ai-data
  DERIVED_DIR: ${{ runner.temp }}/1c-ai-derived
  RUNTIME_DIR: ${{ runner.temp }}/1c-ai-runtime
```

PathManager при загрузке `paths.env` отдаёт приоритет уже установленным env vars (через `os.environ`):

```python
def _load_env(self, env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    # OS env vars override paths.env
    for key in list(env.keys()):
        if key in os.environ:
            env[key] = os.environ[key]
    return env
```

## 4. `ConfigRegistry` — реестр конфигураций

```python
# packages/data_layer/src/data_layer/config_registry.py
"""ConfigRegistry — реестр загруженных конфигураций 1С.

Хранится в runtime/config-registry.json.
Каждая запись: ConfigRegistryEntry (из parsers.models).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from parsers.models import ConfigRegistryEntry


class ConfigRegistry:
    """Реестр конфигураций: add/list/get/remove."""

    def __init__(self, registry_path: Path) -> None:
        self._path = registry_path
        self._entries: dict[str, ConfigRegistryEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        data = json.loads(self._path.read_text(encoding="utf-8"))
        for entry_data in data.get("entries", []):
            entry = ConfigRegistryEntry.model_validate(entry_data)
            key = f"{entry.name}:{entry.version}"
            self._entries[key] = entry

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"entries": [e.model_dump(mode="json") for e in self._entries.values()]}
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def add(self, entry: ConfigRegistryEntry) -> None:
        key = f"{entry.name}:{entry.version}"
        self._entries[key] = entry
        self._save()

    def remove(self, name: str, version: str) -> bool:
        key = f"{name}:{version}"
        if key in self._entries:
            del self._entries[key]
            self._save()
            return True
        return False

    def get(self, name: str, version: str) -> ConfigRegistryEntry | None:
        return self._entries.get(f"{name}:{version}")

    def list(self) -> Iterable[ConfigRegistryEntry]:
        return self._entries.values()

    def update_freshness(self, name: str, version: str, is_fresh: bool) -> None:
        entry = self.get(name, version)
        if entry is None:
            return
        # frozen model → создаём новую с обновлённым полем
        updated = entry.model_copy(update={
            "is_fresh": is_fresh,
            "freshness_checked_at": datetime.now(timezone.utc),
        })
        self._entries[f"{name}:{version}"] = updated
        self._save()
```

## 5. `FreshnessCheck` — отдельная ответственность

```python
# packages/data_layer/src/data_layer/freshness.py
"""Freshness check — сравнение mtime(source) vs mtime(index).

Вынесено из PathManager в отдельный модуль для тестируемости.
PathManager делегирует сюда.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def latest_mtime(paths: Iterable[Path]) -> float | None:
    """Вернуть самый свежий mtime среди файлов. None — если файлов нет."""
    mtimes = [p.stat().st_mtime for p in paths if p.is_file()]
    return max(mtimes) if mtimes else None


def is_fresh(source_dir: Path, index_path: Path) -> bool:
    """Индекс свежий, если index_path существует и mtime(index) >= latest_mtime(source_dir)."""
    if not index_path.exists():
        return False
    source_mtime = latest_mtime(source_dir.rglob("*"))
    if source_mtime is None:
        return True  # нет исходников — индекс "свежий" по определению
    return index_path.stat().st_mtime >= source_mtime
```

## 6. Структура директорий — итоговая карта

```
1c-ai-agent/                          ← git root, paths.env здесь
├── paths.env                         ← конфигурация путей
│
├── data/                             ← gitignored, пользовательский ввод
│   ├── configs/
│   │   ├── ut11/4.5.3/              ← 1c-ai config add --name ut11 --version 4.5.3 --zip ut11.zip
│   │   │   ├── Configuration.xml
│   │   │   ├── Catalogs/
│   │   │   ├── Documents/
│   │   │   ├── CommonModules/
│   │   │   └── ...
│   │   └── erp/2.5.81/
│   ├── archives/                    ← ZIP архивы (для ре-экспорта)
│   │   ├── ut11-4.5.3.zip
│   │   └── erp-2.5.81.zip
│   └── hbk/
│       ├── 8.3.20/                  ← .hbk файлы синтакс-помощника
│       │   └── shcntx_ru/
│       └── 8.3.21/
│
├── derived/                          ← gitignored, сгенерированные индексы
│   ├── configs/
│   │   ├── ut11/4.5.3/
│   │   │   ├── unified-metadata-index.json    ← parsers/xml + indexers
│   │   │   ├── api-reference.json              ← parsers/bsl + indexers
│   │   │   ├── call-graph.json                 ← parsers/bsl + indexers
│   │   │   ├── dependency-graph.json           ← parsers/xml + indexers
│   │   │   ├── embeddings/                     ← Qdrant snapshot для codebase-server
│   │   │   └── bsl-baseline.json               ← BSL LS baseline (известные ошибки)
│   │   └── erp/2.5.81/
│   └── platform/
│       ├── 8.3.20/
│       │   └── platform-methods.db             ← SQLite из .hbk
│       └── 8.3.21/
│           └── platform-methods.db
│
├── runtime/                          ← gitignored, состояние сессий
│   ├── config-registry.json          ← ConfigRegistry (реестр конфигов)
│   ├── session-state.json            ← SessionManager (текущая сессия)
│   ├── soul.md                       ← материализованный persona
│   ├── user-profile.md
│   ├── project-context.md
│   └── session-resume.md
│
├── knowledge-base/                   ← в git, ревью через PR
│   ├── index.json                    ← реестр всех элементов
│   ├── schemas/                      ← JSON Schemas (Шаг 7)
│   ├── standards/                    ← СТО 1С, БСП, корпоративные
│   ├── patterns/                     ← YAML-эталоны
│   ├── antipatterns/                 ← YAML с detect-паттернами
│   ├── prompts/                      ← Jinja2 системные промпты
│   └── examples/                     ← .bsl файлы good/bad
│
├── vendor/                           ← git submodules
│   └── bsl-parser-grammar/           ← 1c-syntax/bsl-parser (LGPL-3.0)
│
└── packages/                         ← Python-пакеты (Шаг 1)
```

## 7. Контракт с другими слоями

### 7.1. CLI (`agent/cli_commands/config.py`)

```python
from data_layer import PathManager, ConfigRegistry

def cmd_config_add(name: str, version: str, zip_path: Path) -> None:
    pm = PathManager()
    registry = ConfigRegistry(pm.config_registry_path())

    target_dir = pm.data_config_dir(name, version)
    target_dir.mkdir(parents=True, exist_ok=True)
    _extract_zip(zip_path, target_dir)

    registry.add(ConfigRegistryEntry(
        name=name,
        version=version,
        title=None,
        added_at=datetime.now(timezone.utc),
        source_zip=str(zip_path),
        source_path=str(target_dir),
        index_path=str(pm.derived_config_dir(name, version)),
        freshness_checked_at=None,
        is_fresh=None,
    ))
```

### 7.2. MCP-сервер `metadata-server`

```python
# mcp_servers/metadata/server.py
from data_layer import PathManager

class MetadataServer:
    def __init__(self, pm: PathManager | None = None) -> None:
        self.pm = pm or PathManager()

    async def get_metadata(self, object_ref: str, config_name: str, config_version: str) -> dict:
        index_path = self.pm.unified_metadata_index(config_name, config_version)
        if not index_path.exists():
            return {"error": "Index not built. Run: 1c-ai config build --name <name>", "code": "INDEX_MISSING"}
        # ... чтение индекса, возврат метаданных
```

### 7.3. Orchestrator (preflight check)

```python
# orchestrator/graph.py
from data_layer import PathManager

def preflight_check(state: TaskState) -> TaskState:
    """Вызывается ПЕРВЫМ узлом в pipeline — проверяет, что данные готовы."""
    pm = PathManager()
    validation = pm.validate()
    missing = [k for k, v in validation.items() if not v]
    if missing:
        raise PreflightError(f"Missing paths: {missing}. Run: 1c-ai init")

    freshness = pm.freshness_check(state.config_name, state.config_version)
    stale = [k for k, v in freshness.items() if not v]
    if stale:
        raise IndexStaleError(f"Stale indexes: {stale}. Run: 1c-ai config build --name {state.config_name} --force")

    return state
```

## 8. Тесты

```python
# tests/data_layer/test_path_manager.py
import pytest
from pathlib import Path
from data_layer import PathManager, ConfigRegistry
from parsers.models import ConfigRegistryEntry
from datetime import datetime, timezone


@pytest.fixture
def tmp_paths(tmp_path: Path) -> PathManager:
    """PathManager с временными директориями."""
    env = tmp_path / "paths.env"
    env.write_text(f"""
DATA_DIR={tmp_path}/data
DERIVED_DIR={tmp_path}/derived
RUNTIME_DIR={tmp_path}/runtime
KNOWLEDGE_BASE_DIR={tmp_path}/kb
VENDOR_DIR={tmp_path}/vendor
""")
    return PathManager(env_path=env)


class TestPathManager:
    def test_config_dir_template(self, tmp_paths: PathManager):
        path = tmp_paths.data_config_dir("ut11", "4.5.3")
        assert path.name == "4.5.3"
        assert path.parent.name == "ut11"

    def test_validate_missing_dirs(self, tmp_paths: PathManager):
        result = tmp_paths.validate()
        assert result["data_dir"] is False
        assert result["runtime_dir"] is False

    def test_validate_after_ensure(self, tmp_paths: PathManager):
        tmp_paths.ensure_dirs()
        result = tmp_paths.validate()
        assert result["data_dir"] is True  # archives/ создан
        assert result["runtime_dir"] is True

    def test_freshness_check_missing_index(self, tmp_paths: PathManager):
        result = tmp_paths.freshness_check("ut11", "4.5.3")
        assert all(v is False for v in result.values())

    def test_freshness_check_fresh(self, tmp_paths: PathManager, monkeypatch):
        # Создаём исходник и индекс
        config_dir = tmp_paths.data_config_dir("ut11", "4.5.3")
        config_dir.mkdir(parents=True)
        (config_dir / "Configuration.xml").write_text("<root/>")
        index = tmp_paths.unified_metadata_index("ut11", "4.5.3")
        index.parent.mkdir(parents=True)
        index.write_text("{}")
        result = tmp_paths.freshness_check("ut11", "4.5.3")
        assert result["unified_metadata"] is True

    def test_env_override(self, tmp_path: Path, monkeypatch):
        """OS env vars переопределяют paths.env."""
        env = tmp_path / "paths.env"
        env.write_text("DATA_DIR=./default_data\n")
        monkeypatch.setenv("DATA_DIR", "/custom/data")
        pm = PathManager(env_path=env)
        assert "/custom/data" in str(pm.data_config_dir("x", "1"))


class TestConfigRegistry:
    def test_add_and_get(self, tmp_path: Path):
        registry = ConfigRegistry(tmp_path / "registry.json")
        entry = ConfigRegistryEntry(
            name="ut11",
            version="4.5.3",
            added_at=datetime.now(timezone.utc),
            source_path="/tmp/ut11",
            index_path="/tmp/ut11/index",
        )
        registry.add(entry)
        assert registry.get("ut11", "4.5.3") == entry

    def test_persistence(self, tmp_path: Path):
        path = tmp_path / "registry.json"
        registry = ConfigRegistry(path)
        entry = ConfigRegistryEntry(
            name="ut11",
            version="4.5.3",
            added_at=datetime.now(timezone.utc),
            source_path="/tmp/ut11",
            index_path="/tmp/ut11/index",
        )
        registry.add(entry)
        # Новый экземпляр читает тот же файл
        registry2 = ConfigRegistry(path)
        assert registry2.get("ut11", "4.5.3") is not None
```

## 9. Что НЕ делает PathManager

- **Не парсит XML/BSL** — это `parsers/`. PathManager только строит пути.
- **Не строит индексы** — это `parsers/indexers/`. PathManager только говорит, **куда** их положить.
- **Не запускает MCP-серверы** — это `mcp_servers/`. PathManager только передаётся им в конструктор.
- **Не хранит state LangGraph** — это `PostgresSaver` (Шаг 9). PathManager знает только про FS-пути.

## 10. Взаимосвязь с другими шагами

| Шаг | Связь с PathManager |
|---|---|
| Шаг 4 (Pipeline contracts) | `preflight_check` использует `PathManager.validate()` и `freshness_check()` |
| Шаг 5 (MCP tool contracts) | Каждый MCP-сервер принимает `PathManager` в конструктор |
| Шаг 7 (KB-as-code) | `kb-server` использует `pm.kb_*_dir()` для загрузки YAML |
| Шаг 8 (Facade) | `data_status` tool возвращает `PathManager.validate()` |
| Шаг 9 (Persistence) | `PostgresSaver` — отдельная ответственность, PathManager не трогает |

---

**Шаг 3 завершён.** Следующий — Шаг 4: центральный контракт — `TaskState` + node contracts (`PlanResult`, `GatherResult`, ...). Это самый важный шаг, от него зависят шаги 5, 6, 8.
