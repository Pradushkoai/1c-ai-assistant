# ADR-0009: Pipeline contracts — центральный контракт проекта

**Статус:** Accepted
**Дата:** 2026-07-11

## Контекст

Pipeline состоит из 10 узлов (preflight, plan, gather, code, validate, review, retry, commit, escalate, next_subtask) и 4 роутеров. Узлы обмениваются state. Без явных контрактов:
- типы `Result` расплывчаты (dict[str, Any] everywhere)
- нельзя тестировать узлы в изоляции
- Facade (Шаг 8) не понимает, что оборачивает
- MCP tool contracts (Шаг 5) не знают, в какой форме собирать результаты

## Решение

**Каждый узел имеет строго один input-тип и строго один output-тип:**
- `PlanResult` → вход в `Gather`
- `GatherResult` → вход в `Code`
- `CodeResult` → вход в `Validate`
- `ValidateResult` → вход в `route_after_validate`
- `ReviewResult` → вход в `route_after_review`
- `CommitResult` → финал

**TaskState — frozen Pydantic v2**, каждый узел возвращает новый state через `model_copy(update={...})`.

**Роутеры — чистые Python-функции** `state -> Literal[...]`, не LLM. LLM живёт ВНУТРИ узлов, не ВЫШЕ них.

**FSMState enum** фиксирует состояния: INIT, PLANNING, GATHERING, CODING, VALIDATING, REVIEWING, COMMITTING, ESCALATED, DONE, FAILED.

## Фокус-контроль — зафиксирован в коде узлов

Каждый узел явно достаёт из `TaskState` только нужные поля:
- Coder видит: `GatherResult` + `SubtaskConstraints` + prev `Iteration.failed_checks`
- Coder НЕ видит: `description`, другие подзадачи, метаданные других объектов
- Reviewer видит: `CodeResult` + `ValidateResult`
- Reviewer НЕ видит: `description`

Это **дисциплина в коде**, не автоматическая фильтрация.

## Последствия

### Положительные
- Узлы тестируются в изоляции (mock state, проверить Result)
- Роутеры — property-test через hypothesis
- Facade (Шаг 8) — тривиальная обёртка над типизированными узлами
- Snapshot-тесты контрактов MCP строятся поверх этих моделей

### Отрицательные
- Больше типов (PlanResult, GatherResult, ... — 6 классов)
- Frozen state — при изменении нужно `model_copy`, не прямая мутация (привыкание)

## Связанные документы
- 04-pipeline-contracts.md (полный код контрактов)
- ADR-0004 (Hierarchical orchestration)
- ADR-0007 (Pydantic v2 frozen)
