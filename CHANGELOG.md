# Changelog

Все значимые изменения проекта [1C AI Assistant](https://github.com/Pradushkoai/1c-ai-assistant)
документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версионирование — [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

## [0.5.0] — 2026-07-13 — Stage 5 (Production Hardening) завершён

### Added — Stage 5 (4 задачи)

- **TD-S7-01: FacadeStateStore survival-restart** — `FacadeStateStore` через LangGraph
  checkpointer (aput/aget_tuple). State по plan_id переживает рестарт контейнера
  (PostgresSaver). In-memory fallback (backward compat). `_subtask_to_plan` cache.
  19 тестов (in-memory, mock checkpointer, survive-restart, TaskState round-trip).
  См. D-2026-07-13-13.
- **TD-S7-02: REST API HTTP server** — `1c-ai serve` (FastAPI :8000).
  GET /health (Docker/k8s probe), GET /servers, GET /tools/{server},
  POST /facade/{tool}, POST /domain/{server}/{tool}. Stateless через store.
  Dockerfile healthcheck обновлён (curl /health). 19 тестов. См. D-2026-07-13-14.
- **TD-S7-03: ZaiLLM mypy cleanup (TD-011)** — все 14 mypy ошибок закрыты
  (zai_llm.py, vector_store.py, form.py, library.py, codebase/server.py).
  **mypy: 0 ошибок** (TD-011 закрыт). См. D-2026-07-13-15.
- **TD-S7-04: CI integration + ruff format** — `ruff format` применён ко всем файлам
  (CI `--check` зелёный). integration.yml: `docker compose up --build`. 4 новых
  integration test (REST API smoke + FacadeStateStore survive-restart с Postgres).

### Changed

- **1032 теста** проходят + 14 skipped (было 991+12, +41 от Stage 5).
- **mypy: 0 ошибок** (TD-011 закрыт, было 14).
- **ruff check + format: чистые** (45 файлов отформатированы).
- **0 boundary violations**.
- **5 DECISIONS** (D-2026-07-13-13..15).

## [0.4.0] — 2026-07-13 — Stage 4 (Contract Compliance) завершён

### Added — Stage 4 (4 задачи)

- **TD-S6-01: metadata MCP server** — `MetadataServer` с 4 tools (get_metadata,
  get_form_structure, get_api_reference, get_dependency_graph). `gather_node` убран
  прямой FS-доступ, ходит через MCP (DI). `plan_node` — metadata_server DI
  (ADR-0005 compliance). Facade `run_cli` proxy поддерживает `metadata.*`.
  Архитектурный пробел #1 закрыт (ADR-0003/0005/0010). См. D-2026-07-13-10.
- **TD-S6-02: commit_node → git MCP** — `commit_node` переписан: real git flow
  (create_branch + commit + опц. open_pr через GitServer) если `git_server` +
  `1C_AI_REPO_PATH` заданы; fallback file save иначе. Facade `handle_review → proceed`
  реально коммитит. Архитектурный пробел #2 закрыт (ADR-0004/0005/0010). См. D-2026-07-13-11.
- **TD-S6-03: `1c-ai mcp serve` CLI + режим C** — `server_factory.py` единая factory
  для 6 серверов (facade/metadata/codebase/kb/bsl_ls/git). `1c-ai mcp serve --server NAME`
  (stdio). Cursor может подключиться к любому MCP напрямую (режим C, CONCEPTUAL §1.2).
  Архитектурный пробел #3 закрыт (ADR-0003). См. D-2026-07-13-12.
- **TD-S6-04: Integration tests + docs sync** — `tests/integration/` с smoke tests
  (Postgres, BSL LS, git, metadata). CI workflow обновлён (env vars + temp git repo).
  AGENTS.md, CHANGELOG.md, INTERNAL_ROADMAP.md, CONTRIBUTING.md актуализированы.

### Changed

- **991 тест** проходят + 12 skipped (было 921+7, +70 от Stage 4).
- **0 boundary violations** — mcp_servers НЕ импортирует agent (DI через kwargs).
- **mypy**: 14 ошибок (базовая TD-011, новых нет).
- **21 ADR** (было 19, +ADR-0020 embeddings strategy, +ADR-0021 будет в future).

## [0.3.0] — 2026-07-13 — Stage 3 (Production-readiness) завершён

### Added — Stage 3 (4 задачи)

- **TD-S5-01: PostgresSaver persistence** — `PersistenceManager` рабочая реализация
  (AsyncPostgresSaver + setup() + connection lifecycle). `schema_version` в TaskState
  (ADR-0018). Миграции: Alembic scaffolding + state-миграции. 21 unit + 3 integration
  тестов. См. D-2026-07-13-04, D-2026-07-13-05.
- **TD-S5-02: Facade handlers** — 8 lifecycle tools по ADR-0013 (plan/gather/generate/
  validate/review/explain/run_cli/data_status). FacadeHandlers с DI, MCP stdio server.
  См. D-2026-07-13-07.
- **TD-S5-03: git MCP** — GitServer с 4 tools (create_branch, commit, open_pr, diff)
  через async subprocess. Безопасность: branch/path validation, secrets scan (7 паттернов).
  См. D-2026-07-13-08.
- **TD-S5-04: Docker production** — multi-stage Dockerfile.app (builder + runtime,
  non-root user, OCI labels). `1c-ai health` CLI (persistence + BSL LS ping, JSON output).
  healthcheck в compose. `.env.example`. `docker-compose.override.yml` (dev hot reload).
  См. D-2026-07-13-09.

## [0.2.0] — 2026-07-13 — Этап 2 (Поиск и качество) завершён

### Added — Этап 2 (7 задач)

- **TD-S4.2-01**: ADR-0020 — гибридный BM25+pgvector+RRF, multilingual-e5-large 1024 dim.
- **TD-S4.2-02**: codebase MCP (4 tools: semantic_search, get_module, get_similar, call_graph).
- **TD-S4.2-03**: standards (8 YAML: 4 СТО + 4 БСП, 4-й валидатор).
- **TD-S4.2-04**: BSL LS Docker (multi-stage, HTTP API, healthcheck, .dockerignore).
- **TD-S4.2-05**: `1c-ai library add` (БСП/БПО индексация).
- **TD-S4.2-06**: transitive closure для Planner/Reviewer.
- **TD-S4.2-07**: api-reference в pipeline (Gatherer).

## [0.1.1] — 2026-07-12 — Этап 1 (Контекст для Coder) завершён

### Added — Этап 1 (5 задач)

- Form/Subsystem/Role парсеры (parsers/xml/)
- api-reference indexer (parsers/indexers/)
- call graph builder (parsers/bsl/)
- dependency graph builder (parsers/xml/dependency_graph.py)
- asyncio.TaskGroup в validate_node (4 параллельных валидатора)

## [0.1.0] — 2026-07-11

### Added

- **Архитектура**: 17 ADR (Architecture Decision Records), фиксирующих ключевые решения
- **Концептуальная архитектура** (`docs/architecture/CONCEPTUAL.md`) — обзор без кода
- **9 шагов проектирования** (`docs/architecture/01-09`) — детальные контракты с кодом

- **`packages/parsers/models/`** — 22 Pydantic v2 модели (frozen + extra=forbid + strict):
  - `ObjectRef`, `Version`, `ExecutionEnvironment`, `ContextAvailability`
  - `BslModule`, `Method`, `Region`, `MethodParameter`
  - `CatalogMetadata`, `DocumentMetadata`, `CommonModuleMetadata`, `FormMetadata`, `FormElement`
  - `PlatformMethod`, `PlatformProperty`
  - `ConfigMeta`, `VersionInfo`, `ConfigRegistryEntry`
  - `DependencyEdge`, `CallEdge`, `GraphStats`

- **`packages/data_layer/`**:
  - `PathManager` — единый источник правды для всех путей (ADR-0008), `${VAR}` подстановка из `paths.env`, OS env override
  - `ConfigRegistry` — реестр загруженных конфигураций с persistence в `runtime/config-registry.json`
  - `freshness.py` — `latest_mtime()`, `is_fresh()` функции

- **`packages/parsers/xml/`** — 4 парсера XML метаданных 1С:
  - `parse_configuration(path) → ConfigMeta`
  - `parse_catalog(path) → CatalogMetadata`
  - `parse_document(path) → DocumentMetadata`
  - `parse_common_module(path) → CommonModuleMetadata`
  - Универсальный парсер для остальных типов (Enum, InformationRegister, ...)
  - Namespace-agnostic XML helpers (`_xml_utils.py`) — все функции используют `local-name()` через `xpath()`

- **`packages/parsers/indexers/`**:
  - `build_metadata_index(config_dir, name, version) → dict` — сборка `unified-metadata-index.json`
  - `save_metadata_index`, `load_metadata_index`, `get_object_from_index`
  - Устойчивость к повреждённым XML (запись в `parse_errors`, не блокирует остальные)

- **`packages/agent/`** — CLI `1c-ai`:
  - `1c-ai init` — создание `data/`, `derived/`, `runtime/` директорий
  - `1c-ai config add --name X --version Y --zip Z.zip` — распаковка и регистрация
  - `1c-ai config build --name X` — построение индексов (`--force`, `--check-freshness`)
  - `1c-ai config list` — список конфигураций с fresh статусом
  - `1c-ai config remove` — удаление (`--yes`, `--keep-data`)
  - `1c-ai validate` — preflight check
  - `1c-ai hbk load --version 8.3.XX --path DIR` — минимальная загрузка .hbk (создаёт SQLite БД)
  - `--project / -p` параметр для указания корневой директории (env: `ONEC_AI_PROJECT`)

- **CI/CD**:
  - `.github/workflows/ci.yml` — lint (ruff + mypy) + boundary check + smoke tests + full tests with coverage
  - `.github/workflows/integration.yml` — nightly integration tests с Docker контейнерами

- **Тесты**: 344 теста (80 models + 90 data_layer + 106 parsers/xml + 35 indexers + 33 CLI)
  - Smoke, property-based (hypothesis), persistence round-trip, error handling, end-to-end

- **Test fixtures**: `tests/fixtures/mini_config/` — синтетическая 1С конфигурация (1 Catalog + 1 Document + 1 CommonModule), `mini_config.zip` для теста `config add`

- **`scripts/check_package_boundaries.py`** — CI-проверка границ пакетов

- **Docker setup**: 3-контейнерный деплой (app + bsl-ls + postgres/pgvector), `docker/postgres/init.sql` с pgvector и pg_trgm extensions

- **`AGENTS.md`** — правила для AI-агентов (Cursor, Claude, Codex)
- **`CONTRIBUTING.md`** — правила для контрибьюторов
- **`.gitignore`** — исключает `data/`, `derived/`, `runtime/`, `.github-token`, `.env`

### Architecture Decisions (ADR)

- **ADR-0001**: Python 3.12 + LangGraph 1.x (изолирован в `orchestrator/`)
- **ADR-0002**: Монорепа с uv workspace, 5 пакетов
- **ADR-0003**: MCP: Facade + 5 доменных серверов (EDT/Vanessa исключены)
- **ADR-0004**: Hierarchical orchestration (pipeline + mini-supervisor subgraphs)
- **ADR-0005**: TOOL_GROUPS registry с CI-проверкой
- **ADR-0006**: Data Layer: 4 слоя + PathManager
- **ADR-0007**: Pydantic v2 frozen models (frozen + extra=forbid + strict)
- **ADR-0008**: PathManager — единый источник путей
- **ADR-0009**: Pipeline contracts — центральный контракт
- **ADR-0010**: MCP tool contracts — двойной контракт
- **ADR-0011**: TOOL_GROUPS — декларативное распределение инструментов
- **ADR-0012**: KB-as-code — YAML + Markdown
- **ADR-0013**: Agent-Facade — 7 lifecycle tools
- **ADR-0014**: Error taxonomy + PostgresSaver
- **ADR-0015**: 3-container deployment (app + JVM + postgres/pgvector)
- **ADR-0016**: Финальная сверка концептуальной архитектуры
- **ADR-0017**: VectorStoreProtocol — pgvector по умолчанию, Qdrant как опция
