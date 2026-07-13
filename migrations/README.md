# migrations/ — стратегия миграций

> См. ADR-0018 (TaskState migration strategy) и D-2026-07-13-05 (разделение
> ответственности с LangGraph `setup()`).

## Две категории миграций

### 1. LangGraph checkpoint-таблицы — управляются `AsyncPostgresSaver.setup()`

Таблицы `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`,
`checkpoint_migrations` создаются **самим LangGraph** (через внутренний
`MIGRATIONS` список `langgraph-checkpoint-postgres`) при вызове
`await saver.setup()` в `PersistenceManager.__aenter__`.

**Alembic их НЕ трогает.** Дублирование schema-owner'а привело бы к конфликту.
`setup()` идемпотентен и вызывается при каждом старте `PersistenceManager`.

### 2. Приложенческие таблицы — `migrations/alembic/`

Таблицы `bsl_modules` (codebase MCP, TD-S4.2-02) и `health_check` сейчас
создаются идемпотентным `docker/postgres/init.sql` (`CREATE TABLE IF NOT EXISTS`)
при первом старте контейнера Postgres.

Alembic scaffolding (`alembic.ini` + `migrations/alembic/`) развёрнут как
**инфраструктура-готовность**: baseline-миграция `0001_baseline` документирует,
что существующие таблицы созданы вне Alembic (brownfield). **Все будущие
schema-изменения приложенческих таблиц** идут через Alembic:

```bash
# Создать новую миграцию (из корня репо):
unset VIRTUAL_ENV && UV_CACHE_DIR=/tmp/uv-cache uv run --directory . alembic revision -m "add_xxx_table"

# Применить миграции:
unset VIRTUAL_ENV && UV_CACHE_DIR=/tmp/uv-cache uv run --directory . alembic upgrade head

# Стампить текущее состояние (для существующих БД):
unset VIRTUAL_ENV && UV_CACHE_DIR=/tmp/uv-cache uv run --directory . alembic stamp head
```

### 3. TaskState pickle-миграции — `migrations/state/`

LangGraph сериализует `TaskState` через pickle в checkpoint-таблицы. При
**breaking change** `TaskState` (rename/type-change поля) старые checkpoint'ы
могут стать нечитаемыми. Стратегия (ADR-0018):

1. `TaskState.schema_version: int = Field(default=1)` — bump только при breaking
   change (добавление/удаление полей — bump НЕ нужен, Pydantic backwards-compatible).
2. Migration-скрипт в `migrations/state/NNNN_description.py` с функциями
   `upgrade(checkpoint_data: dict) -> dict` / `downgrade(...)` (шаблон — ADR-0018 §5).
3. При загрузке checkpoint: `schema_version < CURRENT` → применить миграции
   по цепочке; `schema_version > CURRENT` → ошибка (downgrade не поддерживается).

Сейчас `CURRENT_SCHEMA_VERSION = 1` (нет breaking changes). Шаблон-заглушка —
`migrations/state/0001_initial.py`.

## Принципы (ADR-0018)

- `schema_version` bumps только при **breaking changes** (rename, type change).
- При добавлении/удалении полей — `schema_version` не меняется (Pydantic
  backwards-compatible).
- Миграции **однонаправленные** — downgrade не поддерживается в production.
- Перед breaking change — ADR с описанием что меняется и почему.

## Структура

```
migrations/
├── README.md                     ← этот файл
├── alembic.ini                   ← (в корне репо) конфиг Alembic
├── alembic/
│   ├── env.py                    ← Alembic environment (async, psycopg)
│   ├── script.py.mako            ← шаблон новых миграций
│   └── versions/
│       └── 0001_baseline.py      ← baseline-stamp (brownfield, без DDL)
└── state/
    ├── __init__.py
    ├── 0001_initial.py           ← шаблон TaskState pickle-миграции (ADR-0018 §5)
    └── README.md                 ← про state-миграции
```
