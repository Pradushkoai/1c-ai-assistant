# Architecture Documentation

Этот каталог содержит архитектурные спецификации проекта.

## Основные документы

| Файл | Что |
|---|---|
| [CONCEPTUAL.md](CONCEPTUAL.md) | Концептуальная архитектура без кода — сущности, взаимосвязи, принципы |
| [INDEX.md](INDEX.md) | Технический индекс документов (с кодом и контрактами) |
| [00-overview.md](00-overview.md) | Обзор 6 слоёв, pipeline, фокус-контроль |
| [01-monorepo-structure.md](01-monorepo-structure.md) | Структура пакетов монорепы |
| [02-pydantic-models.md](02-pydantic-models.md) | Общие Pydantic v2 модели |
| [03-paths-protocol.md](03-paths-protocol.md) | PathManager + Data Layer |
| [04-pipeline-contracts.md](04-pipeline-contracts.md) | **Центральный контракт**: state + node contracts |
| [05-mcp-tool-contracts.md](05-mcp-tool-contracts.md) | Контракты 19 MCP tools |
| [06-tool-groups.md](06-tool-groups.md) | TOOL_GROUPS registry |
| [07-kb-as-code.md](07-kb-as-code.md) | Формат KB (YAML + Markdown) |
| [08-agent-facade.md](08-agent-facade.md) | 7 lifecycle tools + `_next_action` |
| [09-error-taxonomy.md](09-error-taxonomy.md) | Иерархия ошибок + persistence |

## Связанные каталоги

- [`/adr`](../../adr) — 17 Architecture Decision Records
- [`/knowledge-base`](../../knowledge-base) — KB-as-code (YAML + Markdown)
