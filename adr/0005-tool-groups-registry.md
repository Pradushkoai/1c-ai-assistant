# ADR-0005: TOOL_GROUPS registry с CI-проверкой

**Статус:** Accepted
**Дата:** 2026-07-11

## Контекст

В `1c-ai-dev-env` использовалась string-фильтрация: код вида `if tool_name in allowed_for_role: ...`. Это приводило к:
- copy-paste ошибок (забыли обновить фильтр в новом узле)
- tool утекал к нескольким ролям случайно
- нет CI-проверки консистентности
- Coder мог «исследовать» кодовую базу вместо генерации

## Решение

**Декларативный `TOOL_GROUPS` registry:**

```python
TOOL_GROUPS: dict[AgentRole, dict[MCPServer, frozenset[ToolName]]] = {
    AgentRole.CODER: {},  # ПУСТО — критично
    AgentRole.GATHERER: {
        "metadata": frozenset({"metadata.get_metadata", ...}),
        ...
    },
    ...
}
```

**3 CI-теста обязательно:**
1. `test_no_orphan_tools` — каждый tool из contracts принадлежит хотя бы одной роли
2. `test_no_unexpected_multi_role` — tool в нескольких ролях только если явно в `MULTI_ROLE_OK`
3. `test_tool_provider_validates` — `ToolProvider(CODER).get_tools() == []`

**Два уровня изоляции:**
1. Prompt-level — LLM видит только свои tools в system prompt
2. MCP-level — каждый вызов проверяет `caller_role` (defense in depth)

## Последствия

### Положительные
- Добавление tool'а = явное решение в `TOOL_GROUPS` + ADR (если multi-role)
- Coder гарантированно без инструментов — фокус на генерации
- Snapshot-тесты контрактов + TOOL_GROUPS тесты = полный coverage

### Отрицательные
- Чуть больше boilerplate при добавлении tool'а (но это хорошо)
- `MULTI_ROLE_OK` — потенциальная дыра (митигация: каждый случай с обоснованием в комментарии)

## Связанные документы
- 06-tool-groups.md
- ADR-0011 (детализация TOOL_GROUPS)
