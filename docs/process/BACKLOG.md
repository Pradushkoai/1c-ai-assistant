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

### TD-S4.1-01: Form/Subsystem/Role парсеры (metadata MCP)
- **Источник:** INTERNAL_ROADMAP.md §4.2, 12-real-data-validation.md §5.1
- **Этап:** 1 (Sprint 4.1)
- **Приоритет:** CRITICAL (блокирует metadata MCP)
- **Описание:** В УТ 11 — 4,124 Form/Module.bsl, 42 Subsystems, 641 Role.
  Нужны парсеры `Form.xml` → `FormMetadata`, `Subsystem.xml`, `Rights.xml`.
  Можно переносить алгоритмы из старого репо 1c-ai-dev-env (MIT, мой).
- **Оценка:** 1-2 дня

### TD-S4.1-02: Call graph builder
- **Источник:** старый репо 1c-ai-dev-env (call_graph.py, call_graph_parser.py)
- **Этап:** 1 (Sprint 4.1)
- **Приоритет:** HIGH
- **Описание:** Граф вызовов методов в BSL-модулях. Coder будет видеть
  существующие методы, не дублировать. Перенос алгоритма под наши модели
  (Pydantic v2 frozen, CallEdge модель).
- **Оценка:** 1-2 дня

### TD-S4.1-03: api-reference indexer
- **Источник:** INTERNAL_ROADMAP.md §4.2
- **Этап:** 1 (Sprint 4.1)
- **Приоритет:** HIGH
- **Описание:** Из BSL модулей извлекаем export-методы → api-reference.json.
  Coder получает список доступных функций конфигурации.
- **Оценка:** 1 день

### TD-S4.1-04: dependency graph builder
- **Источник:** старый репо 1c-ai-dev-env (dependency_graph.py)
- **Этап:** 1 (Sprint 4.1)
- **Приоритет:** MEDIUM
- **Описание:** Граф зависимостей между объектами метаданных (Catalog → Document
  через реквизит). Planner использует для декомпозиции.
- **Оценка:** 1 день

---

## 🟡 Этап 2 (Поиск и качество)

### TD-S4.2-01: ADR-0020 Embeddings strategy
- **Этап:** 2 (Sprint 4.2)
- **Приоритет:** CRITICAL (блокирует codebase MCP)
- **Описание:** Решить: модель (BGE-M3 1024 / OpenAI 1536/3072), локально vs API,
  chunking (по методам, 27,581 chunks), переиндексация.
- **Метрики для решения:** в docs/architecture/12-real-data-validation.md
- **Блокеры:** нет (после Этапа 1)

### TD-S4.2-02: codebase MCP (BM25 + pgvector)
- **Этап:** 2 (Sprint 4.2)
- **Приоритет:** HIGH
- **Описание:** pgvector + embeddings (после ADR-0020!). BM25+vector+RRF.
  Перенос из старого репо: search_bm25.py, search_vector.py, search_hybrid.py.

### TD-S4.2-03: standards (1С СТО, БСП)
- **Этап:** 2 (Sprint 4.2)
- **Приоритет:** MEDIUM
- **Описание:** Перенос YAML из старого репо knowledge_base/standards/.
  Validator будет проверять code на соответствие стандартам 1С.

### TD-S4.2-04: BSL LS через Docker
- **Этап:** 2 (Sprint 4.2)
- **Приоритет:** MEDIUM
- **Описание:** Реальная валидация через BSL LS Java-сервер. Сейчас
  validate работает только на KB antipatterns (regex).

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
| В работе (Этап 1) | 4 (TD-S4.1-01..04) |
| Этап 2 | 4 (TD-S4.2-01..04) |
| Этап 3 | 4 (TD-S5-01..04) |
| Когда-нибудь | 4 (TD-005..011) |
| Закрыто | 3 (TD-000, TD-002, TD-004) |
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
