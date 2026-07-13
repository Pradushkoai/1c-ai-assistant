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
- **Закрыто в:** commit (pending)
- **Решение:** knowledge-base/standards/ — 8 YAML-стандартов (4 СТО + 4 БСП).
  JSON Schema standard.schema.json. KBCollection.standards (3-й тип сущностей).
  2 новых MCP tools: kb.get_standard + kb.check_standards.
  4-й параллельный валидатор в validate_node (_run_standards_validator).
  ValidationFinding.source: добавлен 'kb_standards'. 39 новых тестов.
  MCP tools total: 21 (5→7 KB).

### TD-S4.2-04: BSL LS через Docker
- **Этап:** 2 (Sprint 4.2)
- **Приоритет:** MEDIUM
- **Описание:** Реальная валидация через BSL LS Java-сервер.
  Сейчас bsl_ls.lint возвращает пустой результат (валидатор работает, но
  без реальных правил). Нужно: docker-compose с BSL LS, HTTP-обёртка.

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

### TD-S5-01: PostgresSaver persistence
- **Этап:** 3 (Sprint 5)
- **Описание:** Миграции (см. ADR-0018). Рестарт контейнера не теряет state.

### TD-S5-02: Facade handlers (8 lifecycle tools)
- **Этап:** 3 (Sprint 5)
- **Описание:** Обвязка над orchestrator для Cursor.

### TD-S5-03: git MCP (4 tools)
- **Этап:** 3 (Sprint 5)
- **Описание:** subprocess git CLI. create_branch, commit, open_pr, diff.

### TD-S5-04: Docker production
- **Этап:** 3 (Sprint 5)
- **Описание:** Multi-stage Dockerfile, healthchecks, .env.example.

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

### TD-011: ZaiLLM mypy cleanup (LangChain strict typing)
- **Приоритет:** LOW (не блокирует работу)
- **Описание:** 9 mypy ошибок в zai_llm.py (LangChain strict typing).
  Решение: type: ignore или RunnableLambda вместо BaseChatModel inheritance.

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
| Этап 2 — открыто | 1 (TD-S4.2-04 BSL LS через Docker) |
| Этап 2 — закрыто | 6 (TD-S4.2-01/02/03/05/06/07) |
| Этап 3 | 4 (TD-S5-01..04) |
| Когда-нибудь | 4 (TD-005..011) |
| Закрыто | 12 (TD-000, TD-002, TD-004, TD-S4.1-01..04, TD-S4.2-01/02/03/05/06/07) |
| **Всего** | **21** |

---

## Правила ведения

1. **Новый техдолг** → новая запись в соответствующем разделе
2. **Закрытие** → пометить `[x]`, перенести в «Закрыто» с датой и commit SHA
3. **Ссылки** — обязательны: откуда задача (источник), куда влияет
4. **Приоритет** — CRITICAL / HIGH / MEDIUM / LOW
5. **Оценка** — в часах/днях, грубо
6. **Зависимости** — явно, если есть
7. **Принцип «Глубина сначала»** — качество важнее скорости (D-2026-07-12-08)
