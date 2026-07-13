# DECISIONS.md — журнал архитектурных и операционных решений

> **Назначение:** фиксация решений, которые меняют план или архитектуру.
> ADR — для фундаментальных решений (язык, фреймворк, схема БД), ~20 за проект.
> DECISIONS — для операционных (отложить X, заменить Y, переключить фокус).
>
> **Формат ID:** `D-YYYY-MM-DD-NN` — дата + порядковый номер за день.
> **Принцип:** любое отклонение от плана → запись здесь.
> **ВАЖНО:** этот файл живёт в git репозитории (docs/process/), чтобы переживать сбросы окружения.

---

## Записи (новые сверху)

### D-2026-07-13-14: TD-S7-02 — REST API HTTP server (`1c-ai serve`, FastAPI)

**Дата:** 2026-07-13
**Тип:** architecture + implementation (TD-S7-02, Stage 5 задача 2/4)
**Контекст:** Stage 4 закрыл 3 пробела, Stage 5 TD-S7-01 закрыл survival-restart.
Остальной пробел: Facade доступен только через MCP stdio (`1c-ai mcp serve`).
stdio не работает для удалённых клиентов, k8s probes, browser-based IDE. CONCEPTUAL
§1.2 режим A упоминал "CLI `1c-ai generate`, REST API" — REST API не был реализован.
Docker-compose port 8000 зарезервирован "для REST API (спринт 5+)" — сейчас пришёл.

**Решение:**
1. **`packages/agent/src/agent/cli_commands/serve.py`** — `cmd_serve(host, port)`:
   запускает FastAPI/uvicorn HTTP server. Делегирует в `mcp_servers.http_server`.
2. **`packages/mcp_servers/src/mcp_servers/http_server.py`** — `create_http_app(handlers)`:
   FastAPI app с endpoints:
   - `GET /health` — health check (PersistenceManager.health_check + BSL LS ping).
     Возвращает JSON `{"status": "ok"|"failed", "checks": {...}}`. Для Docker/k8s probe.
   - `GET /servers` — список доступных MCP серверов (через `server_factory.AVAILABLE_SERVERS`).
   - `GET /tools/{server_name}` — список tools для сервера.
   - `POST /facade/{tool}` — вызов Facade lifecycle tool (plan/gather/generate/validate/
     review/explain/run_cli/data_status). Body = tool args. Response = JSON.
   - `POST /domain/{server_name}/{tool}` — вызов доменного tool (metadata/codebase/kb/
     bsl_ls/git). Body = tool args.
   - ErrorHandler: ToolError → 400, неизвестный tool → 404, внутренняя ошибка → 500.
3. **`packages/agent/src/agent/cli.py`** — `@main.command() def serve()` с `--host`
   (default 0.0.0.0) и `--port` (default 8000).
4. **`docker-compose.yml`** — обновить healthcheck для `1c-ai-app`: `curl -f http://localhost:8000/health`
   вместо `1c-ai health` (HTTP probe более стандартен для Docker/k8s).
5. **Тесты** `tests/agent/test_cli_serve.py`:
   - `GET /health` → 200 + JSON structure (status, checks).
   - `GET /servers` → 200 + 6 серверов.
   - `GET /tools/facade` → 200 + 8 tools.
   - `POST /facade/data_status` → 200 + JSON result.
   - `POST /facade/plan` с mock handlers → 200 + plan_id.
   - `POST /facade/unknown` → 404.
   - `POST /domain/unknown_server/foo` → 404.
   - CLI registration: `1c-ai serve --help`.

**ADR compliance:**
- ADR-0003 (MCP-архитектура: Facade + 5 доменных серверов) — HTTP access к любому.
- ADR-0013 (Agent-Facade) — Facade через HTTP (режим A: REST API).
- ADR-0015 (3-container deployment) — port 8000 finally используется.

**Реализация:** commit (pending).

**Последствия:**
- Положительные: Facade доступен через HTTP (удалённые клиенты, k8s probes, browser
  IDE); /health endpoint для Docker/k8s; единый entry point для всех tools; foundation
  для web UI (future).
- Отрицательные: HTTP server — stateless (state через FacadeStateStore, уже готово
  TD-S7-01); без auth (future TD — добавить API key/OAuth для production).

**Связанные:** ADR-0003, ADR-0013, ADR-0015, BACKLOG TD-S7-02, D-2026-07-13-13
(survival-restart — stateless HTTP работает через store).

---

### D-2026-07-13-13: TD-S7-01 — Production survival-restart для Facade (FacadeStateStore)

**Дата:** 2026-07-13
**Тип:** architecture + implementation (TD-S7-01, Stage 5 задача 1/4)
**Контекст:** Stage 4 закрыл 3 архитектурных пробела, но остался 4-й: FacadeHandlers
использовал in-memory dict `_states: dict[plan_id, TaskState]` (D-2026-07-13-07).
Это значит: рестарт контейнера → потеря всех активных Cursor-сессий. Даже с
PostgresSaver (TD-S5-01) persistence работал только для `1c-ai generate` (LangGraph
checkpoint), но не для Facade (in-memory state). Для production deployment это
критичный пробел: долгие задачи (plan → gather → generate → validate → review, с
ожиданием между вызовами) теряются при любом restart.

**Решение:**
1. **`packages/mcp_servers/src/mcp_servers/facade/state_store.py`** — `FacadeStateStore`:
   - `load_state(plan_id) -> TaskState | None` — через `checkpointer.aget_tuple(config)`
     где `thread_id = plan_id`. Десериализация `TaskState.model_validate_json(...)` из
     `checkpoint["channel_values"]["task_state"]`.
   - `save_state(plan_id, state)` — через `checkpointer.aput(config, checkpoint, metadata, new_versions)`.
     Checkpoint structure: `{v:3, id:uuid, ts:ISO, channel_values:{"task_state": json_str},
     channel_versions:{}, versions_seen:{}, pending_sends:[]}`. Используем
     `model_dump_json()` / `model_validate_json()` для round-trip (обходит strict datetime).
   - DI: `checkpointer: Any = None`. Если None → in-memory fallback (dict[plan_id, json_str]).
     Backward compat для tests/dev без persistence.
   - `is_persistent` property (True если checkpointer задан и is_postgres).
2. **`FacadeHandlers`** — `_get_state`/`_save_state` теперь async, ходят через
   `self._state_store`. `_states` dict убран (заменён на store). `_subtask_to_plan`
   in-memory cache (заполняется при handle_plan/gather/generate; после restart клиент
   должен начать с plan — reasonable для MVP). Все handlers обновлены: `await self._get_state(...)`
   вместо sync.
3. **`facade_entry.py`** — создаёт `PersistenceManager.from_env()` → `FacadeStateStore(checkpointer=pm.get_checkpointer())`
   → `FacadeHandlers(state_store=...)`. PersistenceManager lifecycle: для MCP stdio
   server (долгоживущий процесс) — открывается один раз при старте, закрывается при
   shutdown. Для `1c-ai mcp serve` — в `cmd_mcp_serve`.
4. **Тесты** `tests/mcp_servers/test_facade_state_store.py`:
   - Unit: in-memory fallback (no checkpointer), load/save round-trip, load None if
     not saved, save overwrites.
   - Mock checkpointer: aput/aget_tuple mock, load после save, survive-restart (2
     store instances с тем же mock checkpointer — второй находит state от первого).
   - TaskState round-trip (model_dump_json → model_validate_json) с datetime, subtasks,
     iterations.
   - FacadeHandlers с state_store: handle_plan сохраняет в store, handle_gather
     загружает из store.

**ADR compliance:**
- ADR-0014 (PersistenceError + PostgresSaver) — Facade использует PersistenceManager.
- ADR-0018 (TaskState migration) — schema_version в state, migration-ready.
- ADR-0013 (Agent-Facade) — state по plan_id, thread_id = plan_id (как в generate.py).
- CONCEPTUAL §1.1 — mcp_servers.facade НЕ импортирует orchestrator (DI через
  state_store, checkpointer как Any).

**Реализация:** commit (pending).

**Последствия:**
- Положительные: архитектурный пробел #4 закрыт; Facade state переживает рестарт
  контейнера (PostgresSaver); backward compat (in-memory fallback для tests); foundation
  для TD-S7-02 (REST API — stateless HTTP handlers могут использовать store).
- Отрицательные: `_subtask_to_plan` in-memory cache — после restart handle_validate/review
  без явного plan_id не найдут state (клиент должен начать с plan). Задокументировано
  как MVP-ограничение; future TD — расширить artifact_id или добавить plan_id param.

**Связанные:** ADR-0013, ADR-0014, ADR-0018, BACKLOG TD-S7-01, D-2026-07-13-04
(PersistenceManager), D-2026-07-13-07 (FacadeHandlers in-memory state).

---

### D-2026-07-13-12: TD-S6-03 — `1c-ai mcp serve` CLI + режим C (закрыть архитектурный пробел #3)

**Дата:** 2026-07-13
**Тип:** architecture + implementation (TD-S6-03, Stage 4 задача 3/4)
**Контекст:** Архитектурный пробел #3: `1c-ai mcp serve` CLI не существовал.
INTERNAL_ROADMAP Sprint 4 явно требовал: `cli_commands/mcp.py`: `1c-ai mcp serve
[--server NAME]`. Режим C (CONCEPTUAL: power-user → напрямую к доменному MCP) не
работал — Cursor не мог подключиться к `metadata`/`codebase`/`kb`/`bsl_ls`/`git`
как отдельным MCP stdio-серверам. Только Facade имел `create_facade_server()`.

**Решение:**
1. **`packages/mcp_servers/src/mcp_servers/server_factory.py`** — единая factory:
   - `create_domain_server(server_name, **kwargs)` → `mcp.server.Server` для любого
     из 6 серверов (facade, metadata, codebase, kb, bsl_ls, git).
   - Для каждого: `list_tools()` из `*_TOOLS` контрактов, `call_tool()` диспатчит
     к Implementation (metadata/bsl_ls/codebase/git) или напрямую к KbServer методам (kb).
   - `run_domain_server(server_name, **kwargs)` — stdio loop.
   - `SERVER_NAMES` — frozenset валидных имён.
   - `AVAILABLE_SERVERS` — dict {name: tools_count} для `--list`.
2. **`packages/agent/src/agent/cli_commands/mcp.py`** — `1c-ai mcp serve --server NAME`:
   - `--server` (required): facade|metadata|codebase|kb|bsl_ls|git.
   - `--list`: показать доступные серверы + tools count.
   - Вызывает `create_domain_server(server_name)` → `run_domain_server(server_name)`.
3. **`packages/agent/src/agent/cli.py`** — `@main.group() def mcp()` + `@mcp.command("serve")`.
4. **Тесты** `tests/agent/test_cli_mcp.py`:
   - `1c-ai mcp serve --list` показывает 6 серверов.
   - `1c-ai mcp serve --server facade` создаёт Server (mock run).
   - `--server unknown` → error.
   - `create_domain_server()` для каждого имени → Server instance с tools.
   - `SERVER_NAMES` содержит 6 имён.

**ADR compliance (закрываются):**
- ADR-0003 (MCP-архитектура: Facade + 5 доменных серверов) — все 6 серверов
  доступны как MCP stdio.
- CONCEPTUAL §1.2 (режим C: power-user → напрямую к доменному MCP) — работает.

**Реализация:** commit (pending).

**Последствия:**
- Положительные: архитектурный пробел #3 закрыт; Cursor может подключиться к любому
  серверу напрямую; единая factory (DRY); `--list` для discoverability.
- Отрицательные: `create_domain_server()` для kb создаёт KbServer без DI (default
  kb_dir) — для production нужна настройка через env (отдельный TD).

**Связанные:** ADR-0003, CONCEPTUAL §1.2, BACKLOG TD-S6-03, D-2026-07-13-09
(Facade create_facade_server pattern).

---

### D-2026-07-13-11: TD-S6-02 — commit_node → git MCP интеграция (закрыть архитектурный пробел #2)

**Дата:** 2026-07-13
**Тип:** architecture + implementation (TD-S6-02, Stage 4 задача 2/4)
**Контекст:** Архитектурный пробел #2: `commit_node` писал файлы в
`runtime/generated/` (Sprint 2 логика: `commit_sha="n/a (Sprint 2: file save)"`).
`GitServer` (TD-S5-03) уже существует с 4 tools, но `commit_node` его не использует.
Нарушение ADR-0004 (hierarchical orchestration) + ADR-0010 (tool contracts) +
ADR-0005 (TOOL_GROUPS[COMMITTER] = git.*). Facade `handle_review → proceed →
node_commit` писал файл, не создавал branch/commit/PR.

**Решение:**
1. **`orchestrator/nodes/commit.py`** — переписан:
   - DI через конструктор: `git_server: Any = None`, `repo_path: str | None = None`.
   - Если `git_server` задан AND `repo_path` задан → real git flow:
     - `git_server.create_branch(repo_path, branch_name)` — branch `feature/{task_id[:8]}-{subtask_id[:8]}`.
     - Write code to `{repo_path}/{file_path}` (relative path, derived from subtask.target_module).
     - `git_server.commit(repo_path, message, files=[file_path], branch=branch_name)`.
     - Если `open_pr=True` (env `1C_AI_OPEN_PR=1`) → `git_server.open_pr(...)`.
     - `CommitResult` с реальным `commit_sha`, `branch_name`, `pr_url` (если PR).
   - Если `git_server=None` OR `repo_path=None` → **fallback** на Sprint 2 логику
     (file save в `runtime/generated/`). Backward compat для dev/tests.
   - `file_path` derivation: `CommonModule.Имя` → `CommonModules/Имя/Ext/Module.bsl`
     (по convention 1С); иначе — `Generated/{subtask_id}_{iter}.bsl`.
2. **`orchestrator/graph.py`** — `build_graph(git_server=..., repo_path=...)`.
   `commit_node` получает `partial(commit_node, git_server=git_server, repo_path=repo_path)`.
3. **`agent/cli_commands/generate.py`** + **`facade_entry.py`** — создать `GitServer`,
   читать `1C_AI_REPO_PATH` env (путь к git-репозиторию для коммитов). Передать в
   `build_graph` + `FacadeHandlers`.
4. **`mcp_servers/facade/handlers.py`** — `FacadeHandlers.__init__` + `git_server` +
   `repo_path`. `handle_review → proceed → node_commit` пробрасывает `git_server`
   и `repo_path` в вызов `node_commit`.
5. **Тесты** `tests/orchestrator/test_commit_node.py` (новый):
   - Real git flow (mock GitServer): create_branch + commit + CommitResult с sha.
   - open_pr flow (mock GitServer.open_pr).
   - Fallback file save (git_server=None): Sprint 2 логика, warning в log.
   - file_path derivation для CommonModule vs other.
   - Обновить `test_facade_handlers.py`: mock node_commit принимает git_server/repo_path.

**ADR compliance (закрываются):**
- ADR-0004 (Hierarchical orchestration) — commit_node реально коммитит.
- ADR-0010 (MCP tool contracts) — git_server как MCP tool.
- ADR-0005 (TOOL_GROUPS[COMMITTER] = git.*) — Committer использует git tools.

**Реализация:** commit (pending).

**Последствия:**
- Положительные: архитектурный пробел #2 закрыт; pipeline end-to-end контракт-совместим
  (plan → gather → code → validate → review → **real git commit**); foundation для
  TD-S6-03 (mcp serve — git server как отдельный MCP).
- Отрицательные: real git flow требует `1C_AI_REPO_PATH` env (без него — fallback file
  save, задокументировано); `open_pr` требует `gh` CLI + `GH_TOKEN` (без них — commit
  без PR, warning).

**Связанные:** ADR-0004, ADR-0005, ADR-0010, BACKLOG TD-S6-02, D-2026-07-13-08
(GitServer), D-2026-07-13-10 (предыдущая задача).

---

### D-2026-07-13-10: TD-S6-01 — metadata MCP server + orchestrator wiring (закрыть архитектурный пробел #1)

**Дата:** 2026-07-13
**Тип:** architecture + implementation (TD-S6-01, Stage 4 задача 1/4)
**Контекст:** Stage 3 завершён, но архитектурный аудит выявил 3 пробела. TD-S6-01
закрывает первый: `metadata/server.py` НЕ существовал (только contracts с
NotImplementedError). `gather_node` читал `api-reference.json` напрямую из FS
через `PathManager` (нарушение ADR-0003 MCP-архитектура + ADR-0010 tool contracts —
оркестратор должен ходить через MCP, не FS). `plan_node` вообще не получал
структурный контекст (`metadata.get_dependency_graph` в TOOL_GROUPS[PLANNER], но
никто не вызывал). Facade `run_cli` proxy возвращал warning "metadata.* будут
добавлены в следующих спринтах".

**Решение:**
1. **`packages/mcp_servers/src/mcp_servers/metadata/server.py`** — `MetadataServer`
   класс с 4 async methods:
   - `get_metadata(object_ref, config_name, config_version)` → `load_metadata_index`
     + `get_object_from_index` → Pydantic ObjectMetadata/CatalogMetadata/...
   - `get_form_structure(object_ref, form_name, config_name, config_version)` →
     парсинг Form.xml через `parsers.xml.form.parse_form` (read-only, по запросу).
   - `get_api_reference(module_name, config_name, config_version)` →
     `load_api_reference` + фильтрация по module_name.
   - `get_dependency_graph(config_name, config_version, object_ref, direction, depth)`
     → `load_dependency_graph` + фильтрация по object_ref + direction + depth
     (transitive closure для Planner).
   - DI через конструктор: `path_manager: PathManager | None = None`. Если None —
     создаётся через `PathManager()`.
2. **4 Tool Implementations** (`GetMetadataImplementation`, etc.) — обёртки для
   MCP server (по паттерну bsl_ls/git).
3. **`metadata/__init__.py`** — экспорт `MetadataServer`, `METADATA_TOOLS`, 4
   Implementation.
4. **`orchestrator/nodes/gather.py`** — убрать прямой FS-доступ (`PathManager` +
   `load_api_reference`). Вместо этого — DI `metadata_server: Any = None`. Если
   задан — `await metadata_server.get_api_reference(...)` для target_module. Если
   None — warning, контекст без API reference (backward compat для тестов без DI).
5. **`orchestrator/nodes/plan.py`** — добавить `metadata_server: Any = None`. Если
   задан — `await metadata_server.get_dependency_graph(...)` для структурного
   анализа (blAST radius для декомпозиции). Если None — fallback на single subtask
   (как сейчас).
6. **`orchestrator/graph.py`** — `build_graph(metadata_server=...)`. `plan_node` и
   `gather_node` получают `partial(..., metadata_server=metadata_server)`.
7. **`agent/cli_commands/facade_entry.py`** + **`generate.py`** — создать
   `MetadataServer`, передать в `build_graph` + `FacadeHandlers`.
8. **`facade/handlers.py`** — `run_cli` proxy расширить на `metadata.*` (4 methods).
9. **Тесты** `tests/mcp_servers/test_metadata_server.py`:
   - Unit: 4 tools happy path (mock PathManager/load_*), error cases (файл не
     найден, невалидный object_ref), Tool Implementations.
   - Обновить `test_facade_handlers.py`: `run_cli` proxy metadata.* happy path.

**ADR compliance (закрываются):**
- ADR-0003 (MCP-архитектура: Facade + 5 доменных серверов) — metadata server
  существует и работает.
- ADR-0005 (TOOL_GROUPS registry) — Planner/Gatherer реально вызывают tools из
  своих групп через MCP.
- ADR-0010 (MCP tool contracts — двойной контракт) — 4 tools с реализацией.
- CONCEPTUAL §1.1 (зависимости только вниз) — orchestrator НЕ импортирует
  parsers/data_layer напрямую для metadata (через MCP server).

**Реализация:** commit (pending).

**Последствия:**
- Положительные: архитектурный пробел #1 закрыт; gather/plan ходят через MCP
  (контракт-совместимо); run_cli proxy поддерживает metadata.*; foundation для
  TD-S6-02 (commit_node → git) и TD-S6-03 (mcp serve).
- Отрицательные: gather/plan теперь требуют metadata_server для полного
  контекста (без него — деградация с warning, backward compat сохранён).

**Связанные:** ADR-0003, ADR-0005, ADR-0010, CONCEPTUAL §1.1, BACKLOG TD-S6-01,
D-2026-07-13-09 (предыдущая задача).

---

### D-2026-07-13-09: TD-S5-04 — Docker production: multi-stage + `1c-ai health` + .env.example

**Дата:** 2026-07-13
**Тип:** architecture + infrastructure (TD-S5-04, Stage 3 задача 4/4, ЗАВЕРШАЮЩАЯ)
**Контекст:** `docker/Dockerfile.app` был одно-stage (большой образ, build deps в
runtime). Не было healthcheck для `1c-ai-app`. Не было `.env.example`.
Не было `docker-compose.override.yml` для dev. BACKLOG TD-S5-04 требует:
multi-stage Dockerfile.app, healthchecks, .env.example, docker-compose.override.

**Решение:**
1. **Multi-stage `Dockerfile.app`** (builder + runtime):
   - **builder**: `python:3.12-slim` + build deps (gcc для C-extensions), `uv sync
     --all-extras` собирает wheels в `/app/.venv`.
   - **runtime**: `python:3.12-slim` + только runtime deps (git, curl, ca-certificates),
     копирует `.venv` из builder. Образ ~250 МБ (было ~400 МБ).
   - OCI labels (org.opencontainers.image.*), non-root user (`app`), `HEALTHCHECK`.
2. **`1c-ai health` CLI команда** — проверка состояния для Docker healthcheck:
   - `PersistenceManager.health_check()` (если `DATABASE_URL` задан — PostgresSaver
     ping; иначе MemorySaver → True).
   - BSL LS HTTP ping (если `BSL_LS_HTTP_URL` задан — GET /health; иначе skip).
   - Exit 0 если OK, 1 если не OK. JSON output для логов.
3. **`docker-compose.yml`** — healthcheck для `1c-ai-app`:
   `CMD-SHELL`, `1c-ai health || exit 1`, interval 30s, timeout 10s, start_period 30s.
   `1c-ai-app` depends_on postgres + bsl-ls (service_healthy).
4. **`.env.example`** — все env vars с комментариями:
   `DATABASE_URL`, `BSL_LS_HTTP_URL`, `VECTOR_STORE`, `LOG_FORMAT`, `GH_TOKEN`,
   `ZAI_API_KEY`, `TEST_POSTGRES_DSN`, `ONEC_AI_PROJECT`.
5. **`docker-compose.override.yml`** — для dev:
   - Volume mount `.` → `/app` (hot reload исходников).
   - `LOG_FORMAT=text` (читаемость в dev).
   - `restart: "no"` (dev — не перезапускать автоматически).
   - Override command для MCP server (если разработка Facade).

**Health endpoint:** НЕ добавляю HTTP server (FastAPI) — это TD-S5-05+ (REST API).
Для MVP Docker production healthcheck через CLI достаточно. Docker перезапустит
контейнер если `1c-ai health` падает 3 раза подряд.

**Тесты** (`tests/agent/test_cli_health.py`):
- `1c-ai health` с MemorySaver (no DATABASE_URL) → exit 0.
- `1c-ai health` с PostgresSaver (mock health_check False) → exit 1.
- `1c-ai health` с BSL LS (mock httpx 200) → exit 0; (mock 500) → exit 1.
- JSON output format.

**Реализация:** commit (pending).

**Последствия:**
- Положительные: production-ready Docker (multi-stage, healthcheck, .env.example);
  `1c-ai health` reusable для CI/CD; dev override для hot reload.
- Отрицательные: `1c-ai health` — CLI, не HTTP (для orchestration типа k8s
  нужен HTTP probe — отдельный TD).

**Связанные:** ADR-0015 (3-container deployment), D-2026-07-13-04 (PersistenceManager
health_check), BACKLOG TD-S5-04.

---

### D-2026-07-13-08: TD-S5-03 — git MCP server: async subprocess + безопасность

**Дата:** 2026-07-13
**Тип:** architecture + implementation (TD-S5-03, Stage 3 задача 3/4)
**Контекст:** BACKLOG TD-S5-03 требует 4 git tools (create_branch, commit, open_pr,
diff) через subprocess git CLI. Контракты (`git/contracts.py`) уже есть (Sprint 1.5),
`__call__` поднимает `NotImplementedError`. `gh` CLI нет в окружении — `open_pr`
будет падать с понятной ошибкой; тесты mock'ают subprocess.

**Решение:**
1. **`GitServer`** класс с 4 async methods. Каждый: валидация input →
   `asyncio.create_subprocess_exec` (shell=False, явные args, timeout) → парсинг
   вывода → Pydantic Output. Без shell-инъекций (args list, не строка).
2. **Безопасность:**
   - `_validate_branch_name`: regex `^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,199}$` + запрет
     `..`, control chars, leading `-`. Соответствует git ref naming rules.
   - `_validate_repo_path`: `Path(repo_path).resolve()` существует и является dir.
   - `_validate_relative_paths` (для commit files): пути относительно repo_path,
     нет абсолютных, нет `..` traversal.
   - `_check_secrets_in_diff`: regex-скан diff на github_pat_*, AKIA*, bearer tokens,
     private key markers. При находке — `SecretDetectedError` (ABORT).
3. **4 Tool Implementations** (`CreateBranchImplementation`, etc.) — обёртки над
   `GitServer` methods для MCP server (по паттерну `bsl_ls/server.py`).
4. **`git/__init__.py`** — экспорт `GitServer`, `GIT_TOOLS`, 4 Implementation classes.
5. **Subprocess execution** — `asyncio.create_subprocess_exec(*args, cwd=repo_path,
   capture_output=True, timeout=...)`. `shell=False` (явные args list — нет
   shell-инъекций). Для `commit` message — через `-m` arg (не stdin, для простоты).
6. **`open_pr`** — `gh pr create --base ... --head ... --title ... --body ... --label ...`.
   Если `gh` не установлен → `FileNotFoundError` с понятным сообщением. Auth через
   `GH_TOKEN` env (gh CLI стандарт).
7. **`diff`** — `git diff <a>..<b> -- <paths>`, вывод сканируется на secrets перед
   возвратом.

**Тесты** (`tests/mcp_servers/test_git_server.py`):
- Unit (mock `asyncio.create_subprocess_exec`): 4 tools happy path, branch name
  validation (reject `..`, leading `-`, control chars, too long), repo_path
  validation (non-existent), relative paths validation (absolute, `..` traversal),
  secrets in diff (github_pat_*, AKIA*, private key), gh not installed →
  FileNotFoundError, subprocess timeout.
- Integration (skip-if `TEST_GIT_REPO` not set): real git repo, create_branch +
  diff roundtrip.

**Реализация:** commit (pending).

**Последствия:**
- Положительные: 4 git tools работают; безопасность (branch/path validation,
  secrets scan); async subprocess (не блокирует event loop); паттерн совпадает с
  bsl_ls (consistency).
- Отрицательные: `open_pr` требует `gh` CLI в production (задокументировано в
  error message); secrets scan — regex-based (не идеально, но базовая защита).

**Связанные:** ADR-0010, ADR-0003, BACKLOG TD-S5-03, D-2026-07-13-07 (Facade
run_cli proxy расширится на git.* в следующем спринте).

---

### D-2026-07-13-07: TD-S5-02 — Facade handlers: in-memory state + 8 tools по ADR-0013 (расхождение с BACKLOG)

**Дата:** 2026-07-13
**Тип:** architecture + implementation (TD-S5-02, Stage 3 задача 2/4)
**Контекст:** BACKLOG TD-S5-02 перечислил 8 lifecycle tools: `start_task, get_status,
get_plan, get_code, get_review, validate_now, retry_iteration, complete_task`. Но
ADR-0013 (главный контракт, принят 2026-07-11) определяет **другой** набор из 8
tools: `plan, gather, generate, validate, review, explain, run_cli, data_status`.
Контракты (`facade/contracts.py`), `tool_definitions.py` (`FACADE_TOOLS`),
`next_action.py` (5 builder'ов) уже реализованы по ADR-0013. BACKLOG-список —
более поздняя мысль автора BACKLOG, не отражённая в коде.

Дополнительно: orchestrator — это LangGraph StateGraph, запускаемый целиком через
`graph.ainvoke()`. Facade требует **пошагового** выполнения (plan → gather → ...).
В ADR-0013: «CLI и MCP-Facade — один код под капотом (handlers переиспользуются)».

**Решение:**
1. **Следовать ADR-0013** (контракт выше предпочтений). 8 tools: `plan, gather,
   generate, validate, review, explain, run_cli, data_status`. BACKLOG-список
   (`start_task` etc.) **не применяется** — он противоречит контракту и уже
   реализованным `contracts.py` / `tool_definitions.py` / `next_action.py`.
2. **FacadeHandlers** — класс с DI через конструктор: `persistence_manager`,
   `kb_server`, `bsl_ls_server`, `llm`, `path_manager`, `config_registry`.
   Соответствует принципу DI (нет boundary violations: mcp_servers.facade может
   импортировать orchestrator, parsers, data_layer).
3. **State management** — in-memory dict `plan_id → TaskState`. Каждый handler:
   - валидирует input через Pydantic Input-контракт
   - загружает/создаёт TaskState (in-memory; опц. persistence через
     `PersistenceManager` для будущего production survival-restart)
   - вызывает соответствующий node напрямую (`plan_node`, `gather_node`,
     `code_node`, `validate_node`, `review_node`, `commit_node`)
   - применяет обновление: `state.model_copy(update=node_result)`
   - сохраняет в in-memory dict
   - формирует Output через Pydantic Output-контракт + `next_action` builder
4. **handle_review** с `decision="proceed"` дополнительно вызывает `commit_node`
   (review → commit в одном tool, согласно ADR-0013: «при proceed — открывается PR»).
5. **handle_data_status** — `PathManager.validate()` + `ConfigRegistry.list()` +
   `freshness_check()`. Без state, без persistence.
6. **handle_explain** — read-only: `kb_server.search_kb()` + `codebase.semantic_search()`.
   Без state, без persistence.
7. **handle_run_cli** — proxy к доменным MCP tools через lookup-таблицу. Пока
   возвращает warning для нерелизованных tools.
8. **server.py** — `create_facade_server()` возвращает `mcp.server.Server` с 8
   tools (через `FACADE_TOOLS` definitions + handlers dispatch).
   `run_facade_server()` — stdio loop. `run_sync()` — для `[project.scripts]`.

**Persistence notes:** In-memory state dict достаточен для MCP stdio server
(один процесс, state в памяти переживает несколько tool-вызовов в рамках сессии
Cursor). Для production survival-restart (пережить рестарт контейнера) —
отдельный TD: hooks в `checkpointer.aput/aget_tuple` через `PersistenceManager`.
Фундамент (TD-S5-01) уже готов.

**Тесты** (`tests/mcp_servers/test_facade_handlers.py`):
- 8 handlers: happy path (mock nodes) + input validation (extra/missing fields)
  + next_action correctness + state propagation между вызовами + error cases.
- `test_facade_server.py`: tools registered (8), snapshot tool names, input
  schemas valid JSON Schema.

**Реализация:** commit (pending).

**Последствия:**
- Положительные: Facade реально работает (были заглушки NotImplementedError);
  ADR-0013 соблюдён; DI чистый; 8 tools экспонируются через MCP stdio.
- Отрицательные: in-memory state не переживает рестарт процесса — задокументировано
  (отдельный TD для production hooks).

**Связанные:** ADR-0013, ADR-0010, ADR-0003, ADR-0009, D-2026-07-13-04 (persistence),
TD-S5-02.

---

### D-2026-07-13-05: Стратегия миграций — Alembic scaffolding + разделение ответственности с LangGraph setup()

**Дата:** 2026-07-13
**Тип:** architecture (уточнение ADR-0018)
**Контекст:** ADR-0018 §4 предписывает «Alembic управляет SQL-схемой (таблицы LangGraph:
checkpoints, writes, migration_blobs)» + Python-миграции для pickle-state. Однако
`langgraph-checkpoint-postgres` 1.0.9 сам управляет своими таблицами через
`AsyncPostgresSaver.setup()`, который прогоняет внутренний `MIGRATIONS` список.
Дублирование этого управления в Alembic привело бы к конфликту двух schema-owner'ов
и риску рассинхронизации. Приложенческие таблицы (`bsl_modules`, `health_check`) на
данный момент создаются идемпотентным `docker/postgres/init.sql`
(`CREATE TABLE IF NOT EXISTS`) при первом старте контейнера Postgres.

**Решение:** Разделить ответственность явно:
1. **LangGraph checkpoint-таблицы** (`checkpoints`, `checkpoint_writes`, `checkpoint_blobs`,
   `checkpoint_migrations`) — управляются `AsyncPostgresSaver.setup()`, вызываемым в
   `PersistenceManager.__aenter__`. Alembic их НЕ трогает.
2. **Приложенческие таблицы** (`bsl_modules`, `health_check`) — пока остаются в
   `init.sql` (идемпотентно). Alembic scaffolding (`alembic.ini` + `migrations/alembic/`)
   разворачивается как инфраструктура-готовность: baseline-stamp миграция документирует,
   что существующие таблицы созданы вне Alembic, а ВСЕ будущие schema-изменения
   приложенческих таблиц идут через Alembic. Это реализует чеклист ADR-0018
   «Настроить Alembic (Sprint 4)» без конфликта с LangGraph.
3. **TaskState pickle-миграции** — `migrations/state/` с Python-скриптами по шаблону
   ADR-0018 §5, запускаются по `schema_version` при загрузке checkpoint (будущее).
4. **`schema_version: int = Field(default=1)`** добавлено в `TaskState` (ADR-0018 чеклист).

**Реализация:**
- `alembic.ini` (root) + `migrations/alembic/env.py` + `migrations/alembic/versions/0001_baseline.py`.
- `migrations/state/0001_initial.py` (шаблон-заглушка) + `migrations/README.md`.
- ADR-0018 чеклист обновлён: «Настроить Alembic» → ✅ (scaffolding готов).

**Последствия:**
- Положительные: один schema-owner на категорию таблиц (LangGraph ↔ своё, Alembic ↔ наше);
  нет конфликта; готовность к эволюции приложенческих таблиц; явная версионность TaskState.
- Отрицательные: две системы миграций (setup() + Alembic) — задокументировано в README;
  baseline Alembic не создаёт DDL (только stamp) — ожидаемо для brownfield.

**Связанные:** ADR-0018 (уточнено), ADR-0014 (PostgresSaver), D-2026-07-13-04.

---

### D-2026-07-13-04: PostgresSaver persistence — рабочая реализация PersistenceManager

**Дата:** 2026-07-13
**Тип:** architecture + implementation (TD-S5-01, Stage 3 первая задача)
**Контекст:** `packages/orchestrator/src/orchestrator/persistence.py` был заглушкой
из Sprint 1.5: `AsyncPostgresSaver.from_conn_string(self.dsn)` присваивался как
инстанс, но этот метод — `@classmethod @asynccontextmanager`, возвращающий
`AsyncIterator[AsyncPostgresSaver]`. Т.е. код присваивал async-generator объект,
а не saver; `setup()` никогда не вызывался (таблицы не создавались); connection
lifecycle не управлялся. Реальная persistence НЕ работала — рестарт контейнера
терял state. `generate.py` вообще не использовал `PersistenceManager`
(`build_graph` дефолтил на `MemorySaver`).

**Решение:**
1. **Переписать `PersistenceManager`** на корректный lifecycle:
   - `__aenter__`: при наличии DSN — `async with AsyncPostgresSaver.from_conn_string(dsn) as saver:`
     с удержанием context manager'а в `self._saver_cm`, затем `await saver.setup()`
     (создаёт checkpoint-таблицы, идемпотентно). При `ImportError`
     (`langgraph-checkpoint-postgres` не установлен) — graceful fallback на
     `MemorySaver` с warning. При connection-error — `PersistenceError` (ABORT).
   - `__aexit__`: корректно закрывает удерживаемый async context manager (connection).
   - `get_checkpointer()`: возвращает saver (Postgres или Memory); `PersistenceError`,
     если не был войден.
   - `from_env(dsn_env_var="DATABASE_URL")`: classmethod, читает DSN из env.
   - `async health_check()`: выполняет пробный `aget_tuple`/connection-ping — для
     Docker healthcheck и Facade (TD-S5-02). Для MemorySaver возвращает `True`.
2. **`schema_version: int = Field(default=1, ge=1)`** в `TaskState` (ADR-0018).
3. **`generate.py._run_pipeline`** — обёрнут в `async with PersistenceManager.from_env() as pm:`,
   checkpointer передаётся в `build_graph(checkpointer=pm.get_checkpointer())`.
   Production (DATABASE_URL задан) → Postgres; dev/tests (нет env) → MemorySaver.
4. **`_mask_dsn`** сохранён (пароль не утекает в логи).
5. `CheckpointerType = Any` оставлен (LangGraph generic typing + mypy).

**Тесты** (`tests/orchestrator/test_persistence.py`):
- Unit: MemorySaver fallback (dsn=None), DSN masking, get_checkpointer-before-enter →
  PersistenceError, ImportError fallback (monkeypatch), bad DSN → PersistenceError,
  from_env читает DATABASE_URL, health_check MemorySaver → True, mock-lifecycle
  (fake async cm saver: setup вызван, connection закрыт на exit).
- Integration (skip-if `TEST_POSTGRES_DSN` not set): real setup + checkpoint roundtrip
  (put → aget_tuple) + survive-restart (close manager, reopen, aget_tuple находит
  checkpoint) — доказывает «рестарт контейнера не теряет state».

**Реализация:** commit `408abe9`, persistence.py переписан, generate.py обёрнут.

**Последствия:**
- Положительные: persistence реально работает; фундамент для TD-S5-02 (Facade
  lifecycle tools, восстанавливающих state); для TD-S5-04 (Docker healthcheck).
- Отрицательные: `generate.py` теперь требует `langgraph-checkpoint-postgres` для
  production (уже в `postgres` extra, синхронизирован через `uv sync --all-extras`).

**Связанные:** ADR-0014, ADR-0018, ADR-0015, D-2026-07-13-05, TD-S5-01.

---

### D-2026-07-13-03: BSL LS Docker — мульти-stage build + HTTP API v0.2.0

**Дата:** 2026-07-13
**Тип:** architecture + infrastructure
**Контекст:** TD-S4.2-04 — последняя задача Этапа 2. В проекте уже была основа
(Dockerfile.bsl-ls, bsl_ls_http_server.py, BslLsServer, тесты), но:
- CLI-синтаксис BSL LS в `bsl_ls_http_server.py` был некорректный:
  `java -jar bsl-ls.jar analyze <file>` вместо правильного
  `analyze --src <file> --format json --output <result.json>`.
- Не было healthcheck для `1c-ai-bsl-ls` сервиса в docker-compose.
- Не было `.dockerignore` (медленный build context, риск утечки секретов).
- Dockerfile был одно-stage (большой образ), без pinned версий, без OCI labels.
- Не было integration-тестов с реальным контейнером.

**Решение:**
1. **Мульти-stage Dockerfile** (alpine downloader + python:3.12-slim runtime):
   - BSL LS v0.25.5 с sha256 проверкой (пока placeholder, нужно обновить при реальном релизе).
   - Pinned Python-зависимости (fastapi==0.115.0, uvicorn==0.30.6, httpx==0.27.2, pydantic==2.9.2).
   - OCI labels (org.opencontainers.image.*).
   - HEALTHCHECK на /health endpoint.
2. **Исправлен CLI-синтаксис BSL LS v0.25.x** в `bsl_ls_http_server.py`:
   - `analyze --src <file> --format json --output <result.json>` — детерминированный парсинг.
   - `format --src <file>` — модифицирует файл in-place.
   - Корректная обработка stderr (Exception/OutOfMemoryError = критическая ошибка).
3. **Healthcheck в docker-compose** для `1c-ai-bsl-ls`: curl /health,
   start_period=15s, retries=3. Зависимость `1c-ai-app` изменена на `service_healthy`.
4. **`.dockerignore`** — исключает секреты, данные, __pycache__, тесты, IDE файлы.
5. **latency_ms метрика** пробрасывается из BSL LS HTTP response в MCP contracts
   (LintOutput, FormatOutput) — для мониторинга производительности.
6. **10 новых unit-тестов** + 3 integration-теста (skip если BSL_LS_HTTP_URL не задан).

**Альтернативы:**
- A) Long-running JVM с stdin/stdout протоколом (быстрее, но сложнее реализация).
- B) Subprocess для каждого запроса (выбрано, +1-2с на Java startup, но stateless).
- C) Native Python BSL LS (не существует, bsl-ls только на Java).

**Повлияло на:**
- BACKLOG.md — TD-S4.2-04 закрыт, Этап 2 полностью завершён
- CURRENT_FOCUS.md — Этап 2: 7/7
- `.dockerignore` (НОВЫЙ)
- `docker/Dockerfile.bsl-ls` (полностью переписан)
- `docker/bsl_ls_http_server.py` (полностью переписан, v0.2.0)
- `docker-compose.yml` (healthcheck + service_healthy)
- `packages/mcp_servers/src/mcp_servers/bsl_ls/contracts.py` (latency_ms в outputs)
- `packages/mcp_servers/src/mcp_servers/bsl_ls/server.py` (проброс latency_ms)
- `tests/mcp_servers/test_bsl_ls_server.py` (+10 unit + 3 integration тестов)
- `docs/process/worklog.md` (запись о TD-S4.2-04)

**Этап 2 ЗАВЕРШЁН.** Следующий шаг — Stage 3 (Production-readiness):
TD-S5-01 PostgresSaver persistence → TD-S5-02 Facade handlers →
TD-S5-03 git MCP → TD-S5-04 Docker production.

---

### D-2026-07-13-02: Стандарты 1С (СТО + БСП) как 3-й тип KB-сущностей

**Дата:** 2026-07-13
**Тип:** architecture
**Контекст:** TD-S4.2-03 требует проверки кода на соответствие стандартам 1С
(СТО — Стандарты Технологического Обмена, БСП — Библиотека Стандартных Подсистем).
Было два пути:
- A) Расширить существующую сущность antipattern полем `source` (СТО/БСП).
- B) Создать отдельную сущность `standard` (3-й тип KB).

**Решение:** Вариант B — отдельная сущность `standard`.

**Обоснование:**
- Семантика: antipattern = «плохая практика», standard = «требование стандарта 1С».
- У стандарта есть `source` (type+code+url) — у антипаттерна нет.
- Стандарты имеют более длинные description и url-ссылки на its.1c.ru.
- В поиске (search_kb) — отдельная категория 'standard'.
- В валидаторе — отдельный source='kb_standards' (4-й параллельный валидатор).

**Что сделано:**
- knowledge-base/standards/ — 8 YAML (4 СТО + 4 БСП), все с regex-detect.
- knowledge-base/schemas/standard.schema.json — JSON Schema.
- KBCollection.standards + get_standard + list_standards + detect_standards_violations.
- KbServer.get_standard + check_standards — 2 новых MCP tools (KB: 5→7).
- validate_node: 4-й параллельный валидатор (_run_standards_validator).
- ValidationFinding.source: Literal расширен до {"bsl_ls", "kb_antipatterns",
  "kb_standards", "custom_rules"}.
- 39 новых тестов в test_kb_standards.py.

**Повлияло на:**
- BACKLOG.md — TD-S4.2-03 закрыт
- CURRENT_FOCUS.md — Этап 2: 6/7 задач завершено
- packages/mcp_servers/src/mcp_servers/kb/ (loader.py, server.py, contracts.py)
- packages/orchestrator/src/orchestrator/nodes/validate.py + contracts.py
- knowledge-base/index.json + schemas/standard.schema.json + standards/*.yaml
- tests/mcp_servers/test_kb_standards.py + test_mcp_contracts.py

---

### D-2026-07-13-01: ADR-0020 — гибридный поиск + multi-layer индексация

**Дата:** 2026-07-13
**Тип:** architecture
**Контекст:** Этап 1 завершён, нужен семантический поиск по коду для Coder.
Пользователь дал 3 вводных: transitive closure, export-методы, множественные
конфигурации (БСП/БПО/версии).

**Решение:** ADR-0020 — гибридный BM25+pgvector+RRF, BGE-M3 1024 dim локально,
chunking по export-методам (27,581 чанков), 4-layer индексация
(platform/library/config/KB) с metadata-тегами.

**Transitive closure:** Planner — да (blast radius), Reviewer — count, Coder — 1-hop.

**Повлияло на:**
- adr/0020-embeddings-strategy.md — НОВЫЙ
- adr/README.md — 20 ADR
- BACKLOG.md — TD-S4.2-01 закрыт, добавлены TD-S4.2-05/06/07
- CURRENT_FOCUS.md — фокус на Этап 2

---

### D-2026-07-12-09: Файлы состояния переносятся в git репозиторий (docs/process/)

**Дата:** 2026-07-12
**Тип:** process + architecture
**Контекст:** Окружение сессии сбросилось — пропали DECISIONS.md, BACKLOG.md,
PROJECT_BOOTSTRAP.md, PROCESS_FRAMEWORK.md. Они были в /home/z/my-project/
(окружение сессии, не git). Пользователь указал: файлы состояния должны
переживать сброс — иначе механизмы саморегуляции бесполезны.

**Альтернативы:**
- A) Оставить в /home/z/my-project/ — но при сбросе пропадают
- B) Перенести в git репозиторий (docs/process/) — переживают сброс
- C) Внешний backup (Google Drive и т.д.) — сложнее синхронизация

**Решение:** B

**Причина:**
- Git — уже есть, не нужно новой инфраструктуры
- Коммиты автоматически версионнируют файлы состояния
- При clone репозитория — файлы подтягиваются
- Версионность: можно смотреть историю решений через git log

**Повлияло на:**
- Файлы DECISIONS.md, BACKLOG.md, PROJECT_BOOTSTRAP.md, PROCESS_FRAMEWORK.md
  переносятся в /home/z/my-project/1c-ai-assistant/docs/process/
- .gitignore — НЕ исключает docs/process/
- CURRENT_FOCUS.md, INTERNAL_ROADMAP.md, worklog.md — тоже переносятся
- В .gitignore: оставить только data/, derived/, runtime/, vendor/

**Supersedates:** D-2026-07-12-05 (где я решил что файлы НЕ в репо — ошибка)

---

### D-2026-07-12-08: Этап 1 (контекст для Coder) — начинаю сразу. ADR-0020 отложен

**Дата:** 2026-07-12
**Тип:** focus-switch + sprint-scope
**Контекст:** MVP работает, но качество кода низкое — Coder генерирует вслепую.
Пользователь подтвердил принцип «глубина сначала» как постоянное правило.
Старый план Sprint 4 делал всё сразу — неправильный порядок для качества.

**Альтернативы:**
- A) ADR-0020 сначала (документ, 1-2 часа), потом Этап 1
- B) Этап 1 сразу (контекст для Coder), ADR-0020 отложить до Этапа 2
- C) Sprint 4 целиком как в плане

**Решение:** B

**Причина:**
- Этап 1 не зависит от embeddings (metadata MCP, call graph, api-reference —
  работают на парсерах, не на векторном поиске)
- ADR-0020 нужен только для codebase MCP (Этап 2). Делать сейчас — документ ради документа
- Принцип «глубина сначала»: сначала качество кода, потом полнота фич
- Старый репо 1c-ai-dev-env (MIT, мой) — можно переносить алгоритмы

**3 этапа вместо Sprint 4:**
- **Этап 1 (Sprint 4.1): Контекст для Coder** — metadata MCP + call graph + api-reference
- **Этап 2 (Sprint 4.2): Поиск и качество** — ADR-0020 + codebase MCP + standards + BSL LS Docker
- **Этап 3 (Sprint 5): Production-readiness** — Postgres + Facade + git MCP + Docker production

**Принцип «Глубина сначала» (постоянное правило):**
Качество и глубина проработки — первостепенны. Скорость не важна.
Никогда не спрашивать пользователя про темп. Делать правильно, не быстро.

---

### D-2026-07-12-07: MVP Smoke Test — я (Z.ai GLM) как LLM для pipeline

**Дата:** 2026-07-12
**Тип:** focus-switch
**Контекст:** Пользователь сказал: «тестировать будем в твоей среде, LLM тоже
будешь ты». MVP first principle.

**Решение:** B — MVP Smoke Test, я (Z.ai GLM) как LLM через z-ai CLI subprocess.

**Результат (был потерян при сбросе, восстановлен):**
Pipeline end-to-end работает. 3 LLM-вызова (Plan/Code/Review) через ZaiLLM
adapter, structured_output работает, BSL код генерируется.

---

### D-2026-07-12-06: TD-002 — DI для orchestrator (boundary violations)

**Дата:** 2026-07-12
**Тип:** focus-switch
**Решение:** B — TD-002 сначала (DI refactor), потом ADR-0020.
**Результат (был потерян, восстановлен):** 3 boundary violations устранены
через functools.partial в build_graph(). 0 violations.

---

### D-2026-07-12-05: Механизмы саморегуляции (4 механизма + PROJECT_BOOTSTRAP)

**Дата:** 2026-07-12
**Тип:** process
**Решение:** 4 механизма (DECISIONS + BACKLOG + Contract Check + ФОКУС-строка)
+ PROJECT_BOOTSTRAP для переноса в новый чат.
**Superseded by:** D-2026-07-12-09 (файлы переносятся в git репо)

---

### D-2026-07-12-04: HBK Container32 возвращён из Sprint 4 в Sprint 3.2

**Дата:** 2026-07-12
**Тип:** focus-switch
**Решение:** B — прервать ADR-0020, реализовать HBK в Sprint 3.2.
**Результат (был потерян, восстановлен):** 10,150 методов загружено через
zlib + HTML парсинг (алгоритм из старого репо 1c-ai-dev-env).

---

### D-2026-07-12-03: Sprint 3.2 — валидация перед ADR-0020

**Дата:** 2026-07-12
**Тип:** sprint-scope
**Решение:** B — добавить Sprint 3.2 перед ADR-0020.
**Результат (был потерян, восстановлен):** Найден критичный баг (iter_metadata_files),
метрики собраны (27,581 методов, 3.5M строк).

---

### D-2026-07-12-02: HBK Container32 отложен на Sprint 4 (SUPERSeded)

**Дата:** 2026-07-12
**Тип:** tech-debt
**Решение:** Отложить, использовать хардкод 17 методов.
**Superseded by:** D-2026-07-12-04

---

### D-2026-07-12-01: Сначала аудит Sprint 1-3, потом Sprint 4

**Дата:** 2026-07-12
**Тип:** focus-switch
**Решение:** B — сначала фиксы. Sprint 4 (Postgres) закрепил бы баги.
**Результат (был потерян, восстановлен):** 4 бага закрыты в Sprint 3.1 + 3.1.1.

---

## Исторические решения (до внедрения DECISIONS.md)

### D-2026-07-11-01: EDT и Vanessa исключены из архитектуры
**Решение:** Убрать EDT и Vanessa, оставить 5 MCP серверов вместо 6+.
**Причина:** Не оправдано для solo-dev. Зафиксировано в CONCEPTUAL.md §9.

### D-2026-07-11-02: pgvector вместо Qdrant (по умолчанию)
**Решение:** pgvector как default, Qdrant как опция через VectorStoreProtocol.
**Причина:** Контейнер postgres уже нужен, меньше инфры. Зафиксировано в ADR-0017.

### D-2026-07-11-03: 3-контейнерный деплой
**Решение:** app + bsl-ls + postgres (с pgvector), вместо 1 контейнера.
**Причина:** Java изоляция критична. Зафиксировано в ADR-0015.
