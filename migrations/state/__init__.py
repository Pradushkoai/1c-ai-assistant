"""TaskState pickle-миграции (ADR-0018 §5).

LangGraph сериализует TaskState через pickle в checkpoint-таблицы. При breaking
change TaskState (rename/type-change поля) старые checkpoint'ы могут стать
нечитаемыми. Эта цепочка миграций применяется при загрузке checkpoint, если
``schema_version < CURRENT_SCHEMA_VERSION``.

Шаблон миграции (ADR-0018 §5)::

    def upgrade(checkpoint_data: dict) -> dict:
        '''Применить миграцию к десериализованному state.'''
        ...
        return checkpoint_data

    def downgrade(checkpoint_data: dict) -> dict:
        '''Откатить миграцию (если нужно).'''
        ...
        return checkpoint_data

Правила (ADR-0018 §6):
- ``schema_version`` bumps только при breaking changes (rename, type change).
- При добавлении/удалении полей — bump НЕ нужен (Pydantic backwards-compatible).
- Миграции однонаправленные — downgrade не поддерживается в production.
- Перед breaking change — ADR с описанием что меняется и почему.
"""

CURRENT_SCHEMA_VERSION = 1
