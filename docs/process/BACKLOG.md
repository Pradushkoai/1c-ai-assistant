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
- **Закрыто в:** commit (pending)
- **Решение:** ADR-0020 — гибридный BM25+pgvector+RRF, BGE-M3 1024 dim,
  chunking по методам, 4-layer индексация (platform/library/config/KB).

### TD-S4.2-02: codebase MCP (BM25 + pgvector)
- **Этап:** 2 (Sprint 4.2)
- **Приоритет:** HIGH
- **Описание:** pgvector + embeddings (по ADR-0020!). BM25+vector+RRF.
  VectorStoreProtocol (ADR-0017). Multi-layer metadata.

### TD-S4.2-03: standards (1С СТО, БСП)
- **Этап:** 2 (Sprint 4.2)
- **Приоритет:** MEDIUM
- **Описание:** Перенос YAML из старого репо knowledge_base/standards/.
  Validator будет проверять code на соответствие стандартам 1С.

### TD-S4.2-04: BSL LS через Docker
- **Этап:** 2 (Sprint 4.2)
- **Приоритет:** MEDIUM
- **Описание:** Реальная валидация через BSL LS Java-сервер.

### TD-S4.2-05: `1c-ai library add` (БСП/БПО)
- **Этап:** 2 (Sprint 4.2)
- **Приоритет:** HIGH
- **Описание:** Команда для индексации библиотек (БСП, БПО) как отдельного
  слоя (source_layer=library). Шарится между конфигами. Embeddings с тегом.

### TD-S4.2-06: Transitive closure для Planner/Reviewer
- **Этап:** 2 (Sprint 4.2)
- **Приоритет:** MEDIUM
- **Описание:** get_transitive_dependents для dependency graph (blast radius
  для Planner). Transitive call count для Reviewer (impact). Coder — 1-hop только.

### TD-S4.2-07: api-reference в pipeline (Gatherer) — ЗАКРЫТО ✅
- **Дата закрытия:** 2026-07-13
- **Закрыто в:** commit (pending)
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
| В работе (Этап 1) | 1 (TD-S4.1-04) |
| Этап 2 | 4 (TD-S4.2-01..04) |
| Этап 3 | 4 (TD-S5-01..04) |
| Когда-нибудь | 4 (TD-005..011) |
| Закрыто | 6 (TD-000, TD-002, TD-004, TD-S4.1-01, TD-S4.1-02, TD-S4.1-03) |
| **Всего** | **19** |

---

## Правила ведения

1. **Новый техдолг** → новая запись в соответствующем разделе
2. **Закрытие** → пометить `[x]`, перенести в «Закрыто» с датой и commit SHA
3. **Ссылки** — обязательны: откуда задача (источник), куда влияет
4. **Приоритет** — CRITICAL / HIGH / MEDIUM / LOW
5. **Оценка** — в часах/днях, грубо
6. **Зависимости** — явно, если есть
7. **Принцип «Глубина сначала»** — качество важнее скорости (D-2026-07-12-08)
