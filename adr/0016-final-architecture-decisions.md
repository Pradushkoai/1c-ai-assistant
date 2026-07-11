# ADR-0016: Финальная сверка концептуальной архитектуры (10 пунктов)

**Статус:** Accepted
**Дата:** 2026-07-11
**Supersedes:** — (фиксация решений, не отмена предыдущих ADR)

## Контекст

После проектирования 9 шагов архитектуры и 14 ADR проведена финальная сверка с пользователем по 10 концептуальным вопросам. Пользователь подтвердил все 10 пунктов + принял решение по инфраструктуре деплоя (ADR-0015). Этот ADR фиксирует финальные решения для предотвращения regress'а.

## Решения

### 1. 6 слоёв архитектуры — подтверждено

```
1. Entry Points (CLI, MCP-Facade, позже REST/IDE)
2. Orchestrator (LangGraph, TOOL_GROUPS, роутеры)
3. MCP Layer (5 доменных серверов + Facade)
4. Parsers (чистая lib: xml/bsl/hbk/models/indexers)
5. Data Layer (FS + PathManager + ConfigRegistry)
6. Knowledge Layer (YAML + Markdown, в git)
```

Зависимости — только вниз. Data Layer зависит от Parsers.models (единственная осознанная «восходящая» зависимость, правильная).

### 2. 6 агентных ролей — подтверждено

| Роль | Узел | Тип |
|---|---|---|
| Planner | Plan subgraph | mini-supervisor |
| Gatherer | Gather subgraph | mini-supervisor |
| Coder | Code node | simple LLM |
| Validator | Validate subgraph | parallel fan-out |
| Reviewer | Review subgraph | mini-supervisor |
| Committer | Commit node | simple tool |

Разделение Validator (детерминированный gate) и Reviewer (LLM-рецензент) — критично, не объединять.

### 3. Coder без инструментов — подтверждено как главный принцип фокуса

`TOOL_GROUPS[CODER] = {}` — пустое множество. Coder получает контекст от Gatherer и только генерирует. Не давать fallback-инструменты «на всякий случай» — это ломает фокус.

### 4. 5 MCP-серверов + Facade — подтверждено

Доменные серверы: `metadata`, `codebase`, `kb`, `bsl_ls`, `git`. Плюс `facade` сверху. EDT и Vanessa исключены (решение пользователя 2026-07-11).

**Уточнение ADR-0003:** 5 доменных серверов остаются как **логические контракты** в коде, но запускаются в 3 контейнерах (см. ADR-0015):
- Контейнер `1c-ai-app`: facade + metadata + codebase + kb + git (in-process)
- Контейнер `1c-ai-bsl-ls`: bsl_ls (HTTP API)
- Контейнер `postgres`: pgvector + persistence

### 5. 7 lifecycle tools Facade'а — подтверждено

`plan`, `gather`, `generate`, `validate`, `review`, `explain`, `run_cli` + `data_status` (утилита). Каждый возвращает `_next_action` — одно конкретное следующее действие.

`run_cli` проверяет `caller_role` через TOOL_GROUPS — нет дыры в фокус-контроле.

### 6. 4 спринта MVP — подтверждено

| Спринт | Артефакт |
|---|---|
| 1 | `1c-ai config build` работает (parsers + PathManager + CLI) |
| 2 | `1c-ai generate` одной функцией (bsl_ls MCP + 4 узла + Coder) |
| 3 | Planner + Reviewer (KB-as-code + kb MCP + тесты) |
| 4 | Production-ready (metadata/codebase/git MCP + Facade + persistence) |

Спринты 5-6 из изначального плана (optimization, dogfooding) — post-MVP.

### 7. Pydantic v2 frozen как клей проекта — подтверждено

`frozen=True`, `extra="forbid"`, `strict=True` по умолчанию. Исключения — явно задокументированы (например, `ObjectMetadata` с `extra="allow"` для forward-compat с новыми типами 1С).

### 8. PostgresSaver для персистентности — подтверждено (с самого начала)

**Уточнение ADR-0014:** Не SQLiteSaver для MVP. Postgres контейнер уже есть (для pgvector), поэтому используется `AsyncPostgresSaver` с первого дня. Это даёт multi-process готовость без миграции.

### 9. KB-as-code (YAML + Markdown) — подтверждено

- `patterns/*.yaml` — эталоны с `code_template`, `variables`, `example_good`
- `antipatterns/*.yaml` — с `detect:` блоком (regex/AST/bsl_ls_rule), `recommendation_for_llm`
- `prompts/*.j2` — Jinja2 системные промпты
- `schemas/*.json` — JSON Schemas для валидации
- `standards/` — СТО 1С, БСП (Markdown, для справки)

YAML — для машины (детект + генерация промпта), Markdown — для человека (расширенные описания). Комплиментарно, не взаимоисключающи.

### 10. Иерархия из 14 ошибок — подтверждено

14 классов `AgentError`, каждый с `action: retry | escalate | abort`. CI-тест проверяет, что retryable errors не включают ABORT-категории.

Альтернатива сжатия до 11 классов (через слияние IndexStaleError→PreflightError и т.д.) — рассмотрена, отвергнута: каждый класс соответствует реальному сценарию, гранулярность оправдана.

## Дополнительно: деплой (ADR-0015)

**3 контейнера:**
1. `1c-ai-app` (Python, ~180 МБ) — orchestrator + 4 MCP in-process + Facade
2. `1c-ai-bsl-ls` (Python + JVM, ~350 МБ) — BSL LS HTTP API, always-running
3. `postgres` (pgvector/pgvector:pg16, ~400 МБ) — persistence + vector search

**Полный гибридный search:** BM25 (tsvector+GIN) + vector (pgvector) + RRF reranker.

## Финальный состав ADR-каталога (15 записей)

| # | Тема | Статус |
|---|---|---|
| 0001 | Python 3.12 + LangGraph 1.x | Accepted |
| 0002 | Монорепа с uv workspace, 5 пакетов | Accepted |
| 0003 | MCP: Facade + 5 доменных серверов | Accepted (уточнён ADR-0015) |
| 0004 | Hierarchical orchestration | Accepted |
| 0005 | TOOL_GROUPS registry с CI-проверкой | Accepted |
| 0006 | Data Layer: 4 слоя + PathManager | Accepted |
| 0007 | Pydantic v2 frozen models | Accepted |
| 0008 | PathManager — единый источник путей | Accepted |
| 0009 | Pipeline contracts — центральный контракт | Accepted |
| 0010 | MCP tool contracts — двойной контракт | Accepted |
| 0011 | TOOL_GROUPS — декларативное распределение | Accepted |
| 0012 | KB-as-code — YAML + Markdown | Accepted |
| 0013 | Agent-Facade — 7 lifecycle tools | Accepted |
| 0014 | Error taxonomy + PostgresSaver | Accepted (PostgresSaver с начала, см. ADR-0015) |
| 0015 | 3-container deployment (app + JVM + postgres/pgvector) | Accepted |
| 0016 | Этот документ — фиксация финальных решений | Accepted |

## Последствия

### Положительные
- Все концептуальные решения зафиксированы и подтверждены пользователем
- Можно переходить к коду (спринт 1) без риска «переделать архитектуру на полпути»
- ADR-каталог — источник истины, изменения только через новые ADR

### Отрицательные
- 15 ADR — много для чтения новым контрибьютором (но каждый короткий, 1-2 страницы)
- 3 контейнера — больше, чем 1 (но оправдано функциональностью)

## Связанные документы

- CONCEPTUAL.md — концептуальный обзор (без кода)
- 00-overview.md — технический обзор (с архитектурой)
- 01..09 — детальные шаги проектирования
- adr/ — 15 ADR + README

**Готов к переходу к коду Спринта 1.**
