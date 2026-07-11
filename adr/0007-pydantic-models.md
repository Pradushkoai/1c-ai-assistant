# ADR-0007: Pydantic v2 frozen models как клей проекта

**Статус:** Accepted
**Дата:** 2026-07-11

## Контекст

Проекту нужен общий язык для данных 1С (BslModule, CatalogMetadata, ...) и для state pipeline (TaskState, Subtask, Iteration). Этот язык используется:
- парсерами (возвращают модели)
- MCP-серверами (отдают модели через MCP)
- orchestrator'ом (TaskState)
- тестами (round-trip проверка)

Альтернативы: dataclasses, TypedDict, голые dict.

## Рассмотренные варианты

1. **dataclasses** — pros: дёшево; cons: нет валидации, нет JSON Schema export
2. **TypedDict** — pros: типизация; cons: runtime не валидирует, нет методов
3. **Pydantic v1** — pros: зрелый; cons: медленный, v2 лучше во всём
4. **Pydantic v2** — pros: валидация, JSON Schema, `model_dump()`, frozen, интеграция с LangChain `with_structured_output()`

## Решение

**Pydantic v2, frozen по умолчанию, extra=forbid, strict.**

Базовый конфиг:
```python
class ModelConfig(BaseModel):
    model_config = ConfigDict(
        frozen=True,        # иммутабельность
        extra="forbid",     # лишние поля → ошибка
        strict=True,        # строгая типизация
    )
```

Все модели в `parsers/models/` наследуются от `ModelConfig`. JSON Schema доступна через `Model.model_json_schema()` — используется в MCP `inputSchema` и LangChain structured output.

## Последствия

### Положительные
- End-to-end типизация: MCP-клиент знает схему ответа, orchestrator получает Pydantic
- Иммутабельность → корректные LangGraph checkpoint'ы
- JSON Schema export → snapshot-тесты контрактов MCP
- `model_validate_json()` / `model_dump_json()` — round-trip без потерь

### Отрицательные
- Чуть медленнее dataclasses (но не критично для нашего объёма)
- strict=True может ломаться на边缘 cases (митигация: явные overrides для forward-compat)

## Связанные документы
- 02-pydantic-models.md
- Шаг 4 (TaskState наследует тот же принцип)
