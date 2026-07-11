# Шаг 1 — Структура пакетов монорепы

> **ADR-0002:** Монорепа с uv workspace, 5 пакетов
> **Зависимости:** ADR-0001 (Python 3.12 + LangGraph)
> **Артефакт:** дерево `packages/`, `pyproject.toml` workspace, матрица зависимостей

## 1. Почему монорепа, а не multirepo

Альтернативы рассматривались:

1. **Multirepo** — отдельный git-репо для `parsers`, `orchestrator`, каждого MCP-сервера
2. **Монорепа с workspace** — один git, несколько Python-пакетов через `uv workspace`
3. **Один большой пакет** — всё в одном `pyproject.toml`

Multirepo отвергнут: solo-dev не потянет синхронизацию версий между 7+ репозиториями. Каждый кросс-репо change = coordination overhead. Для команды из 1 человека это критично.

Один большой пакет отвергнут: смешивает ответственности, не даёт независимо версионировать `parsers` (lib) и `orchestrator` (application). CI будет прогонять все тесты на каждое изменение, даже если тронули только `parsers`.

**Монорепа с uv workspace** даёт:
- единый git history (простота bisect)
- независимое версионирование пакетов через их `pyproject.toml`
- общие dev-зависимости (ruff, mypy, pytest) в корне
- `uv.lock` фиксирует целостный граф зависимостей
- atomic commits, затрагивающие несколько пакетов

## 2. Дерево пакетов

```
1c-ai-agent/                                ← git root
├── pyproject.toml                           ← workspace root (uv)
├── uv.lock                                  ← pinned deps, в git
├── paths.env                                ← PathManager переменные
├── manifest.json                            ← external deps (Docker images, submodules)
├── .gitmodules                              ← bsl-parser-grammar submodule
│
├── packages/                                ← 5 Python-пакетов
│   │
│   ├── parsers/                             ← Шаг 2: общие модели + парсеры
│   │   ├── pyproject.toml
│   │   └── src/parsers/
│   │       ├── __init__.py
│   │       ├── models/                      ← Pydantic v2 (BslModule, CatalogMeta, ...)
│   │       ├── xml/                         ← XML-парсеры 1С метаданных
│   │       ├── bsl/                         ← BSL-парсеры (tree-sitter + regex fallback)
│   │       │   └── sdbl/                    ← SDBL парсер (ANTLR4, generated)
│   │       ├── hbk/                         ← .hbk парсер синтакс-помощника
│   │       └── indexers/                    ← построение индексов
│   │
│   ├── data_layer/                          ← Шаг 3: PathManager + freshness
│   │   ├── pyproject.toml
│   │   └── src/data_layer/
│   │       ├── __init__.py
│   │       ├── path_manager.py              ← PathManager (единый источник путей)
│   │       ├── config_registry.py           ← ConfigRegistry (config-registry.json)
│   │       └── freshness.py                 ← Freshness check (mtime source vs index)
│   │
│   ├── mcp_servers/                         ← Шаг 5: 5 доменных MCP-серверов + Facade
│   │   ├── pyproject.toml
│   │   └── src/mcp_servers/
│   │       ├── __init__.py
│   │       ├── shared/                      ← общие контракты MCP (ToolContract Protocol)
│   │       │   └── protocol.py
│   │       ├── facade/                      ← Шаг 8: Agent-Facade (7 lifecycle tools)
│   │       │   ├── __init__.py
│   │       │   ├── handlers.py
│   │       │   └── server.py
│   │       ├── metadata/                    ← metadata-server (parsers.xml)
│   │       │   ├── __init__.py
│   │       │   ├── server.py
│   │       │   └── contracts.py             ← tool contracts
│   │       ├── codebase/                    ← codebase-server (parsers.bsl + Qdrant)
│   │       │   ├── __init__.py
│   │       │   ├── server.py
│   │       │   └── contracts.py
│   │       ├── kb/                          ← kb-server (parsers.hbk + KB-as-code)
│   │       │   ├── __init__.py
│   │       │   ├── server.py
│   │       │   └── contracts.py
│   │       ├── bsl_ls/                      ← bsl_ls-server (Java subprocess)
│   │       │   ├── __init__.py
│   │       │   ├── server.py
│   │       │   ├── contracts.py
│   │       │   └── Dockerfile               ← Java 17 + bsl-language-server
│   │       └── git/                         ← git-server (git CLI)
│   │           ├── __init__.py
│   │           ├── server.py
│   │           └── contracts.py
│   │
│   ├── orchestrator/                        ← Шаг 4, 6, 9: LangGraph pipeline
│   │   ├── pyproject.toml
│   │   └── src/orchestrator/
│   │       ├── __init__.py
│   │       ├── state.py                     ← TaskState, Subtask, Iteration (Шаг 4)
│   │       ├── contracts.py                 ← PlanResult, GatherResult, ... (Шаг 4)
│   │       ├── graph.py                     ← главный StateGraph (compile entry)
│   │       ├── nodes/                       ← узлы pipeline
│   │       │   ├── plan.py                  ← mini-supervisor subgraph
│   │       │   ├── gather.py                ← mini-supervisor subgraph
│   │       │   ├── code.py                  ← simple node
│   │       │   ├── validate.py              ← parallel subgraph
│   │       │   ├── review.py                ← mini-supervisor subgraph
│   │       │   └── commit.py                ← simple node
│   │       ├── routers.py                   ← route_after_validate, ... (детерминированные)
│   │       ├── tool_groups.py               ← TOOL_GROUPS registry (Шаг 6)
│   │       ├── tool_provider.py             ← ToolProvider (LangChain BaseTool adapter)
│   │       ├── errors.py                    ← AgentError taxonomy (Шаг 9)
│   │       └── persistence.py               ← PostgresSaver wrapper (Шаг 9)
│   │
│   └── agent/                               ← Шаг 8: CLI + entry points
│       ├── pyproject.toml
│       └── src/agent/
│           ├── __init__.py
│           ├── cli.py                       ← 1c-ai CLI (argparse)
│           ├── cli_commands/                ← подкоманды
│           │   ├── config.py                ← 1c-ai config add/build/list
│           │   ├── hbk.py                   ← 1c-ai hbk load
│           │   ├── generate.py              ← 1c-ai generate --task "..."
│           │   ├── mcp.py                   ← 1c-ai mcp serve [--server NAME]
│           │   └── deps.py                  ← 1c-ai deps check/update-submodules
│           └── api.py                       ← programmatic API (для REST API позже)
│
├── knowledge-base/                          ← Шаг 7: KB-as-code (в git, ревью через PR)
│   ├── index.json                           ← реестр всех элементов
│   ├── schemas/                             ← JSON Schemas для structured outputs
│   │   ├── antipattern.schema.json
│   │   ├── pattern.schema.json
│   │   ├── subtask.schema.json
│   │   └── code-output.schema.json
│   ├── standards/                           ← СТО 1С, БСП, корпоративные
│   ├── patterns/                            ← YAML-эталоны
│   │   ├── transaction-wrapper.yaml
│   │   └── posting-handler.yaml
│   ├── antipatterns/                        ← YAML с detect-паттернами
│   │   ├── query-in-loop.yaml
│   │   └── try-catch-silent.yaml
│   ├── prompts/                             ← Jinja2 системные промпты
│   │   ├── planner.system.j2
│   │   ├── coder.system.j2
│   │   └── reviewer.system.j2
│   └── examples/                            ← .bsl файлы good/bad
│
├── data/                                    ← gitignored, пользовательский ввод
│   ├── configs/{name}/{version}/            ← XML/BSL выгрузки
│   ├── archives/                            ← ZIP архивы
│   └── hbk/{platform_version}/              ← .hbk файлы
│
├── derived/                                 ← gitignored, сгенерированные индексы
│   ├── configs/{name}/{version}/
│   │   ├── unified-metadata-index.json
│   │   ├── api-reference.json
│   │   ├── call-graph.json
│   │   └── dependency-graph.json
│   └── platform/{version}/
│       └── platform-methods.db              ← SQLite из .hbk
│
├── runtime/                                 ← gitignored, состояние сессий
│   ├── session-state.json
│   ├── soul.md                              ← материализованный persona template
│   └── config-registry.json                 ← реестр загруженных конфигов
│
├── vendor/                                  ← git submodules (категория C)
│   └── bsl-parser-grammar/                  ← 1c-syntax/bsl-parser (LGPL-3.0)
│       └── src/grammar/SDBL.g4              ← источник для parsers/bsl/sdbl/generated/
│
├── adr/                                     ← Architecture Decision Records
│   ├── 0000-template.md
│   ├── 0001-language-and-framework.md
│   ├── 0002-monorepo-structure.md           ← этот шаг
│   └── ...
│
├── tests/                                   ← тесты всех пакетов
│   ├── parsers/
│   ├── data_layer/
│   ├── mcp_servers/
│   ├── orchestrator/
│   ├── snapshots/                           ← snapshot-тесты контрактов MCP
│   └── golden/                              ← golden-тесты pipeline
│
├── scripts/                                 ← thin CLI wrappers (без бизнес-логики)
│   ├── regenerate_sdbl.py                   ← .g4 → parsers/bsl/sdbl/generated/
│   └── check_deps.py                        ← CI: pip-upper-bounds, no-personal-forks
│
└── docs/                                    ← документация
    ├── architecture/                        ← эти документы
    └── 1c-xml-specs/                        ← спецификации XML-форматов 1С
```

## 3. Матрица зависимостей между пакетами

| Пакет | Зависит от | Назначение |
|---|---|---|
| `parsers` | (ничего, только pydantic, lxml, tree-sitter опц.) | Чистая lib, от неё зависят все |
| `data_layer` | `parsers` (использует `ConfigMeta` для registry) | Управление путями и индексами |
| `mcp_servers` | `parsers`, `data_layer` | Реализация MCP-серверов |
| `orchestrator` | `parsers`, `data_layer`, `mcp_servers` (контракты, не реализация) | LangGraph pipeline |
| `agent` | `orchestrator`, `mcp_servers.facade` | CLI + entry points |

**Принцип:** зависимость от `mcp_servers` в `orchestrator` — только от `mcp_servers.shared.protocol` (контракты), **не** от конкретных серверов. Orchestrator знает, что есть tool `metadata.get_metadata`, но не знает, в каком Docker-контейнере он живёт. Это позволяет тестировать orchestrator с mock-MCP-серверами.

## 4. Workspace root `pyproject.toml`

```toml
[project]
name = "1c-ai-agent-workspace"
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv.workspace]
members = [
    "packages/parsers",
    "packages/data_layer",
    "packages/mcp_servers",
    "packages/orchestrator",
    "packages/agent",
]

# Общие dev-зависимости (не дублируются в под-пакетах)
[tool.uv]
dev-dependencies = [
    "pytest>=8.0,<9.0",
    "pytest-cov>=4.0,<6.0",
    "pytest-asyncio>=0.23,<1.0",
    "hypothesis>=6.0,<7.0",
    "ruff>=0.5,<1.0",
    "mypy>=1.10,<2.0",
    "pytest-snapshot>=0.9,<1.0",  # snapshot-тесты контрактов MCP
]

[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "UP", "C4", "SIM"]
ignore = ["E501", "B008", "SIM117"]

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_any_generics = true
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = ["smoke: critical path tests"]
```

## 5. `pyproject.toml` для каждого пакета (примеры)

### `packages/parsers/pyproject.toml`

```toml
[project]
name = "parsers"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.5,<3.0",
    "lxml>=5.0,<6.0",
    "pyyaml>=6.0,<7.0",
]

[project.optional-dependencies]
ast = ["tree-sitter>=0.25,<1.0", "tree-sitter-bsl>=0.1,<1.0"]
sdbl = ["antlr4-python3-runtime>=4.13,<5.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/parsers"]
```

### `packages/orchestrator/pyproject.toml`

```toml
[project]
name = "orchestrator"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "langgraph>=0.2,<1.0",
    "langchain-core>=0.3,<1.0",
    "pydantic>=2.5,<3.0",
    "structlog>=24.0,<26.0",
    "jinja2>=3.1,<4.0",
    "parsers",
    "data_layer",
    "mcp_servers",
]

[project.optional-dependencies]
postgres = ["psycopg[binary]>=3.1,<4.0", "langgraph-checkpoint-postgres>=0.1,<1.0"]
langsmith = ["langsmith>=0.1,<1.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/orchestrator"]
```

### `packages/agent/pyproject.toml`

```toml
[project]
name = "agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "click>=8.1,<9.0",  # или argparse — TBD в шаге 8
    "orchestrator",
    "mcp_servers",
]

[project.scripts]
1c-ai = "agent.cli:main"
1c-ai-mcp = "mcp_servers.facade.server:run_sync"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agent"]
```

## 6. Что где живёт — карта артефактов

Чтобы каждый следующий шаг знал, куда класть контракты:

| Артефакт | Путь |
|---|---|
| `BslModule`, `CatalogMeta`, `Method` (Шаг 2) | `packages/parsers/src/parsers/models/` |
| `PathManager` (Шаг 3) | `packages/data_layer/src/data_layer/path_manager.py` |
| `TaskState`, `PlanResult` и др. (Шаг 4) | `packages/orchestrator/src/orchestrator/state.py`, `contracts.py` |
| `ToolContract` Protocol (Шаг 5) | `packages/mcp_servers/src/mcp_servers/shared/protocol.py` |
| MCP tool contracts (Шаг 5) | `packages/mcp_servers/src/mcp_servers/{server}/contracts.py` |
| `TOOL_GROUPS` (Шаг 6) | `packages/orchestrator/src/orchestrator/tool_groups.py` |
| KB YAML schemas (Шаг 7) | `knowledge-base/schemas/` |
| Facade handlers (Шаг 8) | `packages/mcp_servers/src/mcp_servers/facade/handlers.py` |
| `AgentError` taxonomy (Шаг 9) | `packages/orchestrator/src/orchestrator/errors.py` |
| `PostgresSaver` wrapper (Шаг 9) | `packages/orchestrator/src/orchestrator/persistence.py` |

## 7. Решения по структуре

### 7.1. Почему `parsers` — отдельный пакет, а не модуль `orchestrator.parsers`

`parsers` зависит только от pydantic/lxml/tree-sitter. Никакого LangGraph, MCP, агентов. Это **чистая lib**, которую можно:
- использовать вне агента (например, в CLI-утилите `1c-ai inspect`)
- тестировать в изоляции (без mocking LangGraph)
- версионировать независимо (bump parsers 0.1.0 → 0.2.0 без оркестратора)

Если бы `parsers` был внутри `orchestrator`, любой change в парсере требовал бы retest всего pipeline.

### 7.2. Почему `mcp_servers` — один пакет, а не 5

5 MCP-серверов имеют общий код:
- `shared/protocol.py` (`ToolContract` Protocol)
- `shared/auth.py` (caller_role проверка)
- общие тестовые утилиты

Раздельные пакеты создали бы 5 `pyproject.toml` с дублированием. Один пакет с подпакетами — проще. Серверы всё равно запускаются как отдельные процессы (разные entry points в `[project.scripts]`).

### 7.3. Почему `data_layer` — отдельный пакет, а не часть `parsers`

`PathManager` и `FreshnessCheck` — про файловую систему и state, не про парсинг. Если `parsers` начнёт знать про пути, его нельзя будет использовать как lib в других проектах. `data_layer` — тонкая прослойка над FS, использует `parsers.models.ConfigMeta` для registry, но не парсит сама.

### 7.4. Почему `agent` — отдельный пакет, а не часть `orchestrator`

`orchestrator` — это **библиотека пайплайна**. `agent` — **приложение** (CLI, точки входа). Разделение позволяет:
- использовать `orchestrator` как lib (например, в REST API без CLI)
- тестировать orchestrator без argparse
- иметь разные entry points (`1c-ai` CLI, `1c-ai-mcp` MCP server) в одном пакете

## 8. CI-проверки структуры

```yaml
# .github/workflows/structure-check.yml
- name: Verify workspace integrity
  run: |
    uv sync --all-extras
    uv run pytest tests/ -m smoke

- name: Verify no cross-package violations
  run: uv run python scripts/check_package_boundaries.py
  # Скрипт проверяет:
  # - parsers/ не импортирует из orchestrator/, mcp_servers/, data_layer/
  # - data_layer/ не импортирует из orchestrator/, mcp_servers/
  # - mcp_servers/ не импортирует из orchestrator/, agent/
  # - orchestrator/ импортирует из mcp_servers.shared.protocol, но НЕ из mcp_servers.{metadata,codebase,...}
  # - agent/ импортирует откуда угодно
```

Эти проверки гарантируют, что структура пакетов не разлагается со временем.

## 9. Что НЕ попало в структуру

- **`experimental/`** — нет. Если фича не готова, она не в репо. ADR-обоснование + branch.
- **`docs/architecture/`** — этот каталог, в git.
- **`.github/workflows/`** — CI, не пакет.
- **`docker/`** — только `docker-compose.yml` в корне + `Dockerfile` в `mcp_servers/bsl_ls/`.

---

**Шаг 1 завершён.** Следующий — Шаг 2: `parsers/models/` (общие Pydantic-модели), от которых зависят 4 из 5 пакетов.
