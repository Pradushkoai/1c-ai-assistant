# Концептуальная архитектура 1C-AI-Agent (без кода)

> Документ верхнего уровня: сущности, взаимосвязи, принципы.
> Без имплементационных деталей. Для сверки с планом пользователя.
> Дата: 2026-07-11

---

## 1. Сущности системы

### 1.1. Слои (вертикальная декомпозиция)

| Слой | Назначение | Кто зависит от кого |
|---|---|---|
| **Entry Points** | Точки входа (CLI, MCP-Facade, потом REST/IDE) | Зависят от Orchestrator |
| **Orchestrator** | LangGraph pipeline, TOOL_GROUPS, роутеры | Зависит от MCP, Data, KB |
| **MCP Layer** | 4 доменных сервера + Facade | Зависят от Parsers, Data |
| **Parsers** | Чистая lib: xml/bsl/hbk/models/indexers | Не зависит ни от кого выше |
| **Data Layer** | FS + PathManager + ConfigRegistry | Зависит от Parsers (модели) |
| **Knowledge Layer** | YAML-правила + Jinja2 промпты | Не зависит ни от кого (файлы в git) |

**Правило:** зависимости идут только вниз. Слой N знает о контрактах слоя N-1, но не наоборот.

### 1.2. Агентные роли (горизонтальная декомпозиция)

| Роль | Когда работает | Что делает | Какие инструменты видит |
|---|---|---|---|
| **Planner** | В начале задачи | Декомпозирует задачу на подзадачи | metadata.get_dependency_graph, kb.search_kb |
| **Gatherer** | Перед каждой подзадачей | Собирает контекст: метаданные + похожий код + паттерны + availability | metadata (3 tools), codebase (3 tools), kb (2 tools) |
| **Coder** | Для каждой подзадачи | Генерирует BSL-код | **НИКАКИХ** — критично |
| **Validator** | После Coder | Детерминированный gate: BSL LS + антипаттерны | bsl_ls (2 tools), kb.check_antipatterns, kb.check_method_availability |
| **Reviewer** | После Validator | LLM-рецензент: proceed/retry/escalate | kb.get_antipattern, kb.check_antipatterns, codebase.get_similar |
| **Committer** | После Review (если proceed) | git branch + commit + PR | git (4 tools) |

**Всего: 19 инструментов в 5 MCP-серверах.**

### 1.3. Жизненный цикл задачи

```
TaskState (frozen, иммутабельный)
  ├── task_id, description, config, platform
  ├── subtasks: list[Subtask]              ← из Planner
  ├── current_subtask_idx
  ├── current_iteration (0..3, потом escalate)
  ├── iterations: list[Iteration]          ← история попыток
  ├── fsm_state: PLANNING | CODING | ... | DONE | ESCALATED
  └── validation_passed, review_passed, critical_findings
```

**Subtask** — единица работы: id, target_module, description, acceptance_criteria, constraints (DON'T/MUST/available_modules), max_iterations.

**Iteration** — одна попытка Coder'а: code, llm_response, failed_checks, edit_distance_vs_prev.

### 1.4. Внешние клиенты

3 режима работы:

| Режим | Кто | Что видит |
|---|---|---|
| **A. Полный агент** | CLI `1c-ai generate`, REST API | Весь pipeline за один вызов |
| **B. Умный Cursor** | Cursor/Claude через MCP-Facade | 7 lifecycle tools + `_next_action` |
| **C. Power-user** | Cursor напрямую к доменному MCP | Только выбранный сервер (например, bsl_ls для lint'а) |

**Facade = 7 lifecycle tools:**
1. `plan(task, config)` → plan_id + subtasks + _next_action=gather
2. `gather(plan_id, subtask_id)` → context_summary + _next_action=generate
3. `generate(plan_id, subtask_id)` → code + _next_action=validate
4. `validate(artifact_id)` → findings + _next_action=review или generate(retry)
5. `review(artifact_id)` → decision + _next_action=commit/generate/data_status
6. `explain(code_or_query)` → explanation (read-only)
7. `run_cli(tool_name, args)` → proxy к скрытым 12 tools (с проверкой прав)
+ `data_status()` → preflight check

---

## 2. Принципы взаимодействия

### 2.1. Иерархическая оркестрация (Hybrid)

**Верхний уровень** — детерминированный pipeline:
```
preflight → plan → gather → code → validate → review → commit
                                                  ↘ retry (max 3) → code
                                                  ↘ escalate → END
```

**Внутри Plan/Gather/Review** — mini-supervisor subgraph (LLM решает стратегию, Python валидирует).

**Внутри Validate** — parallel fan-out без supervisor (3 валидатора параллельно через asyncio.TaskGroup).

**Роутеры** — ТОЛЬКО Python-функции, не LLM:
- `route_after_validate` → review | retry
- `route_after_review` → commit | retry | escalate
- `route_after_retry` → code | escalate

**Ключевое правило:** LLM не может пропустить валидацию, не может сделать 4-ю итерацию, не может решить «commit без review».

### 2.2. Фокус-контроль (4 механизма)

#### Механизм 1: Контекстная изоляция
Каждый агент видит **только** нужные ему данные:
- Planner: описание задачи + dep graph. **Не видит** BSL-код.
- Gatherer: определяет, какие MCP звать. **Не видит** весь промпт пользователя.
- Coder: собранный контекст + DON'T list + pattern example. **Не видит** метаданные других объектов, не видит промпт.
- Reviewer: код + findings. **Не видит** исходный промпт.
- Committer: только git operations.

#### Механизм 2: TOOL_GROUPS
Декларативная таблица `AgentRole → MCPServer → frozenset(tool_names)`. Coder — пустое множество. 2 уровня изоляции: prompt-level (LLM видит только свои tools в system prompt) + MCP-level (каждый вызов проверяет caller_role). 3 CI-теста гарантируют консистентность.

#### Механизм 3: Промптовый контроль
- Jinja2-шаблоны в `knowledge-base/prompts/` (не в коде)
- `with_structured_output()` — JSON по Pydantic-схеме
- Per-subtask DON'T list + MUST list + available_modules
- `constraints_reminder` — строка в state, добавляется в каждый retry-промпт
- Retry-фидбек — **только** failed_checks, не весь код. Явное «не трогай остальное».

#### Механизм 4: Валидационный gate
BSL LS (187 диагностик) + KB антипаттерны (детерминированные правила) — необходмый gate. LLM не может пропустить — это следующий узел в графе.

### 2.3. Контракты между слоями

| Где | Что | Формат |
|---|---|---|
| Parsers → MCP/Orchestrator | Pydantic v2 frozen модели | `BslModule`, `CatalogMetadata`, ... |
| MCP tools → Orchestrator | Output модели | `GetMetadataOutput`, `LintOutput`, ... |
| Orchestrator узлы → узлы | Result типы | `PlanResult`, `GatherResult`, `CodeResult`, ... |
| Orchestrator → Checkpoint | TaskState | JSON через PostgresSaver |
| Facade → внешний клиент | Lifecycle tool responses | JSON с `_next_action` полем |
| KB → kb-server | YAML + JSON Schema | antipattern.yaml, pattern.yaml |

**Все контракты — Pydantic v2 + JSON Schema.** Snapshot-тесты замораживают. Любое изменение — через `--snapshot-update` + code review.

### 2.4. Управление ошибками

Иерархия из 14 классов `AgentError`. Каждая ошибка имеет `action: retry | escalate | abort`:

| Категория | Примеры | Action |
|---|---|---|
| Preflight | IndexStale, PreflightFailed | ABORT |
| Schema violation | LLM нарушила JSON Schema | RETRY |
| Tool errors | Timeout, Connection, Execution | RETRY (кроме RoleForbidden=ABORT, Execution=ESCALATE) |
| LLM errors | Unavailable, RateLimit, BudgetExceeded | RETRY или ESCALATE (бюджет) |
| Pipeline flow | ValidationFailed, ReviewRejected, MaxIterations | RETRY или ESCALATE |
| Persistence | PostgresSaver упал | ABORT |

`with_retry()` — единая retry-логика с exponential/linear backoff. При истощении retry → escalate.

`escalate_node` создаёт PR с меткой `needs-human-review`, body содержит причину, историю итераций, рекомендуемые действия.

### 2.5. Персистентность

- **TaskState** — `AsyncPostgresSaver` (LangGraph checkpoint'ы)
- **Configs registry** — `runtime/config-registry.json` (ConfigRegistry)
- **Session state** — `runtime/session-state.json` (SessionManager)
- **KB** — `knowledge-base/` в git, ревью через PR
- **Индексы** — `derived/` (gitignored), freshness check через mtime

Длинные задачи (>1 часа) переживают рестарт процесса — восстанавливаются с последнего checkpoint'а.

---

## 3. Поток решения задачи (end-to-end)

### 3.1. CLI режим (полный агент)

Пользователь:
```bash
1c-ai generate --task "Добавить обработку проведения для документа Реализация" \
               --config ut11 --version 4.5.3 --platform 8.3.20
```

Что происходит:

1. **Preflight** — PathManager.validate() + freshness_check(). Если индексы устарели — abort с подсказкой `1c-ai config build --force`.

2. **Plan subgraph** (mini-supervisor):
   - `plan_supervisor` (LLM) выбирает стратегию: feature → 4 подзадачи, refactor → 2, bugfix → 1
   - `decompose` (LLM с structured_output) генерирует Subtask[] по JSON Schema
   - `validate_plan` (Python) проверяет структуру: каждый Subtask имеет id, target_module, acceptance_criteria
   - Если невалидно —回到 supervisor с фидбеком (max 3 попытки)

3. **Для каждой подзадачи** (последовательно):
   
   a. **Gather subgraph** (mini-supervisor):
      - `gather_supervisor` (LLM) решает: какие MCP звать?
      - `fan_out` (asyncio.TaskGroup) параллельно: metadata + codebase + kb
      - `merge_context` (Python) собирает GatherResult с context_summary
      
   b. **Code node** (simple, LLM):
      - `with_structured_output(CodeResult)` по JSON Schema
      - System prompt: persona + role + DON'T/MUST + gathered context + (если retry) prev iteration.failed_checks
      - Coder **не имеет инструментов** — только генерация
      - Возвращает code + explanation + patterns_applied + antipatterns_avoided
   
   c. **Validate subgraph** (parallel, без supervisor):
      - `fan_out`: bsl_ls.lint + kb.check_antipatterns + kb.check_method_availability (параллельно)
      - `fan_in` (Python): собирает ValidateResult с findings, severity_breakdown, failed_checks
      - `validation_passed = (critical_findings == 0)`
   
   d. **`route_after_validate`** (Python):
      - passed → review
      - failed → retry
   
   e. **Review subgraph** (mini-supervisor):
      - `check_antipatterns` (Python + YAML)
      - `check_context` (Python + platform-methods.db)
      - `decide` (LLM с structured_output): proceed | retry | escalate
      - `critical_findings` счётчик
   
   f. **`route_after_review`** (Python):
      - review_passed → commit
      - critical_findings >= 3 → escalate
      - current_iteration >= max_iterations → escalate
      - иначе → retry
   
   g. **Если retry**: `retry_node` инкрементирует iteration, добавляет `constraints_reminder` с конкретными failed_checks, возвращается к Code node.
   
   h. **Если proceed** → **Commit node**:
      - git.create_branch
      - git.commit (с кодом последней итерации)
      - git.open_pr (с метаданными всех итераций в PR body)
   
   i. **`route_after_commit`**:
      - есть следующая подзадача → next_subtask → gather
      - иначе → END
   
   j. **Если escalate** → `escalate_node`:
      - создаёт PR с меткой `needs-human-review`
      - body: причина, история итераций, рекомендуемые действия
      - END

4. **Финал**: PR открыт, пользователь получает URL.

### 3.2. MCP-Facade режим (умный Cursor)

Тот же поток, но разбитый на 7 явных вызовов:

```
Cursor → data_status() → проверка готовности
Cursor → plan(task, config) → plan_id + subtasks + _next_action=gather
Cursor → gather(plan_id, subtask_id) → context + _next_action=generate
Cursor → generate(plan_id, subtask_id) → code + _next_action=validate
Cursor → validate(artifact_id) → findings + _next_action=review ИЛИ generate(retry)
Cursor → review(artifact_id) → decision + _next_action=commit/generate/data_status
                                                              ↓
                                                              если commit и есть след. подзадача → gather
                                                              если commit и нет → data_status (финал)
```

**`_next_action`** — одно конкретное действие, не workflow. LLM внешнего клиента идёт по рельсам.

### 3.3. Power-user режим

Cursor подключается напрямую к `bsl_ls` MCP:
```
Cursor → bsl_ls.lint(code="...") → diagnostics
```

Без pipeline, без агентов. Просто быстрый lint.

---

## 4. Структура данных и путей

### 4.1. 4 слоя файловой системы

```
data/          (gitignored) — пользовательский ввод
  ├── configs/{name}/{version}/    XML/BSL выгрузки
  ├── archives/                    ZIP архивы
  └── hbk/{platform_version}/      .hbk файлы

derived/       (gitignored) — сгенерированные индексы
  ├── configs/{name}/{version}/
  │   ├── unified-metadata-index.json
  │   ├── api-reference.json
  │   ├── call-graph.json
  │   ├── dependency-graph.json
  │   └── embeddings/                Qdrant snapshots
  └── platform/{version}/
      └── platform-methods.db        SQLite из .hbk

runtime/       (gitignored) — состояние сессий
  ├── config-registry.json
  ├── session-state.json
  └── soul.md, user-profile.md, ...

knowledge-base/  (в git) — KB-as-code, ревью через PR
  ├── schemas/                       JSON Schemas
  ├── patterns/*.yaml                эталоны
  ├── antipatterns/*.yaml            с detect-блоками
  ├── prompts/*.j2                   Jinja2 системные промпты
  ├── standards/                     СТО 1С, БСП
  └── examples/                      .bsl good/bad

vendor/        (git submodules)
  └── bsl-parser-grammar/            1c-syntax/bsl-parser (SDBL .g4)
```

### 4.2. PathManager — единый источник путей

Все пути строятся через PathManager. Никакой другой код не формирует пути к `data/`/`derived/`/`runtime/` вручную.

- `data_config_dir(name, version) -> Path`
- `unified_metadata_index(name, version) -> Path`
- `validate() -> {path: exists_bool}` — preflight
- `freshness_check(name, version) -> {index: is_fresh}` — mtime source vs index

Конфигурация через `paths.env` (5 переменных). OS env vars переопределяют (для CI/Docker).

---

## 5. Внешние зависимости — 3 типа

| Тип | Что | Где | Правила |
|---|---|---|---|
| **A** | Python-пакеты | `pyproject.toml` | upper bounds, `uv.lock` в git |
| **B** | Docker-сервисы | `manifest.json` | sha256 для pre-built, version-pinned |
| **C** | Git-submodules | `.gitmodules` | pinned commit, upstream URL |

**Запрещено:** personal forks без ADR-обоснования.

### Конкретные зависимости

**Тип A (Python):**
- Обязательные: pydantic v2, langgraph, langchain-core, mcp, networkx, structlog, lxml, jinja2, httpx, pyyaml
- Опциональные (extras): tree-sitter-bsl (AST), antlr4 (SDBL), qdrant-client+fastembed (vector), fastapi+uvicorn (REST)

**Тип B (Docker):**
- `qdrant/qdrant:vX.Y.Z` (sha256) — для codebase-server
- `1c-syntax/bsl-ls:vX.Y.Z` (sha256) — для bsl_ls-server, Java 17

**Тип C (Submodule):**
- `1c-syntax/bsl-parser` (LGPL-3.0) — SDBL .g4 → `parsers/bsl/sdbl/generated/`

---

## 6. 14 ADR — ключевые решения

| # | Решение | Дата |
|---|---|---|
| 0001 | Python 3.12 + LangGraph 1.x (изолирован в orchestrator/) | 2026-07-11 |
| 0002 | Монорепа с uv workspace, 5 пакетов | 2026-07-11 |
| 0003 | MCP: Facade + 5 доменных серверов (EDT/Vanessa исключены) | 2026-07-11 |
| 0004 | Hierarchical orchestration (pipeline + mini-supervisor subgraphs) | 2026-07-11 |
| 0005 | TOOL_GROUPS registry с CI-проверкой | 2026-07-11 |
| 0006 | Data Layer: 4 слоя + PathManager | 2026-07-11 |
| 0007 | Pydantic v2 frozen models | 2026-07-11 |
| 0008 | PathManager — единый источник путей | 2026-07-11 |
| 0009 | Pipeline contracts — центральный контракт | 2026-07-11 |
| 0010 | MCP tool contracts — двойной контракт | 2026-07-11 |
| 0011 | TOOL_GROUPS — декларативное распределение | 2026-07-11 |
| 0012 | KB-as-code — YAML + Markdown | 2026-07-11 |
| 0013 | Agent-Facade — 7 lifecycle tools | 2026-07-11 |
| 0014 | Error taxonomy + PostgresSaver | 2026-07-11 |

---

## 7. Roadmap — 4 спринта MVP

| Спринт | Артефакт | Что строим |
|---|---|---|
| **1** | `1c-ai config build` работает | Структура пакетов + parsers (xml+hbk) + PathManager + CLI config/hbk + индексы |
| **2** | `1c-ai generate` генерирует BSL одной функцией | bsl_ls MCP + orchestrator (4 узла: gather→code→validate→retry) + 1 агент (Coder) + LangSmith |
| **3** | `1c-ai generate` с Planner + Reviewer | KB-as-code YAML + kb MCP + snapshot-тесты + golden-тесты |
| **4** | Production-ready для внутреннего использования | metadata/codebase/git MCP + Agent-Facade (7 tools) + session persistence |

Спринты 5-6 (optimization, dogfooding) — production hardening, не MVP.

---

## 8. Главный критерий эффективности

Если на вопрос **«какие данные видит Coder при решении подзадачи X?»** можно ответить однозначно, глядя на код — архитектура работает.

Ответ в нашем дизайне фиксирован:
- описание подзадачи (id, target_module, acceptance_criteria)
- собранный Gather'ом контекст (паттерн + похожий код + метаданные target-объекта + availability rules)
- DON'T list + MUST list + available_modules
- код предыдущей итерации + конкретные failed_checks (если retry)

**И больше ничего.** Никакого «Coder может поискать в кодовой базе». Никакого «Coder может посмотреть метаданные других объектов». Это и есть фокус.

---

## 9. Что отличается от первоначального плана пользователя

| Пункт плана | Решение | Почему |
|---|---|---|
| 6 MCP-серверов + Facade | **5 MCP + Facade** | EDT и Vanessa исключены (решение пользователя 2026-07-11) — не оправдано для solo-dev |
| Спринт 1: parsers + data layer | Сохранили без изменений | Правильно |
| Спринт 2: BSL-LS MCP + minimal pipeline | Сохранили без изменений | Правильно |
| Vanessa в спринте 5 | **Убран** | Исключена из архитектуры |
| EDT в спринт 5 | **Убран** | Исключён из архитектуры |
| Спринт 5: Git MCP + Facade | Перенесён в спринт 4 | Без EDT/Vanessa спринт 5 стал пустым,логично сжать до 4 |
| Спринт 6: optimization + dogfooding | Оставлен как post-MVP | Не критично для MVP |
| Qdrant для vector search | **pgvector** (в postgres) | Для нашего масштаба (<100k векторов) pgvector достаточен, меньше инфры (ADR-0015) |
| SQLite для MVP | **Postgres с самого начала** | Контейнер postgres уже нужен для pgvector, плюс multi-process готовность (ADR-0015) |
| 1 контейнер с Java+Python | **3 контейнера** | Пользователь требует полный гибридный search с начала; Java изоляция критична (ADR-0015) |
| Все остальные принципы | Сохранили | Hierarchical, TOOL_GROUPS, KB-as-code, 6 слоёв фокус-контроля (сжали до 4 ключевых), Pydantic v2 State |

**Существенных отклонений от плана пользователя нет.** Удаление EDT/Vanessa, сжатие roadmap 6→4 спринта, выбор pgvector+Postgres вместо Qdrant+SQLite — всё согласовано с пользователем.

---

## 10. Деплой (3 контейнера, ADR-0015)

```
┌────────────────────────────────────────────────────────────┐
│  1c-ai-app (Python, ~180 МБ)                               │
│  ├── Facade MCP (stdio, для Cursor)                        │
│  ├── metadata MCP (in-process)                            │
│  ├── codebase MCP (in-process, postgres+pgvector client)   │
│  ├── kb MCP (in-process)                                   │
│  ├── bsl_ls MCP (in-process, HTTP client → bsl-ls:8080)    │
│  ├── git MCP (in-process, subprocess git CLI)              │
│  └── orchestrator (LangGraph, PostgresSaver)               │
└────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
┌──────────────────────────┐  ┌──────────────────────────────┐
│  1c-ai-bsl-ls            │  │  postgres (pgvector/pg16)    │
│  (Python + JVM, ~350 МБ) │  │  (~400 МБ)                   │
│  ├── HTTP server :8080   │  │  ├── pgvector (embeddings)   │
│  ├── POST /lint          │  │  ├── pg_trgm (триграммы)     │
│  ├── POST /format        │  │  ├── tsvector + GIN (BM25)   │
│  └── Java 17 long-running│  │  ├── checkpoints (LangGraph) │
│     bsl-ls.jar           │  │  └── bsl_modules (full-text  │
└──────────────────────────┘  │      + vector)               │
                              └──────────────────────────────┘
```

### Гибридный search в codebase MCP

1. **BM25** — postgres tsvector + GIN index (лексический)
2. **Vector** — pgvector cosine similarity (семантический)
3. **Reranker** — RRF (Reciprocal Rank Fusion) объединяет оба

Находит и `ОбработкаПроведения` по точному имени, и модуль про «движения по регистру» по семантике.

### Что НЕ меняется в архитектуре от 3-контейнерного деплоя

- 5 MCP-серверов как логические контракты — без изменений
- TOOL_GROUPS — без изменений
- Pipeline contracts — без изменений
- Facade lifecycle tools — без изменений
- KB-as-code — без изменений
- Error taxonomy — без изменений

**Меняется только implementation detail в 2 файлах:**
- `mcp_servers/bsl_ls/server.py` — HTTP client вместо subprocess
- `mcp_servers/codebase/server.py` — postgres+pgvector вместо Qdrant client

### VectorStoreProtocol (ADR-0017) — гибридный подход

Vector store для codebase-server не зафиксирован жёстко. Через `VectorStoreProtocol` реализованы 2 backend'а:

| Backend | Контейнеров | Когда использовать |
|---|---|---|
| `PgVectorStore` (по умолчанию) | 3 | MVP, <100k векторов, меньше инфры |
| `QdrantVectorStore` (опционально) | 4 | Если бенчмарк покажет, что pgvector даёт recall <95% |

Переключение — 1 env var: `VECTOR_STORE=pgvector|qdrant`.

**Бенчмарк-тест в спринте 4** объективно сравнивает оба backend'а на 100 тестовых запросах. Если Qdrant даёт recall@10 > pgvector + 3% — переключаем дефолт.

Это гарантирует, что мы **не пошли по пути ухудшения качества** — решение основано на измерении, не на вере.
