# ADR-0015: 3-container deployment (app + JVM + postgres/pgvector)

**Статус:** Accepted
**Дата:** 2026-07-11
**Supersedes:** частично ADR-0003 (уточняет инфраструктуру запуска)

## Контекст

После сверки с пользователем (2026-07-11) зафиксированы требования к деплою:
- Полный гибридный поиск (BM25 + vector) с самого начала — BM25-only недостаточно для 1С-кода
- Минимум контейнеров, но **не за счёт функциональности**
- BSL LS должен быть всегда запущен (no startup latency на каждый call)
- Java не должна жить в Python-контейнере (изоляция крашей)

Рассмотренные варианты:
1. **1 контейнер** (Python + Java + SQLite, без Qdrant) — отвергнут пользователем: нет полного поиска
2. **4 контейнера** (app + bsl-ls + postgres + Qdrant) — рассмотрен, но Qdrant избыточен для нашего масштаба
3. **3 контейнера** (app + bsl-ls + postgres с pgvector) — **выбран**

## Решение

**3 контейнера:**

### Контейнер 1: `1c-ai-app` (Python)
- Facade MCP (stdio, для Cursor/Claude)
- 4 доменных MCP servers in-process: metadata, codebase, kb, git
- `bsl_ls` MCP server — HTTP client к `1c-ai-bsl-ls:8080`
- orchestrator (LangGraph)
- PostgresSaver — подключение к `postgres:5432`
- Образ: `python:3.12-slim` + git, ~180 МБ

### Контейнер 2: `1c-ai-bsl-ls` (Python + JVM)
- Python HTTP server (FastAPI/Starlette) на :8080
- Endpoints: `POST /lint`, `POST /format`
- Java 17 + bsl-language-server.jar — long-running subprocess, переиспользуется через stdin/stdout
- Образ: `python:3.12-slim` + `openjdk-17-jre-headless`, ~350 МБ

### Контейнер 3: `postgres` (с pgvector)
- PostgreSQL 16
- Extensions: `pgvector` (embeddings), `pg_trgm` (триграммы для fallback)
- tsvector + GIN index для BM25
- Две задачи в одной БД:
  - LangGraph checkpoint'ы (TaskState persistence)
  - BSL modules embeddings + full-text (для codebase search)
- Образ: `pgvector/pgvector:pg16`, ~400 МБ

### Почему pgvector, а не Qdrant

- pgvector — extension к Postgres, не отдельный процесс
- Для <100k векторов (типовая конфигурация 1С = 10-50k BSL-модулей) pgvector работает так же быстро
- Один движок = один backup, одна репликация, один мониторинг
- Если когда-нибудь понадобится 1M+ векторов — добавим Qdrant, контракты MCP не изменятся

### Почему BSL LS в отдельном контейнере, а не subprocess

- Java краш не роняет orchestrator
- BSL LS всегда запущен — нет 2-3s startup latency на каждый call
- HTTP проще для межконтейнерного общения, чем MCP-over-stdio через docker exec
- Python-образ остаётся тонким (~180 МБ вместо ~500 МБ)

## Что НЕ меняется в архитектуре

- 5 MCP-серверов как логические контракты в коде (`packages/mcp_servers/{metadata,codebase,kb,bsl_ls,git}/`)
- TOOL_GROUPS — без изменений
- Pipeline contracts — без изменений
- Facade lifecycle tools — без изменений
- KB-as-code — без изменений
- Error taxonomy — без изменений

**Меняется только implementation detail в 2 файлах:**
- `mcp_servers/bsl_ls/server.py` — `__call__` через httpx вместо subprocess
- `mcp_servers/codebase/server.py` — поиск через postgres+pgvector вместо Qdrant client

## Последствия

### Положительные
- Полный гибридный search с самого начала
- Изоляция Java от Python — краши BSL LS не влияют на orchestrator
- Multi-process готовность (Postgres вместо SQLite)
- Один backup (pg_dump) решает все задачи
- BSL LS always-running — нет latency на startup

### Отрицательные
- 3 контейнера вместо 1 (но это оправданная цена за функциональность)
- Postgres — single point of failure (митигация: регулярный pg_dump, в production — replica)
- HTTP между app и bsl-ls — <1ms latency на одной docker network (терпимо)

## Путь эволюции

| Триггер | Действие |
|---|---|
| 1M+ векторов | Добавить Qdrant контейнер, переключить codebase-server |
| Несколько оркестраторов параллельно | Postgres уже multi-process, просто запускаем несколько app контейнеров |
| BSL LS узкое место | Добавить replica bsl-ls контейнера, load balancer |
| LangSmith trace в production | Добавить env var `LANGSMITH_API_KEY` |

## Связанные документы

- CONCEPTUAL.md (раздел 5: внешние зависимости)
- ADR-0003 (MCP-архитектура — уточнено этим ADR)
- ADR-0014 (Persistence — теперь Postgres с самого начала, не SQLite)
- **ADR-0017 (VectorStoreProtocol — pgvector по умолчанию, Qdrant как опция)**
- docker-compose.yml (будет создан в спринте 1)
- docker/Dockerfile.app, docker/Dockerfile.bsl-ls, docker/postgres/init.sql

## Уточнение от ADR-0017

Vector store для codebase-server — **не зафиксирован жёстко на pgvector**. Через `VectorStoreProtocol` (ADR-0017) реализованы 2 backend'а:
- `PgVectorStore` (по умолчанию, 3 контейнера)
- `QdrantVectorStore` (опционально, 4 контейнера, env var `VECTOR_STORE=qdrant`)

Решение о дефолте — по результатам бенчмарк-теста в спринте 4. Если Qdrant даёт recall@10 > pgvector + 3% — переключаем дефолт.
