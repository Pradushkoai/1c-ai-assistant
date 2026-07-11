# ADR-0004: Hierarchical orchestration (pipeline + mini-supervisor subgraphs)

**Статус:** Accepted
**Дата:** 2026-07-11

## Контекст

Нужно выбрать паттерн оркестрации LLM-агентов:
- **Pipeline** — детерминированная последовательность узлов
- **Supervisor** — LLM решает, какой агент вызвать следующим
- **Hybrid** — pipeline на верхнем уровне, supervisor'ы внутри subgraph'ов

Чистый Supervisor уводит в loop'ы (LLM сама решает маршрут). Чистый Pipeline слишком жёсткий (Plan/Gather/Review требуют динамических решений).

## Решение

**Hybrid (Hierarchical):**
- **Верхний уровень:** детерминированный pipeline (Plan → Gather → Code → Validate → Review → Commit)
- **Внутри Plan/Gather/Review:** mini-supervisor subgraph (LLM решает стратегию, Python валидирует)
- **Внутри Validate:** parallel fan-out без supervisor (3 валидатора параллельно)
- **Роутеры `route_after_*`:** только Python-функции, не LLM

## Ключевое правило

**LLM не может пропустить валидацию. LLM не может сделать 4-ю итерацию. LLM не может решить "commit без review".** Это фиксируется в коде роутеров:

```python
def route_after_validate(state) -> Literal["review", "retry"]:
    return "review" if state.validation_passed else "retry"
```

## Последствия

### Положительные
- Воспроизводимость: одинаковый вход → одинаковый маршрут
- Тестируемость: роутеры — чистые функции, легко property-test
- Predictability для внешнего клиента: `_next_action` в Facade строится по тем же правилам
- Mini-supervisor даёт гибкость там, где она нужна (Plan, Gather, Review)

### Отрицательные
- Больше кода, чем чистый Supervisor (но это хорошо — явность важнее краткости)
- Subgraph'ы LangGraph — не самый интуитивный API

## Связанные документы
- 00-overview.md (раздел 4: agent pipeline)
- 04-pipeline-contracts.md (роутеры, типы узлов)
- ADR-0009 (Pipeline contracts)
