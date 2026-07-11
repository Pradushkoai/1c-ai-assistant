# ADR-0013: Agent-Facade — 7 lifecycle tools + _next_action

**Статус:** Accepted
**Дата:** 2026-07-11

## Контекст

Внешний клиент (Cursor/Claude/Codex) подключается через MCP. Если показать ему все 19 tools из 5 доменных серверов:
- tool interference — модель вызывает не тот tool
- длинный контекст — описание 19 tools отъедает токены
- нет вменяемого workflow — LLM не знает, что за чем вызывать

## Решение

**7 lifecycle tools + `_next_action` паттерн:**

| Tool | Что делает | `_next_action` |
|---|---|---|
| `plan(task, config)` | Декомпозиция | `gather` |
| `gather(plan_id, subtask_id)` | Сбор контекста | `generate` |
| `generate(plan_id, subtask_id)` | LLM генерация | `validate` |
| `validate(artifact_id)` | BSL LS + KB | `review` или `generate` (retry) |
| `review(artifact_id)` | LLM-рецензент | `commit` / `generate` / `data_status` |
| `explain(code_or_query)` | Reverse engineering | — |
| `run_cli(tool_name, args)` | Proxy к скрытым tools | — |
| + `data_status()` | Preflight | — |

**`_next_action` — одно конкретное действие**, не workflow. LLM внешнего клиента идёт по рельсам: `plan → gather → generate → validate → review → commit`.

**Coder'а нет среди lifecycle tools** — `generate` запускает весь мини-pipeline `gather → code → validate` внутри. Внешний клиент не видит Coder как отдельный tool.

## Режимы работы

- **A (полный агент):** CLI `1c-ai generate` или REST API → весь pipeline за один вызов
- **B (умный Cursor):** Cursor → Facade → 7 lifecycle tools (видит _next_action)
- **C (power-user):** Cursor → напрямую к `bsl_ls` MCP для быстрого lint'а

## Последствия

### Положительные
- Внешний клиент видит 8 tools (не 19) — нет tool interference
- `_next_action` направляет LLM по workflow
- `run_cli` proxy сохраняет доступ к скрытым tools для продвинутых
- CLI и MCP-Facade — один код под капотом (handlers переиспользуются)

### Отрицательные
- Facade — дополнительный слой (но тонкий)
- `plan_id`/`thread_id` mapping нужно хранить (митигация: Postgres в production)

## Связанные документы
- 08-agent-facade.md (полная реализация handlers)
- ADR-0003 (MCP-архитектура: Facade + 5 серверов)
- ADR-0009 (Facade оборачивает pipeline contracts)
