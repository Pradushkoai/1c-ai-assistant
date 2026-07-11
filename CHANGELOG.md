# Changelog

Все значимые изменения проекта [1C AI Assistant](https://github.com/Pradushkoai/1c-ai-assistant)
документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версионирование — [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

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
