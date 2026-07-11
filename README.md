# 1C AI Assistant

> Multi-agent system for solving 1C:Enterprise 8.3 development tasks.
> Built on LangGraph orchestration with MCP tools, KB-as-code knowledge base,
> and deterministic validation gates.

**Status:** Sprint 1 complete — `1c-ai config build` works end-to-end. 344 tests passing.

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/Pradushkoai/1c-ai-assistant.git
cd 1c-ai-assistant
uv sync --all-extras --all-packages

# 2. Initialize project structure (creates data/, derived/, runtime/)
uv run 1c-ai init

# 3. Add a 1C configuration from ZIP export
uv run 1c-ai config add --name ut11 --version 4.5.3 --zip ut11.zip

# 4. Build metadata index
uv run 1c-ai config build --name ut11

# 5. List configurations (shows freshness status)
uv run 1c-ai config list

# 6. Validate environment
uv run 1c-ai validate
```

Для работы в другой директории (не в корне репозитория):

```bash
uv run 1c-ai --project /path/to/project init
uv run 1c-ai --project /path/to/project config add --name X --version Y --zip Z.zip
```

Или через env var: `export ONEC_AI_PROJECT=/path/to/project`

## Что это

`1c-ai-assistant` решает задачи разработки на платформе 1С:Предприятие 8.3:

1. Пользователь описывает задачу на естественном языке
2. Agent pipeline декомпозирует задачу на подзадачи
3. Для каждой подзадачи собирается минимально необходимый контекст
4. LLM генерирует BSL-код по собранному контексту
5. Сгенерированный код проходит детерминированный gate (BSL LS + KB-антипаттерны)
6. LLM-рецензент сверяет код с эталонами и решает: принять / доработать / эскалировать
7. Принятый код коммитится в ветку и открывается PR

**Текущий статус (Sprint 1):** загрузка и индексация 1С конфигураций работает. Генерация кода — в Sprint 2.

## Архитектура — 6 слоёв

```
1. Entry Points  (CLI · MCP-Facade · [позже REST/IDE])
2. Orchestrator  (LangGraph pipeline + TOOL_GROUPS + роутеры)
3. MCP Layer     (Facade + 5 доменных серверов)
4. Parsers       (lib: xml · bsl · hbk · models · indexers)
5. Data Layer    (FS + PathManager + ConfigRegistry)
6. Knowledge     (YAML rules + Markdown docs, KB-as-code)
```

Зависимости идут только вниз. См. [docs/architecture/CONCEPTUAL.md](docs/architecture/CONCEPTUAL.md).

## Ключевые принципы

- **Hierarchical orchestration** — детерминированный pipeline + mini-supervisor subgraphs
- **LLM не может пропускать этапы** — роутеры на Python, не на LLM
- **Coder без инструментов** — главный принцип фокус-контроля
- **KB-as-code** — YAML-правила ревьюятся через PR
- **Hybrid search** — BM25 (tsvector) + vector (pgvector/Qdrant) + RRF reranker

## CLI команды

| Команда | Что делает |
|---|---|
| `1c-ai init` | Создать `data/`, `derived/`, `runtime/` директории |
| `1c-ai config add --name X --version Y --zip Z.zip` | Распаковать ZIP и зарегистрировать конфигурацию |
| `1c-ai config build --name X` | Построить `unified-metadata-index.json` |
| `1c-ai config build --name X --check-freshness` | Проверить свежесть индексов |
| `1c-ai config build --name X --force` | Принудительно перестроить индексы |
| `1c-ai config list` | Показать загруженные конфигурации |
| `1c-ai config remove --name X --version Y --yes` | Удалить конфигурацию |
| `1c-ai validate` | Preflight check окружения |
| `1c-ai hbk load --version 8.3.20 --path DIR` | Загрузить .hbk файлы (минимальная версия) |

## Структура репозитория

```
1c-ai-assistant/
├── packages/                # uv workspace (5 Python-пакетов)
│   ├── parsers/             # чистая lib (xml/bsl/hbk/models/indexers)
│   ├── data_layer/          # PathManager + ConfigRegistry
│   ├── mcp_servers/         # 5 доменных MCP + Facade
│   ├── orchestrator/        # LangGraph pipeline
│   └── agent/               # CLI + entry points
├── adr/                     # 17 Architecture Decision Records
├── docs/architecture/       # архитектурные документы
├── knowledge-base/          # KB-as-code (YAML + Markdown)
├── docker/                  # Dockerfile'ы + postgres init
├── tests/                   # тесты всех пакетов (344 теста)
├── scripts/                 # CI-утилиты
├── pyproject.toml           # uv workspace root
├── paths.env                # PathManager переменные
└── manifest.json            # внешние зависимости (Docker, submodules)
```

## Roadmap — 4 спринта MVP

| Спринт | Артефакт | Статус |
|---|---|---|
| 1 | `1c-ai config build` работает (parsers + PathManager + CLI) | ✅ Complete |
| 2 | `1c-ai generate` одной функцией (bsl_ls MCP + 4 узла + Coder) | Planned |
| 3 | Planner + Reviewer (KB-as-code + kb MCP + тесты) | Planned |
| 4 | Production-ready (metadata/codebase/git MCP + Facade + persistence) | Planned |

См. [CHANGELOG.md](CHANGELOG.md) для деталей по версиям.

## Деплой — 3 контейнера (Sprint 4+)

| Контейнер | Что | Размер |
|---|---|---|
| `1c-ai-app` | Python: orchestrator + 4 MCP in-process + Facade | ~180 МБ |
| `1c-ai-bsl-ls` | Python + JVM: BSL LS HTTP API, always-running | ~350 МБ |
| `postgres` | pgvector/pg16: persistence + vector search | ~400 МБ |

См. [ADR-0015](adr/0015-deployment-strategy.md) и [ADR-0017](adr/0017-vector-store-protocol.md).

## Технологии

- **Python 3.12**, **LangGraph 1.x**, **Pydantic v2**
- **PostgreSQL 16** + pgvector + pg_trgm
- **BSL Language Server** (Java 17) — 187 диагностик
- **MCP SDK** (Model Context Protocol)
- **uv** для dependency management
- **Docker Compose** для деплоя

## Документация

- [Концептуальная архитектура](docs/architecture/CONCEPTUAL.md) — обзор без кода
- [ADR-каталог](adr/README.md) — 17 архитектурных решений
- [Структура монорепы](docs/architecture/01-monorepo-structure.md)
- [Pipeline contracts](docs/architecture/04-pipeline-contracts.md) — центральный контракт
- [CHANGELOG.md](CHANGELOG.md) — история изменений
- [CONTRIBUTING.md](CONTRIBUTING.md) — для контрибьюторов
- [AGENTS.md](AGENTS.md) — правила для AI-агентов

## Лицензия

MIT — см. [LICENSE](LICENSE).
