# ADR-0018: TaskState migration strategy

**Статус:** Accepted
**Дата:** 2026-07-11

## Контекст

`TaskState` — главное состояние pipeline, сериализуется LangGraph checkpointer'ом
в Postgres (production) или MemorySaver (tests). По мере развития проекта
`TaskState` будет меняться: добавляться поля, удаляться, переименовываться.

LangGraph `PostgresSaver` сериализует state через pickle в таблицу `checkpoints`.
При изменении структуры `TaskState` старые checkpoint'ы могут стать нечитаемыми.

Нужна стратегия миграций.

## Рассмотренные варианты

1. **Alembic миграции** — классический подход для SQL схем
2. **Версионирование через `schema_version` поле** — в самом TaskState
3. **Ручные миграции** — Python скрипты, запускаемые при обновлении
4. **Не мигрировать** — удалять старые checkpoint'ы при breaking change

## Решение

**Комбинированный подход: версионирование + alembic для breaking changes.**

### 1. Версионирование TaskState

Добавить поле `schema_version: int = 1` в `TaskState`:

```python
class TaskState(ModelConfig):
    schema_version: int = Field(default=1, ge=1)
    # ... остальные поля
```

При загрузке checkpoint:
- `schema_version == 1` → текущая версия, загружаем как есть
- `schema_version < CURRENT_VERSION` → запускаем миграцию
- `schema_version > CURRENT_VERSION` → ошибка (downgrade не поддерживается)

### 2. Классификация изменений

| Тип изменения | Backward compatible? | Миграция нужна? |
|---|---|---|
| Добавление опционального поля с default | ✅ Да | Нет |
| Удаление поля | ✅ Да (поле игнорируется) | Нет |
| Переименование поля | ❌ Нет | Да |
| Изменение типа поля | ❌ Нет | Да |
| Удаление required поля из модели | ❌ Нет | Да (поле становится None) |

### 3. Для MVP (Sprint 2): MemorySaver

В Sprint 2 используется `MemorySaver` — нет Postgres, нет миграций.
Checkpoint'ы живут в памяти, умирают при рестарте процесса.

Это нормально для MVP — длинные задачи (>1 часа) появятся в Sprint 4.

### 4. Для Sprint 4: PostgresSaver + Alembic

Когда переходим на PostgresSaver:

1. **Alembic** управляет SQL-схемой (таблицы LangGraph: `checkpoints`, `writes`, `migration_blobs`)
2. **Python миграции** для pickle-сериализованного state (если изменилась структура TaskState)
3. Migration script: читает старый checkpoint → десериализует → применяет миграцию → сериализует → записывает обратно

### 5. Migration script шаблон

```python
# migrations/versions/002_add_schema_version.py
"""Migration: add schema_version field to TaskState checkpoints."""

def upgrade(checkpoint_data: dict) -> dict:
    """Применить миграцию к десериализованному state."""
    if "schema_version" not in checkpoint_data:
        checkpoint_data["schema_version"] = 1
    return checkpoint_data

def downgrade(checkpoint_data: dict) -> dict:
    """Откатить миграцию (если нужно)."""
    checkpoint_data.pop("schema_version", None)
    return checkpoint_data
```

### 6. Правила

- `schema_version` bumps только при **breaking changes** (rename, type change)
- При добавлении/удалении полей — `schema_version` не меняется
- Миграции **однонаправленные** — downgrade не поддерживается в production
- Перед breaking change — ADR с описанием что меняется и почему

## Последствия

### Положительные
- Явная версия схемы — понятно, какой миграции нужны
- MemorySaver для MVP — нет накладных расходов
- Alembic для SQL-схемы — стандартный инструмент
- Миграции state — изолированные Python скрипты

### Отрицательные
- `schema_version` поле в TaskState — лишнее поле для MVP
- Migration scripts — дополнительный код для поддержки
- Breaking changes требуют планирования (ADR + migration script)

## Реализация

- [ ] Добавить `schema_version: int = Field(default=1)` в TaskState (Sprint 2)
- [ ] Настроить Alembic (Sprint 4, при переходе на PostgresSaver)
- [ ] Создать `migrations/` директорию (Sprint 4)
- [ ] Написать первый migration script как шаблон (Sprint 4)

## Связанные документы

- ADR-0014 (Error taxonomy + PostgresSaver)
- ADR-0009 (Pipeline contracts — TaskState)
- docs/architecture/09-error-taxonomy.md (PersistenceManager)
