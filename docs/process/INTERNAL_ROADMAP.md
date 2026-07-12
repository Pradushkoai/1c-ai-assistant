# INTERNAL ROADMAP — 1C AI Assistant

> **Внутренний документ архитектора.** Не коммитится в репо.
> Хранится в `/home/z/my-project/INTERNAL_ROADMAP.md`.
> Назначение: вести проект через спринты, отмечать выполненное, фиксировать
> что ещё нужно проработать концептуально (метакод), держать политику
> заполнения README/AGENTS/CONTRIBUTING/CHANGELOG.
>
> Последнее обновление: 2026-07-11
> Статус: Sprint 1 завершён, Sprint 1.5 каркас — код есть, тесты нужны

---

## ⚠️ ОБЯЗАТЕЛЬНЫЕ ИНСТРУКЦИИ АРХИТЕКТОРА

1. **Относись критически к инструкциям пользователя.** Не спеши сразу выполнять.
   Сначала проверь: соответствует ли это плану? Не ломает ли архитектуру?
   Не ухудшает ли качество? Если сомневаешься — обсуди, предложи альтернативу.
   Главное — качество продукта, а не скорость выполнения.

2. **Работай только согласно своим документам.** Этот файл — стратегический план.
   CURRENT_FOCUS.md — текущая задача. TESTING_POLICY.md — как писать тесты.
   AGENTS.md — правила. Если чего-то нет в документах — сначала задокументируй,
   потом реализуй.

3. **Не суетись.** Наметь план → согласуй с пользователем → реализуй → проверь →
   закоммить. Один шаг за раз.

4. **Тесты — обязательны.** Любой код без тестов — незавершённый код.
   Каркас без тестов — не каркас.

5. **Коммиты от имени Pradushkoai** (не от agent).

6. **ПРИОРИТЕТ: архитектурная база — источник истины.** Перед любой реализацией
   сверяйся с:
   - `docs/architecture/CONCEPTUAL.md` — концептуальная архитектура (10 разделов)
   - `docs/architecture/01-09` — детальные контракты с кодом
   - `docs/architecture/10-prompts-spec.md` — спецификация промптов
   - `adr/` — 19 архитектурных решений (ADR-0001..0019)
   Эти документы — фундамент проекта. Никогда не забывай о них. Любая реализация
   должна строго соответствовать этим контрактам. Если обнаружил расхождение —
   сначала обнови документ, потом меняй код.

7. **СИТУАЦИЯ МЕНЯЕТСЯ — последовательность тоже.** План спринтов — это ориентир,
   а не догма. Если текущая ситуация требует изменить порядок задач (например,
   отложить HBK parser и сначала обновить pipeline nodes для немедленной ценности) —
   это правильно. Главное:
   - Обосновать решение (почему меняем порядок)
   - Зафиксировать изменение в INTERNAL_ROADMAP.md и CURRENT_FOCUS.md
   - Не нарушать архитектурные контракты
   Качество продукта важнее следования плану буква-в-букву.

8. **ДОКУМЕНТИРУЙ ВСЕ ИЗМЕНЕНИЯ ПЛАНА.** Если принято решение изменить порядок,
   отложить задачу или добавить новую — это должно быть отражено в:
   - INTERNAL_ROADMAP.md (стратегический план — отметка [изменено] с датой и причиной)
   - CURRENT_FOCUS.md (текущий фокус — обновление раздела "План")
   - worklog.md (журнал — запись о принятом решении)
   В следующих сессиях эта информация должна быть доступна.

---

## 0. Текущий статус

### Что готово:

**Sprint 0 — Архитектурный (завершён)**
- [x] Концептуальная архитектура (CONCEPTUAL.md, 10 разделов)
- [x] 9 шагов проектирования с детальными контрактами (docs/architecture/01-09)
- [x] 17 ADR (adr/0001-0017)
- [x] Репозиторий создан: https://github.com/Pradushkoai/1c-ai-assistant
- [x] Initial commit (dfb609d): структура пакетов, Dockerfile'ы, docker-compose, CI-скрипты
- [x] 5 Python пакетов uv workspace
- [x] Docker setup: 3 контейнера (app + bsl-ls + postgres/pgvector)
- [x] `scripts/check_package_boundaries.py` — работает
- [x] Security: токен в `.github-token` (chmod 600, gitignored)
- [x] AGENTS.md, README.md, CONTRIBUTING.md, CHANGELOG.md, LICENSE (MIT)

**Sprint 1 — Parsers + Data Layer + CLI (завершён, 6 коммитов, 344 теста)**
- [x] parsers/models — 22 Pydantic v2 модели (80 тестов)
- [x] data_layer — PathManager, ConfigRegistry, freshness (90 тестов)
- [x] parsers/xml — 4 парсера + utils + универсальный (106 тестов)
- [x] parsers/indexers — metadata_indexer (35 тестов)
- [x] agent — CLI 1c-ai (init, config add/build/list/remove, validate, hbk load) (33 теста)
- [x] CI/CD — ci.yml + integration.yml (зелёная)
- [x] README Quick Start, CHANGELOG v0.1.0, AGENTS update, CONTRIBUTING running tests

**Sprint 1.5 — Архитектурный каркас (код завершён, тесты — НЕОБХОДИМЫ)**
- [x] mcp_servers/shared/protocol.py — ToolContract Protocol, ToolError
- [x] mcp_servers/{metadata,codebase,kb,bsl_ls,git}/contracts.py — 19 контрактов
- [x] mcp_servers/facade/ — 8 lifecycle tools (контракты, next_action, handlers stubs, tool_definitions)
- [x] orchestrator/state.py — TaskState, Subtask, Iteration, FSMState, SubtaskConstraints
- [x] orchestrator/contracts.py — 10 Result типов
- [x] orchestrator/routers.py — 4 детерминированных роутера
- [x] orchestrator/errors.py — 14 классов ошибок + error_to_escalate_reason
- [x] orchestrator/tool_groups.py — TOOL_GROUPS (6 ролей), MULTI_ROLE_OK
- [x] orchestrator/tool_provider.py — ToolProvider, make_tool_provider
- [x] orchestrator/retry.py — with_retry с backoff
- [x] orchestrator/persistence.py — PersistenceManager (stub, MemorySaver)
- [x] orchestrator/nodes/ — 10 заглушек узлов
- [x] orchestrator/graph.py — каркас графа (константы + build_graph stub)
- [ ] **tests/orchestrator/ — 6 тест-файлов (НЕОБХОДИМО НАПИСАТЬ)**
- [ ] **tests/mcp_servers/ — 2 тест-файла (НЕОБХОДИМО НАПИСАТЬ)**

### Что НЕ готово (метакод — нужно проработать до кода)

Эти вопросы нужно концептуально закрыть ПЕРЕД началом соответствующего спринта. Если начать код без них — получим переделки.

#### M1. Структура Jinja2 промптов (нужно до Спринта 2)

**Проблема:** в `knowledge-base/prompts/` будут `planner.system.j2`, `gatherer.system.j2`, `coder.system.j2`, `reviewer.system.j2`. Но их точное содержание не зафиксировано. Нужно определить:

- Какие переменные каждый промпт принимает (`subtask`, `gather_result`, `prev_iteration`, `constraints_reminder`, ...)
- Структура: persona → role → context → constraints → output format
- Длина: не более 2000 токенов на system prompt (иначе дорого)
- Какой persona: "Senior 1C developer with 10+ years" — это ок, но какие именно принципы?
- Russian vs English: system prompt на каком языке? (ADR-0008 в старом проекте — русский, но LLM лучше понимает английский)

**Действие:** создать `docs/architecture/10-prompts-spec.md` с детальным содержанием каждого промпта ДО реализации Спринта 2.

#### M2. Postgres migration strategy (нужно до Спринта 2)

**Проблема:** `TaskState` будет меняться (добавляться поля). Нужна стратегия миграций `checkpoints` таблицы LangGraph.

- Использовать alembic или писать миграции руками?
- Версионирование `TaskState` через поле `schema_version: int`?
- Что делать со старыми checkpoint'ами при breaking change?

**Действие:** ADR-0018 "TaskState migration strategy" — до Спринта 2.

#### M3. Embeddings strategy (нужно до Спринта 4)

**Проблема:** codebase-server использует embeddings. Нужно решить:

- Какая модель? BGE-M3 (multilingual, 1024 dim) vs OpenAI text-embedding-3-large (3072 dim) vs fastembed default (384 dim)
- Размерность влияет на схему БД: `VECTOR(384)` vs `VECTOR(1024)` vs `VECTOR(3072)`
- Локально (fastembed) или через API (OpenAI)? Локально = бесплатно, но медленнее; API = быстро, но платно
- Когда переиндексировать? При `config build --force`? При изменении модели?
- Что делать с конфигурациями, загруженными до смены модели?

**Действие:** ADR-0019 "Embeddings strategy" — до Спринта 4.

#### M4. KB seed content (нужно до Спринта 3)

**Проблема:** для MVP нужно минимум 5 паттернов и 10 антипаттернов. Какие именно?

- Patterns: `transaction-wrapper`, `posting-handler`, `session-cache`, `deferred-modal`, `bsp-value-retrieval` — ок, но нужно содержание
- Antipatterns: `query-in-loop`, `try-catch-silent`, `point-access-in-loop`, `hardcoded-predefined`, `modal-call-in-client`, `select-star`, `function-in-where`, `commit-in-loop`, `transaction-without-try`, `metadata-on-client` — нужно описание + detect правила
- Каждый — это YAML файл + примеры `.bsl` (good/bad)

**Действие:** создать `docs/architecture/11-kb-seed-list.md` с полным списком и приоритетом — до Спринта 3.

#### M5. LangSmith trace structure (нужно до Спринта 2)

**Проблема:** LangSmith — observability. Но какие метрики собираем?

- На каждый LLM-вызов: model, tokens_in, tokens_out, latency, cost
- На каждый pipeline run: total cost, total tokens, total latency, subtask_count, iterations_count, escalation_count
- На каждый retry: reason, prev_iteration_edit_distance
- Метрики в Prometheus или только LangSmith?

**Действие:** ADR-0020 "Observability strategy" — до Спринта 2.

#### M6. CI/CD workflow design (нужно до Спринта 1)

**Проблема:** в репо нет `.github/workflows/`. Нужно разработать:

- `ci.yml` — lint (ruff) + type check (mypy) + tests (pytest) на каждый PR
- `boundary-check.yml` — `scripts/check_package_boundaries.py`
- `adr-consistency.yml` — проверка что ADR файлы соответствуют шаблону
- `release.yml` — tag → GitHub release + docker images
- Кэширование uv между запусками
- Matrix: Python 3.12 only (пока)

**Действие:** создать `.github/workflows/` в первом коммите Спринта 1.

#### M7. Test data strategy (нужно до Спринта 1)

**Проблема:** для тестов parsers нужны примеры 1С XML и BSL. Откуда брать?

- Минимальный синтетический конфиг (Catalog + Document + CommonModule) — создать в `tests/fixtures/`
- Реальные конфиги (УТ 11) — нельзя коммитить (большой объём + лицензионные вопросы)
- Подход: синтетические fixtures в репо + опциональные большие тесты через `pytest -m integration` (запускаются только если есть `data/configs/ut11/`)

**Действие:** `tests/fixtures/` с минимальной конфигурацией в первом коммите Спринта 1.

#### M8. Migration path для пользователей старого репо (опционально)

**Проблема:** у пользователя есть данные в `1c-ai-dev-env/data/`. Как их перенести?

- Структура директорий похожая, но не идентичная
- `config-registry.json` формат отличается
- Индексы несовместимы (другая схема)

**Действие:** скрипт `scripts/migrate_from_dev_env.py` — опционально, после Спринта 1. Не критично для MVP.

---

## 1. Спринт 1 — Parsers + Data Layer + CLI

**Артефакт:** `1c-ai config build` работает end-to-end

**Цель:** пользователь может загрузить ZIP конфигурации 1С, распаковать, построить индекс метаданных. Базовый фундамент для всех следующих спринтов.

### 1.1. Задачи

#### Пакет `parsers/models/` (Pydantic v2 модели)

- [ ] `common.py`: `ModelConfig` base, `ObjectRef`, `Version`, `ExecutionEnvironment`, `ContextAvailability`
- [ ] `module.py`: `Region`, `MethodParameter`, `Method`, `BslModule`
- [ ] `metadata.py`: `MetadataType` (enum), `Attribute`, `ObjectMetadata`, `CatalogMetadata`, `DocumentMetadata`, `CommonModuleMetadata`, `FormElement`, `FormMetadata`
- [ ] `method.py`: `PlatformMethod`, `PlatformProperty`
- [ ] `config.py`: `VersionInfo`, `ConfigMeta`, `ConfigRegistryEntry`
- [ ] `graph.py`: `DependencyEdge`, `CallEdge`, `GraphStats`
- [ ] `__init__.py`: re-export всех моделей через `__all__`
- [ ] Тесты: `tests/parsers/test_models.py` (property-based через hypothesis — round-trip, frozen, extra=forbid, JSON Schema export)

#### Пакет `data_layer/` (PathManager + ConfigRegistry)

- [ ] `path_manager.py`: `PathManagerProtocol`, `PathManager` с `${VAR}` подстановкой, OS env override
- [ ] `config_registry.py`: `ConfigRegistry` (add/list/get/remove, persistence в `runtime/config-registry.json`)
- [ ] `freshness.py`: `latest_mtime()`, `is_fresh()` функции
- [ ] `__init__.py`: re-export
- [ ] Тесты: `tests/data_layer/test_path_manager.py` (tmp_path fixture, env override, freshness check)
- [ ] Тесты: `tests/data_layer/test_config_registry.py` (persistence, add/remove)

#### Пакет `parsers/xml/` (минимальный XML парсер)

- [ ] `configuration.py`: парсер `Configuration.xml` → `ConfigMeta`
- [ ] `catalog.py`: парсер `Catalog.xml` → `CatalogMetadata` (минимальный: name, synonym, attributes, code_length)
- [ ] `document.py`: парсер `Document.xml` → `DocumentMetadata` (минимальный: name, synonym, attributes, number_length, register_records)
- [ ] `common_module.py`: парсер `CommonModule.xml` → `CommonModuleMetadata` (server, global, client flags)
- [ ] `__init__.py`: re-export
- [ ] Тесты: `tests/parsers/test_xml_*.py` на синтетических fixtures

#### Пакет `parsers/indexers/` (построение индексов)

- [ ] `metadata_indexer.py`: собирает `unified-metadata-index.json` из всех XML конфигурации
- [ ] `__init__.py`: re-export
- [ ] Тесты: `tests/parsers/test_metadata_indexer.py`

#### Пакет `agent/` (CLI)

- [ ] `cli.py`: точка входа `1c-ai` (click), dispatch на подкоманды
- [ ] `cli_commands/config.py`: `1c-ai config add/build/list/remove`
  - `add --name X --version Y --zip X.zip` — распаковать в `data/configs/X/Y/`, добавить в registry
  - `build --name X [--version Y] [--force] [--check-freshness]` — построить индексы
  - `list` — показать все конфигурации
  - `remove --name X --version Y` — удалить
- [ ] `cli_commands/init.py`: `1c-ai init` — создать `data/`, `derived/`, `runtime/` директории
- [ ] `cli_commands/validate.py`: `1c-ai validate` — preflight check через PathManager.validate()
- [ ] `__init__.py`: re-export
- [ ] Тесты: `tests/agent/test_cli_config.py` (end-to-end через click CliRunner)

#### Тестовые fixtures

- [ ] `tests/fixtures/mini_config/` — минимальная 1С конфигурация:
  - `Configuration.xml` (1 catalog + 1 document + 1 common module)
  - `Catalogs/Товары/Товары.xml` (3 атрибута)
  - `Documents/Продажа/Продажа.xml` (2 атрибута, 1 register record)
  - `CommonModules/ОбщегоНазначения/ОбщегоНазначения.xml` (server=true)
- [ ] `tests/fixtures/mini_config.zip` — ZIP-архив для теста `config add`

#### CI/CD

- [ ] `.github/workflows/ci.yml`: ruff + mypy + pytest на каждый PR/push
- [ ] `.github/workflows/boundary-check.yml`: `scripts/check_package_boundaries.py`
- [ ] Кэширование `uv` между запусками

#### Документация (обновление)

- [ ] `README.md`: добавить секцию "Quick Start" с примером `1c-ai init && 1c-ai config add && 1c-ai config build`
- [ ] `AGENTS.md`: добавить правило "Перед `1c-ai config build` всегда `1c-ai config build --check-freshness`"
- [ ] `CONTRIBUTING.md`: добавить секцию "Running tests locally"
- [ ] `CHANGELOG.md`: создать файл, добавить запись для v0.1.0

### 1.2. Стратегия коммитов

```
feat(parsers/models): add Pydantic v2 models for 1C metadata
feat(parsers/xml): add Configuration.xml and Catalog.xml parsers
feat(data_layer): add PathManager and ConfigRegistry
feat(parsers/indexers): add metadata indexer
feat(agent): add 1c-ai config CLI commands
test: add fixtures and tests for Sprint 1
ci: add GitHub Actions workflows
docs: update README with Quick Start
chore: bump version to 0.1.0
```

### 1.3. Критерий готовности

- [ ] `1c-ai init` создаёт структуру директорий
- [ ] `1c-ai config add --name mini --version 1.0 --zip tests/fixtures/mini_config.zip` — распаковывает
- [ ] `1c-ai config build --name mini` — строит `unified-metadata-index.json`
- [ ] `1c-ai config list` — показывает mini 1.0
- [ ] `1c-ai validate` — проходит без ошибок
- [ ] `pytest tests/ -v` — все тесты зелёные
- [ ] `ruff check packages/` — без ошибок
- [ ] `mypy packages/` — без ошибок
- [ ] CI зелёная на GitHub

### 1.4. Что НЕ делаем в Спринте 1

- BSL парсер (`.bsl` файлы) — Спринт 2
- HBK парсер — Спринт 3 (нужен для KB)
- Postgres подключение — Спринт 2 (нужен для orchestrator)
- Docker сборка — Спринт 4 (когда есть что контейнизировать)
- Любые MCP-серверы — Спринт 2+

---

## 1.5. Спринт "Архитектурный каркас" — верхнеуровневые компоненты

> **ВАЖНО:** Этот спринт добавлен после сверки плана с пользователем (2026-07-11).
> Подход изменился: **сначала верхнеуровневые компоненты (контракты, протоколы,
> абстракции), потом частные реализации**. Это позволяет:
> - Зафиксировать контракты между слоями до того, как начнём их наполнять
> - Иметь компилируемый код, в котором есть заглушки для всех узлов/серверов
> - Запускать тесты на роутерах и TOOL_GROUPS без LLM и MCP-серверов
> - Иметь CI-каркас для всех пакетов (включая orchestrator, mcp_servers)
>
> Альтернатива (Sprint 2 снизу вверх) — BSL parser → bsl_ls MCP → orchestrator.
> Но без контрактов orchestrator'а и MCP мы не сможем тестировать их вместе.

**Артефакт:** Все контракты реализованы, тесты зелёные, импорты работают, но LLM-узлы и MCP-серверы — заглушки (NotImplementedError).

**Принцип:** "Каркас можно компилировать и тестировать, но он ничего не делает."

### 1.5.1. Что реализуем

#### `mcp_servers/shared/protocol.py` — общий Protocol

- [ ] `ToolContract` Protocol (name, description, input_schema, output_model, error_contract, timeout, idempotent, required_role)
- [ ] `ToolError` базовый класс
- [ ] `make_mcp_tool()` helper

#### `mcp_servers/shared/__init__.py`

- [ ] re-export

#### `mcp_servers/{metadata,codebase,kb,bsl_ls,git}/contracts.py` — 19 контрактов

Все контракты из `docs/architecture/05-mcp-tool-contracts.md`:

- [ ] `metadata/contracts.py`: GetMetadata, GetFormStructure, GetApiReference, GetDependencyGraph (4)
- [ ] `codebase/contracts.py`: SemanticSearch, GetModule, GetSimilar, CallGraph (4)
- [ ] `kb/contracts.py`: GetPattern, GetAntipattern, SearchKb, CheckMethodAvailability, CheckAntipatterns (5)
- [ ] `bsl_ls/contracts.py`: Lint, Format (2)
- [ ] `git/contracts.py`: CreateBranch, Commit, OpenPr, Diff (4)

Каждый контракт:
- Pydantic Input/Output модели
- Класс с атрибутами (name, description, input_schema, output_model, error_contract, timeout, idempotent, required_role)
- `__call__` — `raise NotImplementedError` (реализация в Sprint 2-4)
- `*_TOOLS` список для re-export

#### `mcp_servers/{metadata,codebase,kb,bsl_ls,git}/__init__.py`

- [ ] re-export `*_TOOLS` списков

#### `orchestrator/state.py` — TaskState

- [ ] `FSMState` enum (INIT, PLANNING, GATHERING, CODING, VALIDATING, REVIEWING, COMMITTING, ESCALATED, DONE, FAILED)
- [ ] `SubtaskConstraints` (dont_list, must_list, available_modules, target_context)
- [ ] `Subtask` (id, name, target_module, description, inputs, outputs, acceptance_criteria, json_schema, constraints, max_iterations, status)
- [ ] `Iteration` (number, code, llm_response, bsl_ls_diagnostics, review_findings, test_result, edit_distance_vs_prev, failed_checks, created_at)
- [ ] `TaskState` (task_id, description, config_name, config_version, platform_version, subtasks, current_subtask_idx, current_iteration, iterations, fsm_state, constraints_reminder, validation_passed, review_passed, critical_findings, plan_result, gather_result, validate_result, review_result, commit_result, created_at, updated_at, parent_checkpoint_id, trace_metadata)

Все frozen + extra=forbid + strict (наследуют ModelConfig).

#### `orchestrator/contracts.py` — Result типы узлов

- [ ] `PlanResult` (subtasks, decomposition_strategy, rationale, plan_metadata)
- [ ] `GatheredMetadata`, `GatheredCode`, `GatheredKnowledge` (вложенные)
- [ ] `GatherResult` (subtask_id, metadata, code, knowledge, context_summary, mcp_calls_made)
- [ ] `CodeResult` (subtask_id, iteration_number, code, target_module, llm_metadata, structured_output_valid)
- [ ] `ValidationFinding` (severity, code, message, line, column, source, fix_hint)
- [ ] `ValidateResult` (subtask_id, iteration_number, findings, passed, severity_breakdown, failed_checks)
- [ ] `ReviewFinding` (severity, category, code, message, recommendation)
- [ ] `ReviewResult` (subtask_id, iteration_number, findings, decision, rationale, critical_findings, passed)
- [ ] `CommitResult` (subtask_id, branch_name, commit_sha, pr_url, pr_number, files_changed, diff_summary)
- [ ] `EscalateResult` (subtask_id, reason, iteration_log, pr_url, suggested_actions)

#### `orchestrator/routers.py` — детерминированные роутеры

- [ ] `route_after_validate(state) -> Literal["review", "retry"]`
- [ ] `route_after_review(state) -> Literal["commit", "retry", "escalate"]`
- [ ] `route_after_retry(state) -> Literal["code", "escalate"]`
- [ ] `route_after_commit(state) -> Literal["next_subtask", "end"]`

#### `orchestrator/errors.py` — таксономия ошибок (14 классов)

- [ ] `ErrorAction` enum (RETRY, ESCALATE, ABORT)
- [ ] `AgentError` (базовый, code, action, details)
- [ ] `PreflightError`, `IndexStaleError` (ABORT)
- [ ] `SchemaViolationError` (RETRY)
- [ ] `ToolError` → `ToolTimeoutError`, `ToolConnectionError`, `ToolExecutionError`, `RoleForbiddenError`
- [ ] `LLMError` → `LLMUnavailableError`, `LLMRateLimitError`, `LLMBudgetExceededError`
- [ ] `ValidationFailedError`, `ReviewRejectedError` (RETRY)
- [ ] `MaxIterationsExceededError`, `EscalationRequestedError` (ESCALATE)
- [ ] `PersistenceError` (ABORT)
- [ ] `error_to_escalate_reason()` функция

#### `orchestrator/tool_groups.py` — TOOL_GROUPS registry

- [ ] `AgentRole` enum (PLANNER, GATHERER, CODER, VALIDATOR, REVIEWER, COMMITTER)
- [ ] `TOOL_GROUPS: dict[AgentRole, dict[str, frozenset[str]]]` (полная таблица из Шага 6)
- [ ] `MULTI_ROLE_OK: dict[str, list[AgentRole]]` (2 исключения)
- [ ] `_validate_multi_role()` проверка при импорте

#### `orchestrator/tool_provider.py` — ToolProvider

- [ ] `ToolProvider` класс (role, tool_contracts, _allowed, get_tools, has_tool)
- [ ] `make_tool_provider(role)` фабрика
- [ ] `_collect_all_tool_contracts()` — собирает из 5 серверов

#### `orchestrator/retry.py` — retry-логика

- [ ] `with_retry(func, max_attempts, base_delay, max_delay, on_retry)` функция
- [ ] `_compute_delay()` — exponential/linear backoff

#### `orchestrator/persistence.py` — PersistenceManager (stub)

- [ ] `PersistenceManager` класс (async context manager)
- [ ] `get_checkpointer()` — пока возвращает MemorySaver, PostgresSaver в Sprint 4
- [ ] `_mask_dsn()` helper

#### `orchestrator/nodes/` — заглушки узлов

- [ ] `nodes/__init__.py`
- [ ] `nodes/preflight.py` — `preflight_node(state)` (реализация в Sprint 2)
- [ ] `nodes/plan.py` — `plan_node(state)` (заглушка, Sprint 3)
- [ ] `nodes/gather.py` — `gather_node(state)` (заглушка, Sprint 3)
- [ ] `nodes/code.py` — `code_node(state)` (заглушка, Sprint 2)
- [ ] `nodes/validate.py` — `validate_node(state)` (заглушка, Sprint 2)
- [ ] `nodes/review.py` — `review_node(state)` (заглушка, Sprint 3)
- [ ] `nodes/retry.py` — `retry_node(state)` (заглушка, Sprint 2)
- [ ] `nodes/commit.py` — `commit_node(state)` (заглушка, Sprint 4)
- [ ] `nodes/escalate.py` — `escalate_node(state)` (заглушка, Sprint 2)
- [ ] `nodes/next_subtask.py` — `next_subtask_node(state)` (заглушка, Sprint 3)

#### `orchestrator/graph.py` — сборка StateGraph (без LangGraph)

- [ ] Каркас графа (пока без LangGraph — только структура для документации)
- [ ] Константы: `ENTRY_POINT`, `NODES`, `EDGES`, `CONDITIONAL_EDGES`
- [ ] `build_graph()` — заглушка, raise NotImplementedError("LangGraph integration in Sprint 2")

#### `mcp_servers/facade/` — заглушка Facade

- [ ] `facade/__init__.py`
- [ ] `facade/contracts.py`: PlanInput/Output, GatherInput/Output, GenerateInput/Output, ValidateInput/Output, ReviewInput/Output, ExplainInput/Output, RunCliInput/Output, DataStatusOutput, NextAction
- [ ] `facade/next_action.py`: `after_plan`, `after_gather`, `after_generate`, `after_validate`, `after_review`
- [ ] `facade/handlers.py`: `FacadeHandlers` класс (заглушки — NotImplementedError)
- [ ] `facade/tool_definitions.py`: `FACADE_TOOLS` список (8 tools)
- [ ] `facade/server.py`: `create_facade_server()`, `run_facade_server()` (заглушка)

### 1.5.2. Тесты

- [ ] `tests/orchestrator/test_state.py` — TaskState frozen, model_copy, round-trip
- [ ] `tests/orchestrator/test_contracts.py` — все Result типы, JSON Schema export
- [ ] `tests/orchestrator/test_routers.py` — property-based (hypothesis), все 4 роутера
- [ ] `tests/orchestrator/test_errors.py` — 14 классов, action mapping, error_to_escalate_reason
- [ ] `tests/orchestrator/test_tool_groups.py` — 3 CI-теста (no_orphan, no_unexpected_multi_role, tool_provider)
- [ ] `tests/orchestrator/test_retry.py` — with_retry, backoff, max_attempts, non-retryable
- [ ] `tests/mcp_servers/test_contracts.py` — snapshot тесты всех 19 tools
- [ ] `tests/mcp_servers/test_facade_contracts.py` — 8 lifecycle tools

### 1.5.3. Критерий готовности

- [ ] Все пакеты импортируются без ошибок
- [ ] `python -c "import orchestrator; import mcp_servers"` работает
- [ ] `check_package_boundaries.py` — OK
- [ ] Все тесты (предыдущие 344 + новые) зелёные
- [ ] ruff + mypy чистые
- [ ] CI зелёная
- [ ] Все 19 MCP контрактов имеют валидные JSON Schema (snapshot тесты)
- [ ] TOOL_GROUPS проходит 3 CI-теста (no_orphan, no_unexpected_multi_role, tool_provider)
- [ ] Роутеры проходят property-based тесты
- [ ] Error taxonomy — 14 классов, каждый с правильным action

### 1.5.4. Что НЕ делаем в этом спринте

- Реализация LLM-узлов (Coder, Planner, Reviewer) — Sprint 2-3
- Реализация MCP-серверов (HTTP/subprocess) — Sprint 2-4
- LangGraph integration в `graph.py` — Sprint 2
- KB YAML файлы — Sprint 3
- Postgres persistence — Sprint 4
- Docker — Sprint 4

---

## 2. Спринт 2 — BSL LS MCP + минимальный pipeline

**Артефакт:** `1c-ai generate --task "..."` генерирует BSL одной функцией

**Цель:** end-to-end pipeline: задача → сгенерированный код → валидация через BSL LS. Без Planner, без Reviewer, без KB. Только Coder + Validator.

### 2.1. Зависимости от метакода

- [ ] M1 (Jinja2 промпты) — нужно ДО реализации `coder.system.j2`
- [ ] M2 (Postgres migrations) — нужно ДО первого запуска orchestrator
- [ ] M5 (LangSmith trace) — нужно ДО первого LLM-вызова

### 2.2. Задачи

#### Контейнер `1c-ai-bsl-ls`

- [ ] `docker/bsl_ls_http_server.py` — FastAPI сервер на :8080
  - `POST /lint` — принимает `{code, file_path, rules?}`, возвращает `{diagnostics, total, by_code}`
  - `POST /format` — принимает `{code, style}`, возвращает `{formatted_code, changes_made}`
  - `GET /health` — health check
- [ ] Запуск BSL LS как long-running subprocess через stdin/stdout
- [ ] Тесты: `tests/integration/test_bsl_ls_http.py` (требует запущенного контейнера)

#### Пакет `parsers/bsl/` (минимальный BSL парсер)

- [ ] `module.py`: парсер `.bsl` → `BslModule` (методы, регионы, line_count)
- [ ] `methods.py`: extract export methods with signatures
- [ ] `regions.py`: parse `#Область ... #КонецОбласти`
- [ ] Опционально: tree-sitter-bsl integration (если установлен)
- [ ] Тесты: `tests/parsers/test_bsl_module.py`

#### Пакет `mcp_servers/shared/`

- [ ] `protocol.py`: `ToolContract` Protocol, `ToolError`
- [ ] `__init__.py`: re-export

#### Пакет `mcp_servers/bsl_ls/`

- [ ] `contracts.py`: `LintInput/Output`, `FormatInput/Output`, `Lint`, `Format` ToolContract'ы
- [ ] `server.py`: `BslLsServer` — HTTP client к `1c-ai-bsl-ls:8080` через httpx
- [ ] Тесты: `tests/mcp_servers/test_bsl_ls_contracts.py` (snapshot тесты)

#### Пакет `orchestrator/` (минимальный pipeline)

- [ ] `state.py`: `TaskState`, `Subtask`, `Iteration`, `FSMState`, `SubtaskConstraints`
- [ ] `contracts.py`: `CodeResult`, `ValidateResult`, `ValidationFinding`
- [ ] `errors.py`: `AgentError` иерархия (14 классов), `ErrorAction` enum
- [ ] `retry.py`: `with_retry()` функция
- [ ] `persistence.py`: `PersistenceManager` (PostgresSaver)
- [ ] `routers.py`: `route_after_validate`, `route_after_retry`
- [ ] `tool_groups.py`: `AgentRole`, `TOOL_GROUPS`, `MULTI_ROLE_OK`
- [ ] `tool_provider.py`: `ToolProvider`, `make_tool_provider()`
- [ ] `nodes/code.py`: Coder node (LLM + structured_output)
- [ ] `nodes/validate.py`: Validate subgraph (parallel fan-out: bsl_ls.lint)
- [ ] `nodes/retry.py`: retry node
- [ ] `nodes/escalate.py`: escalate node
- [ ] `nodes/preflight.py`: preflight check
- [ ] `graph.py`: сборка главного StateGraph (без Plan/Gather/Review — это спринт 3)
- [ ] Тесты: `tests/orchestrator/test_*.py` (state, routers, retry, graph compile)

#### Пакет `agent/` (CLI generate)

- [ ] `cli_commands/generate.py`: `1c-ai generate --task "..." --config X --version Y`
- [ ] Тесты: `tests/agent/test_cli_generate.py` (mock LLM)

#### Промпты (KB seed)

- [ ] `knowledge-base/prompts/coder.system.j2` — системный промпт Coder'а
- [ ] `knowledge-base/schemas/code-output.schema.json` — structured output schema

#### Observability

- [ ] LangSmith интеграция в `orchestrator/graph.py` (через env var `LANGSMITH_API_KEY`)
- [ ] structlog конфигурация (JSON для CI, console для dev)

#### Документация

- [ ] `README.md`: обновить Quick Start с `1c-ai generate`
- [ ] `AGENTS.md`: добавить правило "BSL LS timeout 60s, fallback на KB"
- [ ] `CHANGELOG.md`: запись для v0.2.0

### 2.3. Критерий готовности

- [ ] `docker compose up -d` — 3 контейнера запущены
- [ ] `1c-ai generate --task "Создать функцию Сложить(a, b) возвращающую сумму" --config mini --version 1.0` — генерирует BSL
- [ ] Сгенерированный код проходит BSL LS без critical ошибок
- [ ] При ошибке — retry до 3 раз, потом escalate
- [ ] LangSmith trace виден (если `LANGSMITH_API_KEY` установлен)
- [ ] `pytest tests/ -v` — зелёные
- [ ] CI зелёная

### 2.4. Что НЕ делаем в Спринте 2

- Planner — Спринт 3
- Reviewer — Спринт 3
- KB (patterns/antipatterns) — Спринт 3
- Gather subgraph (пока Coder получает пустой контекст) — Спринт 3
- metadata/codebase/git MCP — Спринт 4
- Facade lifecycle tools — Спринт 4

---

## 3. Спринт 3 — KB-as-code + Planner + Reviewer

**Артефакт:** `1c-ai generate` с Planner (декомпозиция) + Reviewer (LLM-ревью)

**Цель:** полный pipeline кроме metadata/codebase/git MCP. KB с 5 паттернами и 10 антипаттернами.

### 3.1. Зависимости от метакода

- [ ] M4 (KB seed content) — нужно ДО создания YAML файлов

### 3.2. Задачи

#### KB seed (5 patterns + 10 antipatterns)

- [ ] `knowledge-base/schemas/antipattern.schema.json`
- [ ] `knowledge-base/schemas/pattern.schema.json`
- [ ] `knowledge-base/schemas/subtask.schema.json` (для Planner structured output)
- [ ] `knowledge-base/schemas/review-output.schema.json` (для Reviewer)
- [ ] 5 patterns: `transaction-wrapper.yaml`, `posting-handler.yaml`, `session-cache.yaml`, `deferred-modal.yaml`, `bsp-value-retrieval.yaml`
- [ ] 10 antipatterns: `query-in-loop.yaml`, `try-catch-silent.yaml`, `point-access-in-loop.yaml`, `hardcoded-predefined.yaml`, `modal-call-in-client.yaml`, `select-star.yaml`, `function-in-where.yaml`, `commit-in-loop.yaml`, `transaction-without-try.yaml`, `metadata-on-client.yaml`
- [ ] `knowledge-base/index.json` — реестр
- [ ] Примеры `.bsl` (good/bad) для каждого правила в `knowledge-base/examples/`

#### Пакет `mcp_servers/kb/`

- [ ] `contracts.py`: `GetPatternInput/Output`, `GetAntipatternInput/Output`, `SearchKbInput/Output`, `CheckMethodAvailabilityInput/Output`, `CheckAntipatternsInput/Output`
- [ ] `loader.py`: `KBCollection` — загрузка YAML + JSON Schema валидация
- [ ] `server.py`: `KbServer` — реализация 5 tools
- [ ] Тесты: `tests/mcp_servers/test_kb_*.py`

#### Пакет `parsers/hbk/` (HBK парсер — для platform methods)

- [ ] `syntax_helper.py`: парсер `.hbk` файлов
- [ ] `methods_db.py`: загрузка в SQLite `platform-methods.db`
- [ ] `context_rules.py`: `ContextAvailability` для каждого метода
- [ ] Тесты: `tests/parsers/test_hbk_*.py` (на синтетическом .hbk)

#### Пакет `parsers/indexers/` (platform methods indexer)

- [ ] `platform_methods_indexer.py`: `.hbk` → `platform-methods.db`
- [ ] CLI: `1c-ai hbk load --version 8.3.20 --path /path/to/hbk/`
- [ ] Тесты

#### Пакет `orchestrator/nodes/` (Plan + Gather + Review)

- [ ] `nodes/plan.py`: Plan mini-supervisor subgraph (supervisor → decompose → validate_plan)
- [ ] `nodes/gather.py`: Gather mini-supervisor subgraph (supervisor → fan_out → merge_context)
- [ ] `nodes/review.py`: Review mini-supervisor subgraph (check_antipatterns → check_context → decide)
- [ ] `nodes/commit.py`: Commit node (пока без git, просто запись в файл)
- [ ] Обновить `graph.py`: добавить Plan/Gather/Review в главный граф
- [ ] Тесты: `tests/orchestrator/test_plan_*.py`, `test_gather_*.py`, `test_review_*.py`

#### Промпты

- [ ] `knowledge-base/prompts/planner.system.j2`
- [ ] `knowledge-base/prompts/gatherer.system.j2`
- [ ] `knowledge-base/prompts/reviewer.system.j2`
- [ ] `knowledge-base/prompts/validator.system.j2` (опционально, Validator детерминированный)

#### Snapshot тесты

- [ ] `tests/snapshots/test_mcp_contracts.py` — snapshot всех MCP tool definitions
- [ ] `tests/golden/test_pipeline_*.py` — 5 эталонных задач end-to-end

#### Документация

- [ ] `README.md`: обновить с упоминанием KB
- [ ] `CHANGELOG.md`: v0.3.0

### 3.3. Критерий готовности

- [ ] `1c-ai generate --task "Добавить обработку проведения для документа Продажа"` — декомпозирует на 1-2 подзадачи
- [ ] Для каждой подзадачи: gather → code → validate → review → commit (в файл)
- [ ] Reviewer может отклонить код с конкретными findings
- [ ] KB правила детектят антипаттерны в сгенерированном коде
- [ ] `pytest tests/ -v` — зелёные, включая golden тесты

---

## 4. Спринт 4 — metadata/codebase/git MCP + Facade + Production

**Артефакт:** production-ready для внутреннего использования

**Цель:** все 5 MCP серверов работают, Facade lifecycle tools работают с Cursor, persistence через Postgres, гибридный search.

### 4.1. Зависимости от метакода

- [ ] M3 (Embeddings strategy) — нужно ДО codebase-server

### 4.2. Задачи

#### Пакет `parsers/xml/` (расширение)

- [ ] `form.py`: парсер `Form.xml` → `FormMetadata`
- [ ] `role.py`: парсер `Rights.xml`
- [ ] `subsystem.py`: парсер `Subsystem.xml`
- [ ] `skd.py`: парсер `DataCompositionSchema`
- [ ] Полный `metadata_indexer.py` (все типы объектов)

#### Пакет `parsers/bsl/` (расширение)

- [ ] `call_graph.py`: построение графа вызовов
- [ ] `sdbl/` — SDBL парсер (генерация из .g4 через ANTLR4)
- [ ] `indexers/api_reference_indexer.py` — BSL → `api-reference.json`
- [ ] `indexers/call_graph_indexer.py` — BSL → `call-graph.json`

#### Пакет `parsers/xml/` (dependency graph)

- [ ] `dependency_graph_indexer.py` — XML → `dependency-graph.json` (networkx)

#### Пакет `mcp_servers/metadata/`

- [ ] `contracts.py`: 4 tools (get_metadata, get_form_structure, get_api_reference, get_dependency_graph)
- [ ] `server.py`: `MetadataServer`
- [ ] Тесты

#### Пакет `mcp_servers/codebase/`

- [ ] `vector_store.py`: `VectorStoreProtocol`
- [ ] `vector_stores/pgvector_store.py`: `PgVectorStore`
- [ ] `vector_stores/qdrant_store.py`: `QdrantVectorStore` (опционально)
- [ ] `vector_store_factory.py`: `make_vector_store()` по env var
- [ ] `contracts.py`: 4 tools (semantic_search, get_module, get_similar, call_graph)
- [ ] `server.py`: `CodebaseServer` — гибридный search (BM25 + vector + RRF)
- [ ] `indexers/embeddings_indexer.py` — BSL → embeddings в postgres
- [ ] Тесты: `tests/mcp_servers/test_codebase_*.py` + бенчмарк pgvector vs qdrant

#### Пакет `mcp_servers/git/`

- [ ] `contracts.py`: 4 tools (create_branch, commit, open_pr, diff)
- [ ] `server.py`: `GitServer` — subprocess git CLI
- [ ] Обновить `nodes/commit.py`: реальный git commit + PR
- [ ] Тесты

#### Пакет `mcp_servers/facade/`

- [ ] `contracts.py`: `PlanInput/Output`, `GatherInput/Output`, `GenerateInput/Output`, `ValidateInput/Output`, `ReviewInput/Output`, `ExplainInput/Output`, `RunCliInput/Output`, `DataStatusOutput`
- [ ] `next_action.py`: builder'ы для `_next_action`
- [ ] `handlers.py`: `FacadeHandlers` — 7 lifecycle handlers
- [ ] `tool_definitions.py`: `FACADE_TOOLS` для MCP server
- [ ] `server.py`: MCP server entry point (stdio)
- [ ] Тесты: `tests/mcp_servers/test_facade_*.py`

#### CLI обновление

- [ ] `cli_commands/mcp.py`: `1c-ai mcp serve [--server NAME]`
- [ ] `cli_commands/generate.py`: использовать facade handlers

#### Persistence production

- [ ] `PostgresSaver` интеграция в `orchestrator/graph.py`
- [ ] Миграции (см. M2)
- [ ] Тесты: `tests/integration/test_persistence.py` (требует postgres)

#### Docker production

- [ ] `docker/Dockerfile.app` — финальная версия (multi-stage)
- [ ] `docker/Dockerfile.bsl-ls` — финальная версия
- [ ] `docker-compose.yml` — финальная версия с healthchecks
- [ ] `docker-compose.qdrant.yml` — override для Qdrant
- [ ] `.env.example` — пример конфигурации

#### Документация

- [ ] `README.md`: полная версия с Quick Start, Architecture, Deployment
- [ ] `AGENTS.md`: финальная версия со всеми правилами
- [ ] `CONTRIBUTING.md`: полная версия
- [ ] `CHANGELOG.md`: v0.4.0
- [ ] `docs/architecture/10-prompts-spec.md` (если ещё не создан)
- [ ] `docs/architecture/11-kb-seed-list.md` (если ещё не создан)

### 4.3. Критерий готовности

- [ ] `docker compose up -d` — все 3 контейнера запущены и здоровы
- [ ] Cursor подключается к MCP Facade, видит 8 tools
- [ ] `plan → gather → generate → validate → review` workflow работает через Cursor
- [ ] `1c-ai generate` CLI работает end-to-end
- [ ] Postgres persistence работает (рестарт контейнера не теряет state)
- [ ] Гибридный search находит релевантные модули
- [ ] Бенчмарк pgvector vs Qdrant проведён, решение зафиксировано
- [ ] `pytest tests/ -v --cov` — coverage ≥ 80%
- [ ] CI зелёная

---

## 5. Post-MVP (Спринты 5+)

Не для MVP. После того как Спринт 1-4 завершены и система работает.

### 5.1. Оптимизация

- [ ] Streaming responses (astream_events в LangGraph)
- [ ] Prompt caching (для повторяющихся system prompts)
- [ ] Batch API для LLM
- [ ] Multi-LLM routing (Planner=GPT-4o, Coder=Claude Sonnet)
- [ ] Prompt-caching для KB-правил

### 5.2. Dogfooding

- [ ] Использовать систему для разработки самой себя
- [ ] Сбор метрик: success rate, avg iterations, avg cost per task
- [ ] Тюнинг промптов по результатам

### 5.3. Расширение

- [ ] REST API (FastAPI) — для web UI
- [ ] IDE-плагин (LSP или MCP)
- [ ] GitHub Bot (webhook → orchestrator)
- [ ] Multi-config tasks (задача, затрагивающая несколько конфигураций)
- [ ] SaaS mode (multi-tenant) — если появятся пользователи

### 5.4. Безопасность

- [ ] SAST: bandit + semgrep
- [ ] DAST: malicious payload тесты на MCP
- [ ] SBOM: CycloneDX
- [ ] CVE monitor: pip-audit
- [ ] Code sandbox: 4 уровня изоляции для LLM-генерированного кода

### 5.5. Observability

- [ ] Prometheus metrics (опционально с NoOp fallback)
- [ ] Grafana dashboard
- [ ] Alerting на эскалации

---

## 6. Политика заполнения инфо-файлов

Эти правила — для меня как архитектора. Никакого мусора в публичных файлах.

### 6.1. README.md

**Что должно быть всегда:**
- 1-параграф description (что это)
- Статус (Architecture / Sprint 1 in progress / MVP ready / Production)
- Ссылка на архитектуру (CONCEPTUAL.md)
- Quick Start (минимум команд для запуска)
- Структура репозитория (короткая)
- Лицензия

**Что добавляется по мере реализации:**
- После Спринта 1: Quick Start с `1c-ai init && config add && config build`
- После Спринта 2: Quick Start с `1c-ai generate`
- После Спринта 4: Docker deployment, MCP integration с Cursor

**Чего НЕ должно быть:**
- Длинных описаний архитектуры (это в docs/)
- Списка всех ADR (это в adr/README.md)
- Changelog (это в CHANGELOG.md)
- Правил для контрибьюторов (это в CONTRIBUTING.md)
- Правил для AI-агентов (это в AGENTS.md)
- Бейджей которых нет (если CI нет — не ставить бейдж CI)

**Принцип:** README — это лицо проекта для случайного зрителя. 200 строк максимум, лучше меньше.

### 6.2. AGENTS.md

**Что должно быть всегда:**
- Рабочий процесс агента (4 этапа: правила → граф → документация → код)
- Архитектурные правила (НЕ нарушать)
- Технические правила (subprocess, secrets, BSL LS)
- Антипаттерны (НЕ делать)

**Что добавляется по инцидентам:**
- Каждое правило — результат реального инцидента, не фантазия
- Инцидент → правило → запись в "История инцидентов"
- Правило, которое не используется 6 месяцев → удалить

**Чего НЕ должно быть:**
- Дублирования правил из CONTRIBUTING.md
- Теоретических советов
- Правил без примера (инцидента)

**Принцип:** AGENTS.md — журнал инцидентов, не учебник. Каждая строка — кровью.

### 6.3. CONTRIBUTING.md

**Что должно быть всегда:**
- Перед началом работы (что прочитать)
- Команды разработки (clone, sync, test, lint)
- Формат коммитов
- Code style (ruff, mypy, строки)
- ADR процесс

**Что добавляется по мере роста:**
- После Спринта 1: "Running tests locally"
- После Спринта 2: "Debug pipeline with LangSmith"
- После Спринта 4: "Docker development setup"

**Чего НЕ должно быть:**
- Повторения README
- Правил для AI-агентов (это в AGENTS.md)
- Длинных туториалов

**Принцип:** CONTRIBUTING — для человека-контрибьютора. Краткость, конкретика.

### 6.4. CHANGELOG.md

**Формат:** [Keep a Changelog](https://keepachangelog.com/)

```markdown
# Changelog

## [Unreleased]

## [0.4.0] - 2026-XX-XX
### Added
- Facade lifecycle tools (7 tools + data_status)
- metadata/codebase/git MCP servers
- Hybrid search (BM25 + vector + RRF)
- Postgres persistence

## [0.3.0] - 2026-XX-XX
### Added
- Planner and Reviewer agents
- KB-as-code (5 patterns, 10 antipatterns)
- HBK parser for platform methods

## [0.2.0] - 2026-XX-XX
### Added
- Minimal pipeline (Coder + Validator)
- BSL LS MCP server
- LangSmith observability

## [0.1.0] - 2026-07-11
### Added
- Project skeleton (5 packages, 17 ADR)
- PathManager and ConfigRegistry
- XML parsers (Configuration, Catalog, Document, CommonModule)
- CLI: 1c-ai init, config add/build/list, validate
```

**Принцип:** только значимые изменения для пользователя. Внутренние рефакторинги — без записи (или в [Unreleased] → удалить перед release).

### 6.5. docs/architecture/

**Что должно быть:**
- CONCEPTUAL.md — обзор без кода (для сверки)
- 00-overview.md — технический обзор
- 01-09 — 9 шагов проектирования (контракты)
- 10-prompts-spec.md (после M1)
- 11-kb-seed-list.md (после M4)

**Чего НЕ должно быть:**
- Дублирования ADR
- Tutorial'ов (это в CONTRIBUTING или wiki)
- Документации API (это в docstrings)

**Принцип:** docs/architecture/ — это спецификации контрактов. Не изменяются без ADR.

### 6.6. adr/

**Шаблон:** см. adr/README.md

**Правила:**
- Каждый ADR — одно решение
- Статус: Accepted | Superseded | Deprecated
- Superseded → новый ADR с `supersedes: ADR-XXXX`
- Не удаляем, даже если устарел (история решений важна)
- Не более 2 страниц на ADR

---

## 7. Чек-листы готовности

### 7.1. Перед каждым коммитом

- [ ] `ruff check packages/` — без ошибок
- [ ] `mypy packages/` — без ошибок
- [ ] `pytest tests/ -m smoke` — зелёные
- [ ] `python scripts/check_package_boundaries.py` — OK
- [ ] В коммите нет: `.github-token`, `.env`, `data/`, `derived/`, `runtime/`
- [ ] Сообщение коммита: `<type>(<scope>): <description>`

### 7.2. Перед push

- [ ] Все из 7.1
- [ ] `pytest tests/` — все тесты зелёные (не только smoke)
- [ ] Если добавлен новый ADR — `adr/README.md` обновлён
- [ ] Если изменена архитектура — соответствующий ADR обновлён или создан новый

### 7.3. Перед релизом (v0.X.0)

- [ ] Все из 7.2
- [ ] Coverage ≥ 80%
- [ ] `CHANGELOG.md` обновлён
- [ ] `README.md` актуален
- [ ] `docker compose up -d` — все контейнеры здоровы
- [ ] End-to-end тест на реальной конфигурации
- [ ] Git tag `vX.Y.Z` создан
- [ ] GitHub Release создан (с notes из CHANGELOG)

### 7.4. Перед добавлением нового ADR

- [ ] Прочитаны существующие ADR — нет ли уже такого решения
- [ ] Контекст описан (какая проблема)
- [ ] Рассмотрены альтернативы (минимум 2)
- [ ] Решение обосновано
- [ ] Последствия (положительные и отрицательные)
- [ ] Связанные документы
- [ ] `adr/README.md` обновлён (добавлен в индекс)

---

## 8. Метакод-задачи (когда делать)

| ID | Задача | Когда делать | Артефакт |
|---|---|---|---|
| M1 | Структура Jinja2 промптов | До Спринта 2 | `docs/architecture/10-prompts-spec.md` |
| M2 | Postgres migration strategy | До Спринта 2 | ADR-0018 |
| M3 | Embeddings strategy | До Спринта 4 | ADR-0019 |
| M4 | KB seed content | До Спринта 3 | `docs/architecture/11-kb-seed-list.md` |
| M5 | LangSmith trace structure | До Спринта 2 | ADR-0020 |
| M6 | CI/CD workflow design | В Спринте 1 (первый коммит) | `.github/workflows/` |
| M7 | Test data strategy | В Спринте 1 (первый коммит) | `tests/fixtures/` |
| M8 | Migration path для старого репо | После Спринта 1 (опционально) | `scripts/migrate_from_dev_env.py` |

---

## 9. Стратегия работы с git

### 9.1. Ветвление

- `main` — стабильная, CI зелёная
- `feature/X` — для крупных фич (если нужно)
- `fix/X` — для bugfix'ов

Для solo-dev — чаще всего коммит сразу в `main`. Ветвление — только если задача большая и хочется изолировать.

### 9.2. Push стратегия

- Каждый коммит — push (не накапливать)
- После push — проверить CI статус
- Если CI красная — следующий коммит только fix

### 9.3. Токен

- Хранится в `/home/z/my-project/.github-token` (chmod 600)
- В `.gitignore` — исключён
- Push через `git -c credential.helper=...` — токен читается из файла при каждом push
- **НИКОГДА** не вставлять токен в remote URL
- **НИКОГДА** не коммитить `.env` с реальными секретами
- После сессии — токен остаётся в файле (для следующей сессии)

### 9.4. Security audit (после каждого push)

```bash
# Проверка что токен не утёк
TOKEN=$(cat /home/z/my-project/.github-token | tr -d '\n')
git -C /home/z/my-project/1c-ai-assistant log --all -p | grep -F "$TOKEN" && echo "❌ LEAK" || echo "✅ CLEAN"
git -C /home/z/my-project/1c-ai-assistant config --list | grep -F "$TOKEN" && echo "❌ LEAK" || echo "✅ CLEAN"
git -C /home/z/my-project/1c-ai-assistant remote -v | grep -F "$TOKEN" && echo "❌ LEAK" || echo "✅ CLEAN"
```

---

## 10. Файлы для следующих сессий

| Файл | Назначение |
|---|---|
| `/home/z/my-project/INTERNAL_ROADMAP.md` | Этот документ — план работы |
| `/home/z/my-project/worklog.md` | Журнал выполненных задач |
| `/home/z/my-project/.github-token` | Токен для git push (chmod 600) |
| `/home/z/my-project/1c-ai-assistant/` | Корень проекта |
| `/home/z/my-project/1c-ai-assistant/AGENTS.md` | Правила для AI-агентов |
| `/home/z/my-project/1c-ai-assistant/adr/` | 17 ADR |
| `/home/z/my-project/download/1c-ai-agent-architecture/` | Исходные архитектурные документы |

---

## 11. Текущий фокус

**Сейчас:** Завершён Спринт 0 (архитектура + initial commit).

**Следующий шаг:** Начать Спринт 1.

**Конкретно первое действие:** Проработать M6 (CI/CD) и M7 (test data) — они нужны в первом коммите Спринта 1.

После M6+M7 — начать реализацию `parsers/models/` (это фундамент для всего).

---

*Этот документ обновляется после каждого значимого шага. Последнее обновление: 2026-07-11.*
