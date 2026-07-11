# 1C AI Assistant

> Multi-agent system for solving 1C:Enterprise 8.3 development tasks.
> Built on LangGraph orchestration with MCP tools, KB-as-code knowledge base,
> and deterministic validation gates.

**Status:** Architecture design complete (17 ADRs). Sprint 1 implementation in progress.

---

## Что это

`1c-ai-assistant` решает задачи разработки на платформе 1С:Предприятие 8.3:

1. Пользователь описывает задачу на естественном языке
2. Agent pipeline декомпозирует задачу на подзадачи
3. Для каждой подзадачи собирается минимально необходимый контекст
4. LLM генерирует BSL-код по собранному контексту
5. Сгенерированный код проходит детерминированный gate (BSL LS + KB-антипаттерны)
6. LLM-рецензент сверяет код с эталонами и решает: принять / доработать / эскалировать
7. Принятый код коммитится в ветку и открывается PR

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
├── tests/                   # тесты всех пакетов
├── scripts/                 # CI-утилиты
├── pyproject.toml           # uv workspace root
├── paths.env                # PathManager переменные
└── manifest.json            # внешние зависимости (Docker, submodules)
```

## Roadmap — 4 спринта MVP

| Спринт | Артефакт |
|---|---|
| 1 | `1c-ai config build` работает (parsers + PathManager + CLI) |
| 2 | `1c-ai generate` одной функцией (bsl_ls MCP + 4 узла + Coder) |
| 3 | Planner + Reviewer (KB-as-code + kb MCP + тесты) |
| 4 | Production-ready (metadata/codebase/git MCP + Facade + persistence) |

## Деплой — 3 контейнера

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

## Лицензия

MIT — см. [LICENSE](LICENSE).
