# ADR Catalog — 1C AI Assistant

> Architecture Decision Records. Каждое решение — отдельный файл.
> Статус по умолчанию: Accepted. Изменения — через новый ADR с `supersedes`.

## Индекс — 20 ADR

| # | Тема | Статус | Дата |
|---|---|---|---|
| 0001 | Python 3.12 + LangGraph 1.x (изолирован) | Accepted | 2026-07-11 |
| 0002 | Монорепа с uv workspace, 5 пакетов | Accepted | 2026-07-11 |
| 0003 | MCP: Facade + 5 доменных серверов | Accepted | 2026-07-11 |
| 0004 | Hierarchical orchestration (pipeline + subgraphs) | Accepted | 2026-07-11 |
| 0005 | TOOL_GROUPS registry с CI-проверкой | Accepted | 2026-07-11 |
| 0006 | Data Layer: 4 слоя + PathManager | Accepted | 2026-07-11 |
| 0007 | Pydantic v2 frozen models | Accepted | 2026-07-11 |
| 0008 | PathManager — единый источник путей | Accepted | 2026-07-11 |
| 0009 | Pipeline contracts — центральный контракт | Accepted | 2026-07-11 |
| 0010 | MCP tool contracts — двойной контракт | Accepted | 2026-07-11 |
| 0011 | TOOL_GROUPS — декларативное распределение | Accepted | 2026-07-11 |
| 0012 | KB-as-code — YAML + Markdown | Accepted | 2026-07-11 |
| 0013 | Agent-Facade — 7 lifecycle tools | Accepted | 2026-07-11 |
| 0014 | Error taxonomy + PostgresSaver | Accepted | 2026-07-11 |
| 0015 | 3-container deployment (app + JVM + postgres/pgvector) | Accepted | 2026-07-11 |
| 0016 | Финальная сверка концептуальной архитектуры (10 пунктов) | Accepted | 2026-07-11 |
| 0017 | VectorStoreProtocol — pgvector по умолчанию, Qdrant как опция | Accepted | 2026-07-11 |
| 0018 | TaskState migration strategy | Accepted | 2026-07-11 |
| 0019 | Observability strategy (LangSmith + structlog) | Accepted | 2026-07-11 |
| 0020 | Embeddings strategy — гибридный поиск + multi-layer индексация | Accepted | 2026-07-13 |

## Шаблон ADR

```
# ADR-XXXX: <Title>

**Статус:** Accepted | Superseded | Deprecated
**Дата:** YYYY-MM-DD
**Supersedes:** ADR-YYYY (если есть)
**Superseded by:** ADR-ZZZZ (если есть)

## Контекст
<Почему это решение обсуждается. Какие проблемы.>

## Рассмотренные варианты
1. <Вариант A> — pros/cons
2. <Вариант B> — pros/cons

## Решение
<Что выбрали и почему.>

## Последствия
### Положительные
- ...

### Отрицательные
- ...

## Связанные документы
- <Ссылки на другие ADR, шаги проектирования, код>
```

## Как добавлять новые ADR

1. Скопировать `0000-template.md` (создать при необходимости)
2. Назвать `00NN-short-kebab-title.md` (next number)
3. Заполнить по шаблону
4. PR с меткой `adr`
5. После merge — обновить индекс в этом файле
