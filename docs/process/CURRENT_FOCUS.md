# CURRENT FOCUS — точка входа для каждой сессии

> **Этот файл живёт в git репозитории (docs/process/), чтобы переживать сбросы окружения.**
> Последнее обновление: 2026-07-13 (**Stage 3 ЗАВЕРШЁН** — 4/4 задачи, TD-S5-01/02/03/04 закрыты)

---

## 📌 START HERE — для НОВОЙ сессии / нового агента

> **Если ты только что подключился к проекту — прочитай это первым делом!**

### Текущее состояние (snapshot на 2026-07-13)
- **Этап 1:** ✅ ЗАВЕРШЁН (5/5 задач)
- **Этап 2:** ✅ **ЗАВЕРШЁН** (7/7 задач) — TD-S4.2-01..07 все закрыты
- **Stage 3 (Production-readiness):** ✅ **ЗАВЕРШЁН** (4/4) — TD-S5-01/02/03/04 все закрыты

### Что прочитать в порядке приоритета (первые 5 минут сессии)
1. **Этот файл** (CURRENT_FOCUS.md) — целиком, до конца
2. **`docs/process/PROJECT_BOOTSTRAP.md`** — точка входа, snapshot, архитектура
3. **`docs/process/BACKLOG.md`** — раздел «Этап 3 (Production-readiness)»: TD-S5-01..04
4. **`docs/process/worklog.md`** — последняя запись (TD-S4.2-04, дата 2026-07-13)
5. **`docs/architecture/CONCEPTUAL.md`** §2.1 (asyncio.TaskGroup) — если работаешь с validate_node

### Следующий этап (post-Stage 3)
Stage 3 (Production-readiness) завершён. Возможные следующие направления:
- **Post-MVP** (TD-005..011): Streaming responses, prompt caching, multi-LLM routing.
- **REST API** (HTTP server на :8000, Facade через HTTP вместо stdio — для k8s probes).
- **Production survival-restart** для Facade (hooks в checkpointer.aput/aget_tuple
  через PersistenceManager — in-memory state dict сейчас не переживает рестарт процесса).
- **ZaiLLM mypy cleanup** (TD-011: 14 ошибок, LangChain strict typing).
- **Integration tests** с реальными контейнерами (TEST_POSTGRES_DSN, TEST_GIT_REPO,
  BSL_LS_HTTP_URL — skip-if-not-set сейчас).

### Закрытые задачи Stage 3
- ✅ **TD-S5-01: PostgresSaver persistence** (2026-07-13) — рабочая реализация
  PersistenceManager (AsyncPostgresSaver + setup() + connection lifecycle),
  schema_version в TaskState, миграции (Alembic scaffolding + state-миграции),
  generate.py обёрнут в PersistenceManager. 21 unit + 3 integration тестов.
  См. D-2026-07-13-04, D-2026-07-13-05.
- ✅ **TD-S5-02: Facade handlers** (2026-07-13) — 8 lifecycle tools по ADR-0013
  (plan/gather/generate/validate/review/explain/run_cli/data_status). FacadeHandlers
  с DI (state_factory + node_* callables + servers). MCP server (stdio). 35 новых
  тестов + 10 обновленных. См. D-2026-07-13-07.
- ✅ **TD-S5-03: git MCP** (2026-07-13) — GitServer с 4 tools (create_branch, commit,
  open_pr, diff) через async subprocess. Безопасность: branch name validation,
  repo_path validation, relative paths validation, secrets scan в diff (7 паттернов).
  59 тестов. См. D-2026-07-13-08.
- ✅ **TD-S5-04: Docker production** (2026-07-13) — multi-stage Dockerfile.app
  (builder + runtime, non-root user, OCI labels), `1c-ai health` CLI команда
  (persistence + BSL LS ping, JSON output), healthcheck в docker-compose,
  .env.example, docker-compose.override.yml (dev hot reload). 16 тестов.
  См. D-2026-07-13-09.

### Ключевые принципы (без знания которых нельзя работать)
- **«Глубина сначала»** (D-2026-07-12-08): качество важнее скорости, никаких временных решений.
- **«Всегда готов к завершению»**: после КАЖДОЙ задачи — коммит + push + обновление ВСЕХ
  state-файлов (CURRENT_FOCUS, BACKLOG, DECISIONS, worklog, PROJECT_BOOTSTRAP). Сессия
  может прерваться в любой момент.
- **DI через functools.partial** — 0 boundary violations (см. `scripts/check_package_boundaries.py`).
- **asyncio.TaskGroup** для parallel fan-out в validate_node (CONCEPTUAL.md §2.1).

### Команды (не забыть!)
```bash
# Тесты (ВСЕГДА из директории проекта!)
unset VIRTUAL_ENV && UV_CACHE_DIR=/tmp/uv-cache uv run --directory /home/z/my-project/1c-ai-assistant pytest tests/ -v

# Lint (включая docker/)
unset VIRTUAL_ENV && UV_CACHE_DIR=/tmp/uv-cache uv run --directory /home/z/my-project/1c-ai-assistant ruff check packages/ tests/ docker/

# Boundaries
unset VIRTUAL_ENV && UV_CACHE_DIR=/tmp/uv-cache uv run --directory /home/z/my-project/1c-ai-assistant python scripts/check_package_boundaries.py

# Git push (НЕ git add -A, только конкретные файлы; использовать -C для git)
TOKEN=$(cat /home/z/my-project/.github-token | tr -d '\n' | tr -d '[:space:]')
git -C /home/z/my-project/1c-ai-assistant config user.name "Pradushkoai"
git -C /home/z/my-project/1c-ai-assistant config user.email "Pradushkoai@users.noreply.github.com"
git -C /home/z/my-project/1c-ai-assistant config core.fileMode false  # игнорировать mode changes
git -C /home/z/my-project/1c-ai-assistant add <file1> <file2> ...
git -C /home/z/my-project/1c-ai-assistant commit -m "feat(...): ..."
git -C /home/z/my-project/1c-ai-assistant remote set-url origin "https://x-access-token:${TOKEN}@github.com/Pradushkoai/1c-ai-assistant.git"
git -C /home/z/my-project/1c-ai-assistant push origin main
git -C /home/z/my-project/1c-ai-assistant remote set-url origin "https://github.com/Pradushkoai/1c-ai-assistant.git"
```

### Известные грабли (наступать НЕ надо)
- **Всегда используй `git -C /home/z/my-project/1c-ai-assistant ...`** — `cd` в Bash не сохраняется
  между вызовами.
- **Никогда не используй `git add -A`** — только конкретные файлы (правило безопасности).
- **`git config core.fileMode false`** — обязательно, иначе будешь видеть кучу mode changes
  (100644→100755), которые не несут реальных изменений.
- **Данные УТ11 + HBK** — gitignored, после сброса окружения нужно перезагружать через
  `1c-ai config build` и `1c-ai hbk parse`.
- **uv.lock** — автоматически обновляется при `uv sync`, иногда нужно коммитить отдельно.

---

## 🎯 ФОКУС СЕССИИ (для продолжающей сессии)

> **Задача:** Stage 3 (Production-readiness) — **ЗАВЕРШЁН** ✅ (4/4)
> **Статус:** все 4 задачи закрыты (persistence + Facade + git MCP + Docker production)
> **Блокеры:** нет
> **Что сделано:** ✅ PersistenceManager (TD-S5-01), ✅ FacadeHandlers с 8 tools + MCP
> server (TD-S5-02), ✅ GitServer с 4 tools + безопасность (TD-S5-03),
> ✅ Multi-stage Docker + `1c-ai health` + .env.example + dev override (TD-S5-04)
> **Следующий шаг:** post-Stage 3 — см. «Следующий этап» выше (post-MVP / REST API /
> production survival-restart / ZaiLLM mypy / integration tests с контейнерами)
>
> **Принцип «Глубина сначала»** (D-2026-07-12-08): качество важнее скорости.
>
> ⚠️ **ПРАВИЛО «Всегда готов к завершению»**: после каждой задачи — коммит + push +
> обновление всех файлов состояния (CURRENT_FOCUS, BACKLOG, DECISIONS, worklog,
> PROJECT_BOOTSTRAP). Сессия может прерваться в любой момент.

---

## 📊 Текущий статус

- **Спринты завершены:** 0, 1, 1.5, 2, 3, 3.1, 3.2, 3.2.1, 3.3
- **Этап 1 прогресс:** 5/5 задач ЗАВЕРШЁН ✅ (TD-S4.1-01..04 + контракт)
- **Этап 2 прогресс:** **7/7 задач ЗАВЕРШЕНО** ✅ (TD-S4.2-01/02/03/04/05/06/07 ✅)
- **Stage 3 прогресс:** ✅ 4/4 задач ЗАВЕРШЕНО (TD-S5-01/02/03/04 ✅)
- **Тесты:** 921 проходят + 7 skipped (3 BSL LS + 3 Postgres + 1 git integration)
- **Persistence:** ✅ PostgresSaver (AsyncPostgresSaver + setup() + connection lifecycle);
  MemorySaver fallback (dev/tests); migrations/ (Alembic scaffolding + state-миграции)
- **Facade:** ✅ 8 lifecycle tools (ADR-0013): plan/gather/generate/validate/review/explain/run_cli/data_status;
  MCP stdio server; DI через конструктор; in-memory state dict
- **git MCP:** ✅ 4 tools (create_branch, commit, open_pr, diff) через async subprocess;
  безопасность (branch/path validation, secrets scan в diff)
- **Docker:** ✅ multi-stage Dockerfile.app (builder + runtime, non-root user, OCI labels);
  `1c-ai health` CLI (persistence + BSL LS ping, JSON output); healthcheck в compose;
  .env.example; docker-compose.override.yml (dev hot reload)
- **MVP:** ✅ `1c-ai generate` работает с реальной LLM (ZaiLLM через z-ai CLI)
- **HBK:** 10,150 методов платформы 8.3.25 (Container32 парсер)
- **KB:** 5 patterns + 10 antipatterns + 8 standards (4 СТО + 4 БСП) — 3 типа сущностей
- **MCP tools:** 21 domain tools (5→7 KB: get_standard + check_standards)
- **Валидаторы:** 4 параллельных в validate_node (BSL LS + antipatterns + method availability + standards)
- **BSL LS Docker:** мульти-stage Dockerfile v0.25.5, HTTP API, healthcheck, .dockerignore
- **Boundary violations:** 0 (DI через functools.partial)
- **Данные:** УТ11 (5,575 объектов, 7,141 BSL модулей) + HBK 8.3.25 (80 файлов)
- **Последний коммит:** TD-S5-04 Docker production — Stage 3 ЗАВЕРШЁН (4/4)

---

## 📂 Файлы проекта (все в git репозитории)

| Файл | Назначение |
|---|---|
| `docs/process/PROJECT_BOOTSTRAP.md` | Точка входа для нового агента |
| `docs/process/CURRENT_FOCUS.md` | Этот файл — ФОКУС + статус |
| `docs/process/INTERNAL_ROADMAP.md` | Стратегический план |
| `docs/process/DECISIONS.md` | Журнал решений (D-YYYY-MM-DD-NN) |
| `docs/process/BACKLOG.md` | Реестр техдолга (TD-NNN) |
| `docs/process/worklog.md` | Журнал выполненных задач |
| `docs/process/TESTING_POLICY.md` | Политика тестирования |
| `docs/architecture/CONCEPTUAL.md` | Главный контракт |
| `adr/` | 19 ADR |

---

## 🔒 Contract Check (читать ПЕРЕД git commit)

### Триггеры по файлам

| Меняешь | Сверить с |
|---|---|
| `packages/orchestrator/nodes/*.py` | CONCEPTUAL.md §2.1 + ADR-0004 + ADR-0009 |
| `packages/parsers/src/parsers/hbk/*` | 12-real-data-validation.md + ADR-0006 |
| `packages/mcp_servers/*/contracts.py` | ADR-0010 + 05-mcp-tool-contracts.md |
| `packages/orchestrator/state.py` | ADR-0009 + ADR-0018 |
| `packages/orchestrator/tool_groups.py` | ADR-0005 + ADR-0011 + CONCEPTUAL.md §2.2 |
| `packages/parsers/models/*` | ADR-0007 + 02-pydantic-models.md |
| `knowledge-base/prompts/*.j2` | 10-prompts-spec.md |
| `knowledge-base/{patterns,antipatterns}/*.yaml` | ADR-0012 + 07-kb-as-code.md |

### Общие проверки

- [ ] Новый техдолг → BACKLOG.md?
- [ ] Изменён план → INTERNAL_ROADMAP.md?
- [ ] Операционное решение → DECISIONS.md?
- [ ] ФОКУС-строка актуальна?
- [ ] worklog.md обновлён?

---

## ✅ Session Checkpoint (читать ПЕРЕД завершением задачи)

**⚠️ ПРАВИЛО «Всегда готов к завершению»**: сессия может прерваться в любой момент.
После КАЖДОЙ задачи — обязательно:
1. Коммит + push (все изменения в git)
2. Обновить CURRENT_FOCUS.md (ФОКУС-строка + статус)
3. Обновить BACKLOG.md (если есть новый/закрытый техдолг)
4. Обновить DECISIONS.md (если есть новое решение)
5. Обновить worklog.md (запись о выполненной работе)

- [ ] ФОКУС-строка обновлена?
- [ ] worklog.md — запись добавлена?
- [ ] DECISIONS.md — решения зафиксированы?
- [ ] BACKLOG.md — техдолг обновлён?
- [ ] Тесты проходят? ruff чистый?
- [ ] Коммит запушен от Pradushkoai?
- [ ] Security audit: токен не утёк?
- [ ] docs/process/ файлы закоммичены (переживают сброс)?

---

## 🛠 Команды

```bash
# Тесты
unset VIRTUAL_ENV && UV_CACHE_DIR=/tmp/uv-cache uv run --directory /home/z/my-project/1c-ai-assistant pytest tests/ -v

# Lint
unset VIRTUAL_ENV && UV_CACHE_DIR=/tmp/uv-cache uv run --directory /home/z/my-project/1c-ai-assistant ruff check packages/ tests/
unset VIRTUAL_ENV && UV_CACHE_DIR=/tmp/uv-cache uv run --directory /home/z/my-project/1c-ai-assistant mypy packages/

# Boundaries
unset VIRTUAL_ENV && UV_CACHE_DIR=/tmp/uv-cache uv run --directory /home/z/my-project/1c-ai-assistant python scripts/check_package_boundaries.py

# Git push (НЕ git add -A, только конкретные файлы)
TOKEN=$(cat /home/z/my-project/.github-token | tr -d '\n' | tr -d '[:space:]')
git -C /home/z/my-project/1c-ai-assistant config user.name "Pradushkoai"
git -C /home/z/my-project/1c-ai-assistant config user.email "Pradushkoai@users.noreply.github.com"
git -C /home/z/my-project/1c-ai-assistant add <file1> <file2> ...
git -C /home/z/my-project/1c-ai-assistant commit -m "feat(...): ..."
git -C /home/z/my-project/1c-ai-assistant remote set-url origin "https://x-access-token:${TOKEN}@github.com/Pradushkoai/1c-ai-assistant.git"
git -C /home/z/my-project/1c-ai-assistant push origin main
git -C /home/z/my-project/1c-ai-assistant remote set-url origin "https://github.com/Pradushkoai/1c-ai-assistant.git"
```
