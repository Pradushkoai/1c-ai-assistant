# ADR-0003: MCP-архитектура — Facade + 5 доменных серверов

**Статус:** Accepted
**Дата:** 2026-07-11
**Supersedes:** Подход из `1c-ai-dev-env` (1 сервер с гибридным фильтром tools)

## Контекст

Agent взаимодействует с внешним миром через MCP tools. Нужна архитектура, которая:
- даёт внешним клиентам (Cursor/Claude) вменяемый workflow
- изолирует разные runtime (Python vs Java 17 для BSL LS)
- не плодит инфраструктурный ад (8 контейнеров для solo-dev)
- позволяет power-user'ам дёргать отдельные MCP напрямую

## Рассмотренные варианты

1. **1 MCP-сервер, гибридный фильтр** (как в `1c-ai-dev-env`) — pros: минимальная инфра; cons: смешивает runtime, BSL LS Java в одном процессе с Python
2. **6 MCP-серверов по плану v1** — pros: чистая изоляция; cons: 8 контейнеров для solo-dev, over-engineering
3. **Facade + 5 доменных серверов** — pros: внешний клиент видит 7 lifecycle tools, доменные серверы изолированы по runtime; cons: чуть больше инфраструктуры, чем вариант 1

## Решение

**Facade + 5 доменных серверов:**
- `facade` (Python, stdio) — 7 lifecycle tools + `run_cli` proxy + `data_status`, видит внешний клиент
- `metadata` (Python) — XML-метаданные 1С
- `codebase` (Python + Qdrant) — semantic search по BSL-кодам
- `kb` (Python) — patterns/antipatterns/platform methods
- `bsl_ls` (Java 17 subprocess) — BSL Language Server, отдельный Docker
- `git` (Python + git CLI) — git operations

**EDT и Vanessa исключены** (решение пользователя 2026-07-11) — они требуют 1С runtime/лицензию, не оправдано для solo-dev.

## Последствия

### Положительные
- Внешний клиент видит 8 tools (не 19) — нет tool interference
- BSL LS изолирован в JVM — Python-процесс не падает при Java crash
- Power-user может подключиться напрямую к `bsl_ls` для быстрого lint'а

### Отрицательные
- 2 Docker-контейнера (Python app + BSL LS JVM) вместо 1
- Facade — дополнительный слой (но тонкий, без бизнес-логики)

## Связанные документы
- 05-mcp-tool-contracts.md (контракты 19 tools)
- 08-agent-facade.md (7 lifecycle tools)
- ADR-0013 (Agent-Facade подробно)
