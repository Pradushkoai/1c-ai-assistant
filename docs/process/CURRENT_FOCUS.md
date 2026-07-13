# CURRENT FOCUS — точка входа для каждой сессии

> **Этот файл живёт в git репозитории (docs/process/), чтобы переживать сбросы окружения.**
> Последнее обновление: 2026-07-13 (Этап 2 — **7/7 задач завершены**, TD-S4.2-04 закрыт)

---

## 🎯 ФОКУС СЕССИИ

> **Задача:** Этап 2 (Поиск и качество) — **ЗАВЕРШЁН** ✅
> **Статус:** TD-S4.2-04 ЗАВЕРШЁН (BSL LS Docker: Dockerfile, HTTP server, integration-тесты)
> **Блокеры:** нет
> **Что сделано:** ✅ Этап 1, ✅ ADR-0020, ✅ api-reference в pipeline, ✅ transitive closure, ✅ library add,
> ✅ codebase MCP (indexer + VectorStoreProtocol + PgVectorStore + server 4 tools),
> ✅ TD-S4.2-03 standards (8 YAML: 4 СТО + 4 БСП, 4-й валидатор),
> ✅ **TD-S4.2-04 BSL LS Docker** (мульти-stage Dockerfile, исправлен CLI-синтаксис,
> healthcheck в docker-compose, .dockerignore, latency_ms метрика, 10 новых тестов + 3 integration)
> **Следующий шаг:** Stage 3 (Production-readiness): PostgresSaver persistence → Facade handlers → git MCP → Docker production
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
- **Тесты:** 780 проходят + 3 skipped (integration, без Docker) (+10 от BSL LS)
- **MVP:** ✅ `1c-ai generate` работает с реальной LLM (ZaiLLM через z-ai CLI)
- **HBK:** 10,150 методов платформы 8.3.25 (Container32 парсер)
- **KB:** 5 patterns + 10 antipatterns + 8 standards (4 СТО + 4 БСП) — 3 типа сущностей
- **MCP tools:** 21 domain tools (5→7 KB: get_standard + check_standards)
- **Валидаторы:** 4 параллельных в validate_node (BSL LS + antipatterns + method availability + standards)
- **BSL LS Docker:** мульти-stage Dockerfile v0.25.5, HTTP API, healthcheck, .dockerignore
- **Boundary violations:** 0 (DI через functools.partial)
- **Данные:** УТ11 (5,575 объектов, 7,141 BSL модулей) + HBK 8.3.25 (80 файлов)
- **Последний коммит:** TD-S4.2-04 BSL LS Docker — Этап 2 ЗАВЕРШЁН

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
