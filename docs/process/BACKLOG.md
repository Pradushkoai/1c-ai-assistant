# BACKLOG.md — единый реестр техдолга и отложенных задач

> **Назначение:** одно место, где видно всё что отложено.
> Любая новая найденная проблема → запись здесь.
> При закрытии — пометить `[x]` и перенести в раздел «Закрыто».
>
> **Формат ID:** `TD-NNN` — сквозная нумерация.
> **Принцип:** если техдолг не здесь — его не существует.
> **ВАЖНО:** этот файл живёт в git репозитории (docs/process/), чтобы переживать сбросы окружения.

---

## 🔴 В работе (Этап 1 — Контекст для Coder)

### TD-S4.1-04: dependency graph builder — ПОСЛЕДНЯЯ ЗАДАЧА ЭТАПА 1
- **Источник:** старый репо 1c-ai-dev-env (dependency_graph.py)
- **Этап:** 1 (Sprint 4.1)
- **Приоритет:** MEDIUM
- **Описание:** Граф зависимостей между объектами метаданных (Catalog → Document
  через реквизит). Planner использует для декомпозиции.
- **Оценка:** 1 день

---

## 🟡 Этап 2 (Поиск и качество)

### TD-S4.2-01: ADR-0020 Embeddings strategy — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `e1c6330`
- **Решение:** ADR-0020 — гибридный BM25+pgvector+RRF, multilingual-e5-large
  1024 dim (BGE-M3 недоступен в fastembed), chunking по методам,
  4-layer индексация (platform/library/config/KB).

### TD-S4.2-02: codebase MCP (BM25 + pgvector) — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commits `0eaf241` (ч.1) + `08cd30f` (ч.2)
- **Решение:**
  - Часть 1: embeddings_indexer.py + vector_store.py (VectorStoreProtocol,
    PgVectorStore, InMemoryVectorStore) — ADR-0017 compliance.
  - Часть 2: codebase/server.py — 4 MCP tools (semantic_search, get_module,
    get_similar, call_graph). 9 тестов с InMemoryVectorStore.

### TD-S4.2-03: standards (1С СТО, БСП) — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `2e09542`
- **Решение:** knowledge-base/standards/ — 8 YAML-стандартов (4 СТО + 4 БСП).
  JSON Schema standard.schema.json. KBCollection.standards (3-й тип сущностей).
  2 новых MCP tools: kb.get_standard + kb.check_standards.
  4-й параллельный валидатор в validate_node (_run_standards_validator).
  ValidationFinding.source: добавлен 'kb_standards'. 39 новых тестов.
  MCP tools total: 21 (5→7 KB).

### TD-S4.2-04: BSL LS через Docker — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `80365fd`
- **Решение:**
  - `.dockerignore` — ускоряет docker build, предотвращает утечку секретов.
  - `docker/Dockerfile.bsl-ls` — мульти-stage build (alpine downloader + python:3.12-slim runtime),
    BSL LS v0.25.5 с sha256 проверкой, pinned Python-зависимости, OCI labels, HEALTHCHECK.
  - `docker/bsl_ls_http_server.py` — исправлен CLI-синтаксис BSL LS v0.25.x:
    `analyze --src <file> --format json --output <result.json>` (раньше был некорректный
    `analyze <file> --format json`). Добавлены: latency_ms метрика, structured logging,
    корректная обработка HTTP ошибок (504 timeout, 500 critical errors).
  - `docker-compose.yml` — healthcheck для `1c-ai-bsl-ls` (curl /health), зависимость
    `1c-ai-app` от `service_healthy` вместо `service_started`.
  - `LintOutput.latency_ms` + `FormatOutput.latency_ms` — проброс метрики в MCP contracts.
  - `tests/mcp_servers/test_bsl_ls_server.py` — 10 новых unit-тестов:
    TestLatencyMetric (3), TestLintRulesAndBaseline (3), TestErrorHandling (4) +
    3 integration-теста (TestBslLsIntegration, skip если BSL_LS_HTTP_URL не задан).

### TD-S4.2-05: `1c-ai library add` (БСП/БПО) — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `c756c74`
- **Решение:** agent/cli_commands/library.py — add/build/list/remove.
  Библиотеки индексируются как source_layer=library.

### TD-S4.2-06: Transitive closure для Planner/Reviewer — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `163cfc6`
- **Решение:** parsers/xml/dependency_graph.py — get_transitive_dependents
  (blast radius для Planner) + transitive call count для Reviewer.
  Coder получает только 1-hop зависимости.

### TD-S4.2-07: api-reference в pipeline (Gatherer) — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `f53c21f`
- **Решение:** `1c-ai config build` теперь строит api-reference.json, call-graph.json,
  dependency-graph.json. Gatherer загружает api-reference и передаёт Coder'у
  список существующих export-методов для целевого объекта.

---

## 🟢 Этап 3 (Production-readiness)

> **Статус:** ✅ ЗАВЕРШЁН (TD-S5-01/02/03/04 все закрыты 2026-07-13, 4/4 задач).
> **Цель этапа:** production-ready система для Cursor IDE — persistence, lifecycle,
> git-интеграция, production Docker.

### TD-S5-01: PostgresSaver persistence — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `408abe9`
- **Решение:**
  - `packages/orchestrator/src/orchestrator/persistence.py` — переписан из заглушки
    в рабочую реализацию: `AsyncPostgresSaver.from_conn_string()` (как async cm) +
    `await saver.setup()` (идемпотентное создание checkpoint-таблиц) + корректный
    connection lifecycle в `__aexit__`. Fallback на `MemorySaver` при отсутствии DSN
    или `langgraph-checkpoint-postgres`. `PersistenceError` (ABORT) при ошибке
    подключения. Добавлены `from_env()` (DATABASE_URL) и `async health_check()`.
  - `packages/orchestrator/src/orchestrator/state.py` — `schema_version: int = Field(default=1, ge=1)` в TaskState (ADR-0018).
  - `packages/agent/src/agent/cli_commands/generate.py` — `_run_pipeline` обёрнут в
    `async with PersistenceManager.from_env() as pm:`; checkpointer передаётся в
    `build_graph`. Production (DATABASE_URL) → Postgres; dev/tests → MemorySaver.
  - Миграции (ADR-0018, D-2026-07-13-05): `migrations/` — Alembic scaffolding
    (`alembic.ini` + `migrations/alembic/` + baseline `0001_baseline`) +
    TaskState pickle-миграции (`migrations/state/0001_initial.py`). Разделение
    schema-owner'ов: LangGraph ↔ своё (setup()), Alembic ↔ приложенческие таблицы.
  - `docker/postgres/init.sql` — комментарий актуализирован (setup() управляет
    checkpoint-таблицами).
  - `tests/orchestrator/test_persistence.py` — 21 unit-тест + 3 integration
    (skip-if TEST_POSTGRES_DSN not set). Integration доказывает «рестарт контейнера
    не теряет state» (checkpoint переживает новый PersistenceManager, тот же DSN).
  - `alembic` добавлен в dev-зависимости.
  - Тесты: 801 проходят + 6 skipped (3 BSL LS + 3 Postgres integration).
  - См. D-2026-07-13-04 (реализация), D-2026-07-13-05 (миграции).

### TD-S5-02: Facade handlers (8 lifecycle tools) — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `f9e454c`
- **Решение:**
  - **8 tools по ADR-0013** (не BACKLOG-список `start_task` etc. — расхождение
    зафиксировано в D-2026-07-13-07): `plan, gather, generate, validate, review,
    explain, run_cli, data_status`. Контракт выше предпочтений.
  - `packages/mcp_servers/src/mcp_servers/facade/handlers.py` — реализация
    `FacadeHandlers` с DI через конструктор: `state_factory`, `node_plan/gather/
    code/validate/review/commit` callables, `kb_server`, `bsl_ls_server`, `llm`,
    `path_manager`, `config_registry`. In-memory state dict (`plan_id → state`).
    `handle_review` с `proceed` → дополнительно `node_commit`. `FacadeNotConfiguredError`
    при отсутствии DI. Helpers: `_validate_plan_id`, `_parse_artifact_id`,
    `_find_subtask_idx`, `_find_plan_id_by_subtask`.
  - `packages/mcp_servers/src/mcp_servers/facade/server.py` — `create_facade_server()`
    возвращает `mcp.server.Server` с 8 tools (через `FACADE_TOOLS` + handlers dispatch).
    `run_facade_server()` (stdio), `run_sync()` (для `[project.scripts]`).
  - `packages/agent/src/agent/cli_commands/facade_entry.py` — `create_facade_handlers()`
    собирает handlers с DI из orchestrator.nodes + data_layer + mcp_servers
    (единственное место встречи mcp_servers.facade ↔ orchestrator, CONCEPTUAL §1.1).
  - Boundaries: 0 violations (mcp_servers НЕ импортирует orchestrator — DI через
    конструктор; facade → codebase intra-package разрешён).
  - `tests/mcp_servers/test_facade_handlers.py` — 35 тестов: 8 handlers happy path
    (mock nodes) + input validation + next_action correctness + state propagation
    + full workflow (plan→gather→generate→validate→review). `test_mcp_contracts.py`
    обновлён: `TestFacadeHandlers` проверяет `FacadeNotConfiguredError` (было
    NotImplementedError).
  - Тесты: 846 проходят + 6 skipped (+45 от facade). ruff чист. mypy 14 (базовая).
  - См. D-2026-07-13-07.

### TD-S5-03: git MCP (4 tools) — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `3a32362`
- **Решение:**
  - `packages/mcp_servers/src/mcp_servers/git/server.py` — `GitServer` класс с 4 async
    methods (create_branch, commit, open_pr, diff) через `asyncio.create_subprocess_exec`
    (shell=False, явные args list — нет shell-инъекций).
  - 4 Tool Implementations (`CreateBranchImplementation`, `CommitImplementation`,
    `OpenPrImplementation`, `DiffImplementation`) — обёртки для MCP server (по
    паттерну `bsl_ls/server.py`).
  - **Безопасность:**
    - `_validate_branch_name`: regex `^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,199}$` + запрет
      `..` (git ref naming rules).
    - `_validate_repo_path`: `Path(repo_path).resolve()` существует и is_dir.
    - `_validate_relative_paths` (commit files): нет абсолютных, нет `..` traversal.
    - `_scan_diff_for_secrets`: regex-скан diff на github_pat_*, ghp_*, AKIA*,
      private keys, Bearer tokens, Slack tokens. При находке — `SecretDetectedError`
      (ABORT, snippet маскирован в error message).
  - `open_pr` — `gh pr create --base --head --title --body --label`. `gh` CLI
    проверяется через `shutil.which`; если нет — `FileNotFoundError` с инструкцией.
    Auth через `GH_TOKEN` env (gh CLI стандарт).
  - Errors: `GitValidationError`, `GitCommandError` (non-zero exit + stderr),
    `GitTimeoutError` (subprocess timeout + kill), `SecretDetectedError`.
  - `git/__init__.py` — экспорт `GitServer`, `GIT_TOOLS`, 4 Implementation, 4 errors.
  - `git/contracts.py` — `__call__` обновлён: указывает на `*Implementation` (было
    "реализация в Sprint 4").
  - `tests/mcp_servers/test_git_server.py` — 59 тестов: validations (branch names,
    repo_path, relative paths), secret scan (7 паттернов), `_parse_diff_stat`,
    4 tools happy path (mock subprocess), error cases, timeout, Tool Implementations,
    integration (skip-if `TEST_GIT_REPO` not set).
  - Тесты: 905 проходят + 7 skipped (+59 от git). ruff чист. 0 boundaries. mypy 14.
  - См. D-2026-07-13-08.

### TD-S5-04: Docker production — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `c83ca2d`
- **Решение:**
  - `docker/Dockerfile.app` — переписан на **multi-stage** (builder + runtime):
    - **builder**: `python:3.12-slim` + gcc/g++/libpq-dev (build deps для C-extensions),
      `uv sync --all-extras` собирает `.venv`.
    - **runtime**: `python:3.12-slim` + только git/curl/ca-certificates, копирует
      `.venv` из builder. Non-root user (`app`). OCI labels. `HEALTHCHECK`.
  - `packages/agent/src/agent/cli_commands/health.py` — `1c-ai health` CLI команда:
    `PersistenceManager.health_check()` + BSL LS HTTP ping. JSON output, exit 0/1.
    Зарегистрирована в `cli.py`.
  - `docker-compose.yml` — healthcheck для `1c-ai-app`:
    `CMD-SHELL, 1c-ai health || exit 1`, interval 30s, timeout 10s, start_period 30s.
  - `.env.example` — все env vars с комментариями: `DATABASE_URL`, `BSL_LS_HTTP_URL`,
    `BSL_LS_TIMEOUT`, `VECTOR_STORE`, `LOG_FORMAT`, `GH_TOKEN`, `ZAI_API_KEY`,
    `ONEC_AI_PROJECT`, `TEST_POSTGRES_DSN`, `TEST_GIT_REPO`.
  - `docker-compose.override.yml` — dev: volume mount `./packages` (hot reload),
    `LOG_FORMAT=text`, `VECTOR_STORE=memory`, `restart: "no"`, `command: 1c-ai-mcp`,
    healthcheck disabled (быстрый старт).
  - `tests/agent/test_cli_health.py` — 16 тестов: MemorySaver ok, PostgresSaver
    ok/failed/error, BSL LS ok/500/connection-error/skipped, JSON output format,
    CLI registration, `_mask_dsn`.
  - Тесты: 921 проходят + 7 skipped (+16 от health). ruff чист. 0 boundaries.
    mypy 14 (базовая TD-011, новых нет).
  - См. D-2026-07-13-09.

---

## 🟣 Когда-нибудь (Post-MVP)

### TD-005: Streaming responses (astream_events в LangGraph)
- **Приоритет:** LOW
- **Описание:** Streaming для долгих pipeline runs. Сейчас ainvoke блокирует.

### TD-006: Prompt caching
- **Приоритет:** LOW
- **Описание:** Кеширование system prompts для снижения стоимости LLM.

### TD-007: Multi-LLM routing
- **Приоритет:** LOW
- **Описание:** Planner=GPT-4o, Coder=Claude Sonnet. Сейчас одна модель на всё.

### TD-011: ZaiLLM mypy cleanup (LangChain strict typing) — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit (pending, TD-S7-03)
- **Решение:**
  - `zai_llm.py`: `_content_to_str()` helper для LangChain content (str | list) → str
    (убрал `__add__`/`append` type errors). `type: ignore[call-arg]` на `super().__init__`.
    `type: ignore[override]` на `with_structured_output` (LangChain LSP violation).
    `_call_cli` как real метод класса (вместо monkey-patch в конце файла).
  - `vector_store.py`: `int(cur.rowcount)`, `tuple[Any, ...]`, `float(dot / ...)`.
  - `form.py`: `str(elem.text.strip())` для `_extract_v8_content`.
  - `library.py`: `dict[str, Any]` вместо `dict` (type-arg) + `from typing import Any`.
  - `codebase/server.py`: `embedding: list[float] | None = chunk.get("embedding")`.
  - **mypy: 0 ошибок** (было 14, все закрыты). Базовая линия TD-011 ликвидирована.

---

## 🟠 Stage 4 (Contract Compliance) — ЗАКРЫТ ✅

> **Статус:** ✅ ЗАВЕРШЁН (4/4) — TD-S6-01/02/03/04 все закрыты (2026-07-13).
> **Цель этапа:** закрыть 3 архитектурных пробела (metadata MCP, commit→git, mcp serve).

### TD-S6-01: metadata MCP server + orchestrator wiring — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `0dc3d47`
- **Решение:** `MetadataServer` с 4 tools (get_metadata, get_form_structure,
  get_api_reference, get_dependency_graph). `gather_node` убран прямой FS-доступ,
  ходит через metadata_server (DI). `plan_node` — metadata_server DI (ADR-0005).
  Facade `run_cli` proxy поддерживает metadata.*. 24 теста. Архитектурный пробел #1
  закрыт (ADR-0003/0005/0010). См. D-2026-07-13-10.

### TD-S6-02: commit_node → git MCP интеграция — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `25ef38f`
- **Решение:** `commit_node` переписан: real git flow (create_branch + commit + опц.
  open_pr через GitServer) если `git_server` + `1C_AI_REPO_PATH` заданы; fallback
  file save иначе. Facade `handle_review → proceed` реально коммитит. 14 тестов.
  Архитектурный пробел #2 закрыт (ADR-0004/0005/0010). См. D-2026-07-13-11.

### TD-S6-03: `1c-ai mcp serve` CLI + режим C — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `c0d6658`
- **Решение:** `server_factory.py` единая factory: `create_domain_server(name)` для
  6 серверов (facade/metadata/codebase/kb/bsl_ls/git). `1c-ai mcp serve --server NAME`
  (stdio). `--list` показывает серверы + tools count. Cursor может подключиться к
  любому MCP напрямую (режим C, CONCEPTUAL §1.2). 29 тестов. Архитектурный пробел #3
  закрыт (ADR-0003). См. D-2026-07-13-12.

### TD-S6-04: Integration tests + docs sync — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `23613bb`
- **Решение:** `tests/integration/` с smoke tests (Postgres, BSL LS, git, metadata).
  CI workflow обновлён (env vars + temp git repo). AGENTS.md, CHANGELOG.md,
  INTERNAL_ROADMAP.md, CONTRIBUTING.md актуализированы.

---

## 🔵 Stage 5 (Production Hardening) — ЗАКРЫТ ✅

> **Статус:** ✅ ЗАВЕРШЁН (4/4) — TD-S7-01/02/03/04 все закрыты (2026-07-13).
> **Цель этапа:** production hardening (survival-restart, REST API, mypy cleanup, CI).

### TD-S7-01: Production survival-restart для Facade — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `1a20095`
- **Решение:** `FacadeStateStore` через LangGraph checkpointer (aput/aget_tuple).
  State по plan_id переживает рестарт контейнера (PostgresSaver). In-memory fallback.
  `_subtask_to_plan` cache. 19 тестов. Архитектурный пробел #4 закрыт.
  См. D-2026-07-13-13.

### TD-S7-02: REST API HTTP server — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `288e1fb`
- **Решение:** `1c-ai serve` (FastAPI :8000). GET /health (Docker/k8s probe),
  GET /servers, GET /tools/{server}, POST /facade/{tool}, POST /domain/{server}/{tool}.
  Stateless через store. Dockerfile healthcheck обновлён (curl /health). 19 тестов.
  См. D-2026-07-13-14.

### TD-S7-03: ZaiLLM mypy cleanup (TD-011) — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `4bd9db9`
- **Решение:** все 14 mypy ошибок закрыты (zai_llm.py, vector_store.py, form.py,
  library.py, codebase/server.py). **mypy: 0 ошибок** (TD-011 закрыт).
  См. D-2026-07-13-15.

### TD-S7-04: Real integration tests run в CI + ruff format — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit `849765c`
- **Решение:** `ruff format` применён ко всем файлам (CI `--check` зелёный).
  integration.yml: `docker compose up --build`. 4 новых integration test
  (REST API smoke + FacadeStateStore survive-restart с Postgres).

---

## ✅ Закрыто

### TD-S4.1-03: api-reference indexer — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-12
- **Закрыто в:** commit `4c255d4`
- **Решение:** parsers/indexers/api_reference_indexer.py — извлечение export-методов.
  15 тестов. Проверен на УТ11: 43 метода из 5 модулей.

### TD-S4.1-02: Call graph builder — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-12
- **Закрыто в:** commit `ccf158a`
- **Решение:** parsers/bsl/call_graph.py — двухпроходный regex-парсер.
  13 тестов. Проверен на УТ11: 27 рёбер из 4 модулей.

### TD-S4.1-01: Form/Subsystem/Role парсеры — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-12
- **Закрыто в:** commits `169cbf4`, `9ef4856`
- **Решение:** parsers/xml/form.py (14 тестов) + parsers/xml/subsystem_role.py (15 тестов).
  Проверены на УТ11: Form (элементы, события), Subsystem (17 объектов), Role (имя, синоним).

### TD-002: 3 boundary violations (orchestrator → mcp_servers) — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-12 (восстановлено)
- **Решение:** Dependency injection через `functools.partial` в `build_graph()`.

### TD-004: HBK Container32 парсер — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-12 (восстановлено)
- **Решение:** parsers/hbk/container32.py (zlib + HTML). 10,150 методов.

### TD-000: iter_metadata_files не работал на реальной выгрузке — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-12 (восстановлено)
- **Решение:** glob('*.xml') в корне {Type}s/.

---

## 📊 Сводка

| Статус | Количество |
|---|---|
| В работе (Этап 1) | 0 (Этап 1 завершён) |
| Этап 2 — открыто | 0 (**Этап 2 ЗАВЕРШЁН**) |
| Этап 2 — закрыто | 7 (TD-S4.2-01/02/03/04/05/06/07) |
| Stage 3 — открыто | 0 (**Stage 3 ЗАВЕРШЁН**) |
| Stage 3 — закрыто | 4 (TD-S5-01/02/03/04) |
| Stage 4 — открыто | 0 (**Stage 4 ЗАВЕРШЁН**) |
| Stage 4 — закрыто | 4 (TD-S6-01/02/03/04) |
| Stage 5 — открыто | 0 (**Stage 5 ЗАВЕРШЁН**) |
| Stage 5 — закрыто | 4 (TD-S7-01/02/03/04) |
| Когда-нибудь — открыто | 3 (TD-005, TD-006, TD-007) |
| Когда-нибудь — закрыто | 1 (TD-011) |
| Закрыто | 22 (TD-000, TD-002, TD-004, TD-011, TD-S4.1-01..04, TD-S4.2-01..07, TD-S5-01..04, TD-S6-01..04, TD-S7-01..04) |
| **Всего** | **25** (22 закрыто + 3 post-MVP открыто) |

---

## Правила ведения

1. **Новый техдолг** → новая запись в соответствующем разделе
2. **Закрытие** → пометить `[x]`, перенести в «Закрыто» с датой и commit SHA
3. **Ссылки** — обязательны: откуда задача (источник), куда влияет
4. **Приоритет** — CRITICAL / HIGH / MEDIUM / LOW
5. **Оценка** — в часах/днях, грубо
6. **Зависимости** — явно, если есть
7. **Принцип «Глубина сначала»** — качество важнее скорости (D-2026-07-12-08)
