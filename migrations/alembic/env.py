"""Alembic environment configuration.

Управляет ТОЛЬКО приложенческими таблицами (bsl_modules, health_check и будущие).
LangGraph checkpoint-таблицы создаёт AsyncPostgresSaver.setup() — Alembic их
НЕ трогает (см. migrations/README.md, ADR-0018, D-2026-07-13-05).

DSN берётся из env DATABASE_URL (с приоритетом), иначе из alembic.ini.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# this is the Alembic Config object, which provides access to .ini values.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DSN: env DATABASE_URL имеет приоритет над alembic.ini (где sqlalchemy.url пуст).
# Это позволяет переиспользовать тот же DSN, что и PersistenceManager / docker-compose.
db_url = os.environ.get("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# target_metadata — None: мы используем autogenerate=False (миграции пишутся
# вручную). LangGraph-таблицы НЕ описываем здесь — они вне зоны ответственности
# Alembic. При необходимости autogenerate для приложенческих таблиц — описать
# модели SQLAlchemy здесь.
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect to DB and apply)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
