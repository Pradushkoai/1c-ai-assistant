# 1C-AI-Agent — Архитектурный каталог

> **Финальный набор архитектурных контрактов** для нового репозитория `1c-ai-agent`.
> Дата: 2026-07-11
> Статус: Active — основа для реализации спринтов 1-4

Этот каталог — **не код**, а **контракты**. Каждый документ фиксирует, как части системы договариваются между собой. Реализация начинается только после того, как все 9 контрактов зафиксированы.

---

## Структура каталога

```
1c-ai-agent-architecture/
├── README.md                       ← этот файл (индекс)
├── 00-overview.md                  ← общая архитектура (6 слоёв, зависимости)
│
├── 01-monorepo-structure.md        ← Шаг 1: структура пакетов
├── 02-pydantic-models.md           ← Шаг 2: общие модели (BslModule, CatalogMeta, ...)
├── 03-paths-protocol.md            ← Шаг 3: PathManager + data layer
├── 04-pipeline-contracts.md        ← Шаг 4: state + node contracts (ЦЕНТРАЛЬНЫЙ)
├── 05-mcp-tool-contracts.md        ← Шаг 5: контракты 19 MCP tools в 5 серверах
├── 06-tool-groups.md               ← Шаг 6: роли → tools (TOOL_GROUPS registry)
├── 07-kb-as-code.md                ← Шаг 7: формат KB (YAML + JSON Schema)
├── 08-agent-facade.md              ← Шаг 8: 7 lifecycle tools + _next_action
├── 09-error-taxonomy.md            ← Шаг 9: ошибки + persistence (PostgresSaver)
│
├── adr/                            ← 14 ADR (по одному на ключевое решение)
│   ├── README.md
│   ├── 0001-language-and-framework.md
│   ├── 0002-monorepo-structure.md
│   ├── 0003-mcp-architecture.md
│   ├── 0004-hierarchical-orchestration.md
│   ├── 0005-tool-groups-registry.md
│   ├── 0006-data-layer.md
│   ├── 0007-pydantic-models.md
│   ├── 0008-paths-protocol.md
│   ├── 0009-pipeline-contracts.md
│   ├── 0010-mcp-tool-contracts.md
│   ├── 0011-tool-groups-registry.md
│   ├── 0012-kb-as-code.md
│   ├── 0013-agent-facade.md
│   └── 0014-error-taxonomy.md
│
└── skeleton/                       ← заготовка кода (контракты как .py файлы)
    └── pyproject.toml              ← uv workspace root
```

**Объём:** ~8100 строк контрактов.

---

## Карта зависимостей между шагами

```
Шаг 1: Структура пакетов
  │
  ├─► Шаг 2: Pydantic-модели
  │     │
  │     └─► Шаг 3: Paths protocol
  │           │
  │           └─► Шаг 4: Pipeline contracts  ← центральный
  │                 │
  │                 ├─► Шаг 5: MCP tool contracts
  │                 │     │
  │                 │     └─► Шаг 6: TOOL_GROUPS
  │                 │           │
  │                 │           └─► Шаг 7: KB-as-code
  │                 │                   │
  │                 └───────────────────┤
  │                                     ▼
  └─────────────────────────────► Шаг 8: Agent-Facade
                                       │
                                       ▼
                                Шаг 9: Error taxonomy
```

**Принцип:** каждый шаг проектируется только после того, как зафиксированы его зависимости. Это гарантирует, что контракты стыкуются.

---

## Краткое содержание каждого шага

### Шаг 1 — Структура пакетов монорепы
5 пакетов в uv workspace: `parsers`, `data_layer`, `mcp_servers`, `orchestrator`, `agent`. Зависимости идут только вниз. CI-проверка границ пакетов.

### Шаг 2 — Общие Pydantic-модели
`parsers/models/` — самый нижний слой контрактов. Модели: `ObjectRef`, `BslModule`, `Method`, `CatalogMetadata`, `DocumentMetadata`, `FormMetadata`, `PlatformMethod`, `ConfigMeta`, `DependencyEdge`. Все frozen + extra=forbid + strict.

### Шаг 3 — PathManager + Data Layer
4 слоя FS: `data/` → `derived/` → `runtime/` → `knowledge-base/`. PathManager — единый источник путей с `${VAR}` подстановкой из `paths.env`. Freshness check: mtime(source) vs mtime(index).

### Шаг 4 — Pipeline state + node contracts
**Центральный контракт.** `TaskState` (frozen Pydantic), `Subtask`, `Iteration`, `FSMState` enum. Контракты узлов: `PlanResult`, `GatherResult`, `CodeResult`, `ValidateResult`, `ReviewResult`, `CommitResult`. 4 детерминированных роутера (НЕ LLM). Mini-supervisor subgraphs для Plan/Gather/Review. Parallel subgraph для Validate.

### Шаг 5 — MCP tool contracts
5 доменных MCP-серверов, 19 tools с `ToolContract` Protocol. Для каждого: `name`, `description`, `input_schema` (JSON Schema), `output_model` (Pydantic), `error_contract`, `timeout`, `idempotent`, `required_role`. Snapshot-тесты замораживают контракты.

### Шаг 6 — TOOL_GROUPS registry
Декларативное распределение `AgentRole → MCPServer → frozenset(tool_names)`. **Coder без инструментов** — главная защита от drift. `MULTI_ROLE_OK` для осознанных исключений. 3 CI-теста: no_orphan_tools, no_unexpected_multi_role, tool_provider_validates. `ToolProvider` — LangChain adapter с 2 уровнями изоляции (prompt + MCP).

### Шаг 7 — KB-as-code формат
YAML — для машины (детект + генерация промпта), Markdown — для человека. JSON Schema валидация при загрузке. Антипаттерн: `id`, `severity`, `detect` (regex/AST/bsl_ls_rule), `example_bad/good`, `recommendation_for_llm/reviewer`. Jinja2 системные промпты в `prompts/*.j2`.

### Шаг 8 — Agent-Facade lifecycle tools
7 lifecycle tools (`plan`, `gather`, `generate`, `validate`, `review`, `explain`, `run_cli`) + `data_status`. `_next_action` паттерн — каждый tool возвращает одно конкретное следующее действие. Внешний клиент (Cursor) идёт по рельсам. `run_cli` proxy — доступ к скрытым 19 tools с проверкой прав через TOOL_GROUPS.

### Шаг 9 — Error taxonomy + state persistence
Иерархия из 14 классов ошибок `AgentError` → `ToolError`/`LLMError`/... Каждая с `action: retry | escalate | abort`. `with_retry()` — единая retry-логика с exponential/linear backoff. `AsyncPostgresSaver` для checkpoint'ов. `error_handler` decorator оборачивает все узлы графа. `escalate_node` создаёт PR с меткой `needs-human-review`.

---

## ADR-каталог — 17 решений

| ADR | Тема | Статус |
|---|---|---|
| 0001 | Python 3.12 + LangGraph 1.x (изолирован) | Accepted |
| 0002 | Монорепа с uv workspace, 5 пакетов | Accepted |
| 0003 | MCP: Facade + 5 доменных серверов | Accepted |
| 0004 | Hierarchical orchestration (pipeline + subgraphs) | Accepted |
| 0005 | TOOL_GROUPS registry с CI-проверкой | Accepted |
| 0006 | Data Layer: 4 слоя + PathManager | Accepted |
| 0007 | Pydantic v2 frozen models | Accepted |
| 0008 | PathManager — единый источник путей | Accepted |
| 0009 | Pipeline contracts — центральный контракт | Accepted |
| 0010 | MCP tool contracts — двойной контракт | Accepted |
| 0011 | TOOL_GROUPS — декларативное распределение | Accepted |
| 0012 | KB-as-code — YAML + Markdown | Accepted |
| 0013 | Agent-Facade — 7 lifecycle tools | Accepted |
| 0014 | Error taxonomy + PostgresSaver | Accepted |
| 0015 | 3-container deployment (app + JVM + postgres/pgvector) | Accepted |
| 0016 | Финальная сверка концептуальной архитектуры (10 пунктов) | Accepted |
| 0017 | VectorStoreProtocol — pgvector по умолчанию, Qdrant как опция | Accepted |

---

## Как читать этот каталог

### Первое чтение (общее понимание)
1. `00-overview.md` — 6 слоёв, pipeline, фокус-контроль
2. `01-monorepo-structure.md` — где что живёт
3. Любой шаг по интересу

### Перед реализацией спринта N
- Прочитать шаги, которые этот спринт реализуют
- Прочитать соответствующие ADR
- Посмотреть skeleton/ для шаблона pyproject.toml

### При конфликте решений
- ADR-каталог — источник истины
- Шаги 1-9 — детализация контрактов
- Если нужны изменения — новый ADR с `supersedes`

---

## Roadmap реализации (4 спринта)

| Спринт | Артефакт | Какие шаги реализует |
|---|---|---|
| **1** | `1c-ai config build` работает | Шаг 1 (структура) + Шаг 2 (модели) + Шаг 3 (PathManager) + `parsers/xml` + `parsers/hbk` + `parsers/indexers` |
| **2** | `1c-ai generate` генерирует BSL одной функцией | Шаг 4 (pipeline) + Шаг 5 (`bsl_ls` server) + Шаг 6 (TOOL_GROUPS) + Шаг 9 (errors) + LangSmith |
| **3** | `1c-ai generate` с Planner + Reviewer | Шаг 7 (KB-as-code) + Шаг 5 (`kb` server) + snapshot-тесты + golden-тесты |
| **4** | Production-ready для внутреннего использования | Шаг 5 (`metadata`, `codebase`, `git` servers) + Шаг 8 (Facade) + session persistence |

Спринты 5-6 (optimization, dogfooding) — production hardening, не MVP.

---

## Главный критерий эффективности архитектуры

Если на вопрос **«какие данные видит Coder при решении подзадачи X?»** можно ответить однозначно, глядя на код — архитектура работает. Если ответ зависит от того, что LLM «решила» — архитектура сломана.

В этом дизайне ответ фиксирован:
- описание подзадачи (id, target_module, acceptance_criteria)
- собранный Gather'ом контекст (паттерн + похожий код + метаданные target-объекта + availability rules)
- DON'T list + MUST list + available_modules
- код предыдущей итерации + конкретные failed_checks (если retry)

**И больше ничего.** Это и есть фокус.

---

## Статус документов

Все документы — **Accepted**. Изменения только через новый ADR с `supersedes` ссылкой.

*Автор: архитектор проекта. Последнее обновление: 2026-07-11.*
