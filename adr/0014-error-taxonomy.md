# ADR-0014: Error taxonomy + PostgresSaver

**Статус:** Accepted
**Дата:** 2026-07-11

## Контекст

Pipeline длинный (Plan → Gather → Code → Validate → Review → Commit, плюс retry-циклы). На любом этапе может что-то пойти не так: LLM вернул невалидный JSON, BSL LS завис, Qdrant недоступен, 3 итерации failed, превышен token budget.

Без таксономии — retry-логика превращается в спагетти `if/elif`. Без persistence — длинные задачи теряются при рестарте процесса.

## Решение

### Иерархия ошибок

```
AgentError (базовый)
├── PreflightError (ABORT)
├── IndexStaleError (ABORT)
├── SchemaViolationError (RETRY)
├── ToolError
│   ├── ToolTimeoutError (RETRY)
│   ├── ToolConnectionError (RETRY)
│   ├── ToolExecutionError (ESCALATE)
│   └── RoleForbiddenError (ABORT)
├── LLMError
│   ├── LLMUnavailableError (RETRY)
│   ├── LLMRateLimitError (RETRY, retry_after)
│   └── LLMBudgetExceededError (ESCALATE)
├── ValidationFailedError (RETRY)
├── ReviewRejectedError (RETRY)
├── MaxIterationsExceededError (ESCALATE)
├── EscalationRequestedError (ESCALATE)
└── PersistenceError (ABORT)
```

Каждая ошибка имеет `action: Literal["retry", "escalate", "abort"]`.

### Retry-логика — единое место

`with_retry(func, max_attempts=3, base_delay=1.0, max_delay=30.0)`:
- `LLMRateLimitError` → delay = retry_after
- `ToolConnectionError` → linear backoff
- Остальные retryable → exponential backoff
- При истощении retry → `MaxIterationsExceededError` → escalate

### Persistence — `AsyncPostgresSaver`

- `PersistenceManager(dsn)` — async context manager
- `get_checkpointer()` → передаётся в `build_graph(checkpointer=...)`
- Схема таблиц — управляется LangGraph (`setup()` создаёт автоматически)
- Migration через alembic при breaking changes в `TaskState`

### Error handler decorator

Каждый узел графа оборачивается в `error_handler(node_fn)`:
1. `with_retry` для retryable ошибок
2. AgentError с `action=ESCALATE` → `fsm_state="escalated"` + `escalate_reason`
3. AgentError с `action=ABORT` → `fsm_state="failed"`
4. PersistenceError → критическая, `fsm_state="failed"`
5. Unexpected Exception → `fsm_state="failed"` + log

### Escalate PR — структурированный

`escalate_node` создаёт PR с меткой `needs-human-review`, body содержит:
- причину эскалации
- историю итераций (сколько строк сгенерировано, failed_checks, edit distance)
- рекомендуемые действия (зависят от причины)

## Последствия

### Положительные
- Retry-логика тестируется (property-based через hypothesis)
- Длинные задачи переживают рестарт процесса (checkpoint в Postgres)
- Эскалация — не crash, а вменяемый PR для человека
- Mapping `error → escalate reason` — единая точка

### Отрицательные
- Postgres — дополнительная инфраструктура (митигация: MemorySaver для dev/test)
- Migration при breaking changes в TaskState (митигация: alembic + ADR)
- Иерархия ошибок — 14 классов (но каждый с осмысленным action)

## Связанные документы
- 09-error-taxonomy.md (полный код errors.py, retry.py, persistence.py)
- ADR-0009 (TaskState, который сериализуется)
- ADR-0004 (error_handler оборачивает узлы графа)
