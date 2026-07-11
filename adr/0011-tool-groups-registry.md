# ADR-0011: TOOL_GROUPS — декларативное распределение инструментов

**Статус:** Accepted
**Дата:** 2026-07-11
**Supersedes**: string-фильтрацию из `1c-ai-dev-env`

## Контекст

В `1c-ai-dev-env` код фильтрации tools был размазан: `if tool_name in ALLOWED_FOR_ROLE: ...` в нескольких местах. Это приводило к copy-paste ошибкам, tool утекал к нескольким ролям, Coder мог «исследовать» кодовую базу вместо генерации.

## Решение

**Декларативный `TOOL_GROUPS` registry — единственное место, где зафиксировано, какой агент какие инструменты может вызывать.**

```python
TOOL_GROUPS: dict[AgentRole, dict[MCPServer, frozenset[ToolName]]] = {
    AgentRole.CODER: {},  # ПУСТО — критично
    AgentRole.GATHERER: {"metadata": frozenset({...}), "codebase": ..., "kb": ...},
    ...
}
```

**`MULTI_ROLE_OK`** — исключения для tools, которые законно принадлежат нескольким ролям:
- `kb.check_method_availability` → GATHERER + VALIDATOR
- `kb.check_antipatterns` → VALIDATOR + REVIEWER

**`ToolProvider`** — LangChain adapter, отдаёт LLM только разрешённые tools + проверяет `caller_role` на каждом вызове.

## 3 CI-теста обязательно

1. `test_no_orphan_tools` — каждый tool из contracts ∈ хотя бы одной роли
2. `test_no_unexpected_multi_role` — tool в нескольких ролях только если в `MULTI_ROLE_OK`
3. `test_tool_provider_validates` — `ToolProvider(CODER).get_tools() == []`

## Фокус-контроль

**Coder без инструментов — критично.** Если Coder может вызвать `semantic_search`, он начнёт «исследовать» вместо генерации. Coder получает контекст от Gatherer и **только генерирует**.

## Последствия

### Положительные
- Добавление tool'а = явное решение в `TOOL_GROUPS`
- Snapshot-тесты контрактов + TOOL_GROUPS тесты = полный coverage
- Фокус-контроль на двух уровнях: prompt + MCP

### Отрицательные
- `MULTI_ROLE_OK` — потенциальная дыра (митигация: каждый случай с обоснованием в комментарии)
- При добавлении tool'а в contracts.py нужно не забыть добавить в TOOL_GROUPS — CI ловит

## Связанные документы
- 06-tool-groups.md (полная таблица)
- ADR-0005 (верхнеуровневое решение)
- ADR-0009 (роли = узлы pipeline)
- ADR-0010 (`required_role` в ToolContract)
