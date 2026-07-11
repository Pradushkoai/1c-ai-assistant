# 00 — Обзор архитектуры 1C-AI-Agent

> Самый высокий уровень. Детали — в документах 01-09.

## 1. Назначение системы

`1c-ai-agent` решает задачи разработки на платформе 1С:Предприятие 8.3. Типовой жизненный цикл:

1. Пользователь описывает задачу на естественном языке («добавь обработку проведения для документа Реализация»)
2. Агентский pipeline декомпозирует задачу на подзадачи
3. Для каждой подзадачи собирается минимально необходимый контекст (метаданные, похожий код, паттерны)
4. LLM генерирует BSL-код по собранному контексту
5. Сгенерированный код проходит детерминированный gate (BSL LS + KB-антипаттерны)
6. LLM-рецензент сверяет код с эталонами и решает: принять / доработать / эскалировать
7. Принятый код коммитится в ветку и открывается PR

Система НЕ заменяет 1С:Предприятие и НЕ запускает конфигурацию. Она работает с XML-выгрузкой и `.bsl`-файлами, используя BSL Language Server как детерминированный валидатор.

## 2. Шесть слоёв

```
┌─────────────────────────────────────────────────────────────┐
│ 1. ENTRY POINTS  (CLI · MCP-Facade · [позже REST, IDE])    │
├─────────────────────────────────────────────────────────────┤
│ 2. ORCHESTRATOR  (LangGraph, изолирован)                    │
│    Pipeline + mini-supervisor subgraphs                     │
│    TOOL_GROUPS registry                                     │
├─────────────────────────────────────────────────────────────┤
│ 3. MCP LAYER  (Facade + 5 доменных серверов)                │
│    metadata · codebase · kb · bsl_ls · git                  │
├─────────────────────────────────────────────────────────────┤
│ 4. PARSERS  (общая lib: xml · bsl · hbk · models · indexers)│
├─────────────────────────────────────────────────────────────┤
│ 5. DATA LAYER  (data/ → derived/ → runtime/ · PathManager)  │
├─────────────────────────────────────────────────────────────┤
│ 6. KNOWLEDGE LAYER  (YAML rules + MD docs · KB-as-code)     │
└─────────────────────────────────────────────────────────────┘
```

### Правило зависимостей

**Зависимость идёт только вниз.** Слой N знает о контрактах слоя N-1, но не наоборот. Конкретно:

- Entry points вызывают `orchestrator.run()` — не знают про MCP/parsers
- Orchestrator вызывает MCP-tools через `ToolProvider` — не знает про их реализацию
- MCP-серверы используют `parsers` напрямую (lib, не сервис)
- Parsers не зависит ни от кого выше себя — чистая библиотека
- Data Layer — файловая система + PathManager, не знает про агентов
- Knowledge Layer — файлы в git, ревью через PR

### Что НЕ входит в слои

- **CI/CD** — не слой, а свойство (workflows в `.github/`)
- **External dependencies** — не слой, а `pyproject.toml` + `manifest.json`
- **Docker-compose** — не слой, а deploy-артефакт

## 3. Точки входа

| Точка | Статус | Протокол | Назначение |
|---|---|---|---|
| CLI `1c-ai` | MVP спринт 1 | argparse → orchestrator | Основной интерфейс разработки, debug, CI |
| MCP-Facade | MVP спринт 1 | MCP stdio | Cursor/Claude/Codex — внешний клиент |
| REST API | Позже | HTTP/JSON | Web UI, интеграции |
| IDE-плагин | Позже | LSP/MCP | EDT/Cursor integration |

**Принцип:** CLI и MCP-Facade — тонкие presentation-слои. Оба вызывают один и тот же `orchestrator.run(task, config, ...) -> TaskResult`. Никакой бизнес-логики в entry points.

## 4. Agent pipeline (без Vanessa/EDT)

```
ENTRY
  │
  ▼
Plan (mini-supervisor subgraph)
  ├── plan_supervisor (LLM): структура подзадач
  ├── decompose (LLM, structured output)
  └── validate_plan (Python): проверка схемы
  │
  ▼  [для каждой подзадачи]
Gather (mini-supervisor subgraph)
  ├── gather_supervisor (LLM): какие MCP звать
  ├── fan_out (asyncio): metadata + codebase + kb
  └── merge_context (Python): сборка контекста
  │
  ▼
Code (simple node, LLM с structured_output)
  │
  ▼
Validate (parallel subgraph, без supervisor)
  ├── fan_out: bsl_ls.lint + kb.check_antipatterns
  └── fan_in: ValidationResult
  │
  ▼  ─── route_after_validate ───
  │         │                │
  │       passed           failed
  │         │                │
  │         ▼                ▼
  │      Review          Retry → Code (iteration++)
  │
  ▼
Review (mini-supervisor subgraph)
  ├── check_antipatterns (Python + YAML)
  ├── check_context (Python + platform-methods.db)
  └── decide (LLM, structured): proceed | retry | escalate
  │
  ▼  ─── route_after_review ───
  │      │          │              │
  │   proceed    retry         ≥3 critical
  │      │          │              │
  │      ▼          ▼              ▼
  │   Commit    Retry         Escalate
  │
  ▼
Commit (simple node, git MCP)
  │
  ▼
END (или следующая подзадача)
```

### Типы узлов

| Тип | Где используется | Что это |
|---|---|---|
| **Mini-supervisor subgraph** | Plan, Gather, Review | Subgraph с LLM-supervisor внутри |
| **Parallel subgraph** | Validate | Fan-out/fan-in без supervisor |
| **Simple agent node** | Code, Commit | Один LLM-вызов (Code) или один tool-вызов (Commit) |
| **Deterministic router** | route_after_validate, route_after_review, route_after_retry | Python-функция, не LLM |

### Роутеры — детерминированные

LLM **не может** пропустить валидацию. LLM **не может** сделать 4-ю итерацию. LLM **не может** решить «commit без review». Это железобетонно фиксируется в коде роутеров:

```python
def route_after_validate(state: TaskState) -> Literal["review", "retry"]:
    return "review" if state.validation_passed else "retry"

def route_after_review(state: TaskState) -> Literal["commit", "retry", "escalate"]:
    if state.review_passed: return "commit"
    if state.critical_findings >= 3: return "escalate"
    return "retry"

def route_after_retry(state: TaskState) -> Literal["code", "escalate"]:
    return "escalate" if state.current_iteration >= 3 else "code"
```

## 5. Фокус-контроль — 4 принципа

### 5.1. Контекстная изоляция

Каждый агент видит **только то, что ему нужно**:

- **Planner** — описание задачи + dep graph. **Не видит** BSL-код.
- **Gatherer** — определяет, какие MCP звать. **Не видит** промпт пользователя целиком.
- **Coder** — собранный контекст + DON'T list + pattern example. **Не видит** метаданные других объектов, не видит промпт.
- **Reviewer** — код + findings. **Не видит** исходный промпт.
- **Committer** — только git operations.

**Coder без MCP-инструментов — критично.** Если Coder может вызвать `semantic_search`, он начинает «исследовать» вместо генерации. Coder получает контекст от Gatherer и **только генерирует**.

### 5.2. Структурный контроль

- LangGraph StateGraph с детерминированными роутерами
- Max 3 итерации, потом escalate
- Каждый узел — типизированный contract (Pydantic v2)
- Checkpointer — рестарт с последнего состояния

### 5.3. Промптовый контроль

- Jinja2-шаблоны в `knowledge-base/prompts/` (не в коде)
- `with_structured_output()` — JSON по Pydantic-схеме
- Per-subtask DON'T list + MUST list + available_modules
- `constraints_reminder` — строка в state, добавляется в каждый промпт retry

### 5.4. Валидационный gate

- BSL LS (187 диагностик) + KB anti-patterns (детерминированные правила) — **необходмый** gate
- LLM не может пропустить — это следующий узел в графе
- Фидбек в retry — **только** failed_checks с конкретными строками, не «код плохой»

## 6. Внешние зависимости — 3 типа

| Тип | Что это | Где | Правила |
|---|---|---|---|
| **A** | Python-пакеты | `pyproject.toml` | upper bounds, `uv.lock` в git |
| **B** | Docker-сервисы | `manifest.json` | sha256 для pre-built, version-pinned (не `latest`) |
| **C** | Git-submodules | `.gitmodules` | pinned commit, upstream URL (не fork), CI-проверка |

**Запрещено:** personal forks без ADR-обоснования. Исключение — собственные upstream-репозитории автора (категория D, описывается явно).

## 7. Roadmap — 4 спринта MVP

| Спринт | Артефакт | Что строим |
|---|---|---|
| 1 | `1c-ai config build` работает | `parsers/`, PathManager, Data Layer, CLI config/hbk |
| 2 | `1c-ai generate` генерирует BSL одной функцией | `mcp_servers/bsl_ls/`, `orchestrator/` (4 узла), 1 агент (Coder), LangSmith |
| 3 | `1c-ai generate` с Planner + Reviewer | KB-as-code YAML, `mcp_servers/kb/`, snapshot-тесты, golden-тесты |
| 4 | Production-ready для внутреннего использования | `mcp_servers/{metadata,codebase,git}/`, Agent-Facade, session persistence |

Спринты 5-6 (optimization, dogfooding) — production hardening, не MVP.

## 8. Главный критерий эффективности

Если на вопрос **«какие данные видит Coder при решении подзадачи X?»** можно ответить однозначно, глядя на код — архитектура работает. Если ответ зависит от того, что LLM «решила» — архитектура сломана.

В этом дизайне ответ фиксирован:
- описание подзадачи (id, target_module, acceptance_criteria)
- собранный Gather'ом контекст (паттерн + похожий код + метаданные target-объекта + availability rules)
- DON'T list + MUST list + available_modules
- код предыдущей итерации + конкретные failed_checks (если retry)

**И больше ничего.** Это и есть фокус.
