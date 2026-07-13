"""baseline — brownfield stamp (без DDL).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-13

Контекст (ADR-0018, D-2026-07-13-05):
- LangGraph checkpoint-таблицы (checkpoints, checkpoint_blobs, checkpoint_writes,
  checkpoint_migrations) создаются AsyncPostgresSaver.setup() — Alembic их НЕ
  трогает.
- Приложенческие таблицы (bsl_modules, health_check) на данный момент создаются
  идемпотентным docker/postgres/init.sql (CREATE TABLE IF NOT EXISTS) при первом
  старте контейнера Postgres.

Эта миграция — **baseline-stamp**: НЕ выполняет DDL, только фиксирует точку
отсчёта. Все будущие schema-изменения приложенческих таблиц — новые миграции
поверх этого baseline.

Для существующей БД (где таблицы уже созданы init.sql):
    alembic stamp head

Для свежей БД: init.sql отрабатывает при создании контейнера, затем
    alembic stamp head
(или `alembic upgrade head` — пока нечего применять).
"""
from __future__ import annotations

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Baseline — намеренно без DDL.

    Существующие таблицы (bsl_modules, health_check) создаются
    docker/postgres/init.sql. LangGraph checkpoint-таблицы —
    AsyncPostgresSaver.setup(). Здесь ничего не создаём.
    """


def downgrade() -> None:
    """Downgrade baseline невозможен (точка отсчёта)."""
