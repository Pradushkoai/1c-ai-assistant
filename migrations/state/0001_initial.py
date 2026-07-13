"""Migration 0001: initial TaskState schema (baseline).

Revision ID: state-0001
Schema version: 1
Create Date: 2026-07-13

Контекст (ADR-0018): это baseline-миграция TaskState. ``schema_version=1``
соответствует текущей структуре TaskState (включая поле ``schema_version``,
добавленное в TD-S5-01). Никаких преобразований не требуется — миграция
существует как шаблон-образец для будущих breaking changes.

Цепочка применения (будущее):
    загружен checkpoint с schema_version=1
    → CURRENT_SCHEMA_VERSION (1) → ничего не делаем
    загружен checkpoint с schema_version=2 (после breaking change)
    → CURRENT (3) → применить 0002→0003

Пример реальной миграции (когда понадобится)::

    \"\"\"Migration 0002: rename foo → bar in TaskState.\"\"\"

    def upgrade(checkpoint_data: dict) -> dict:
        if \"foo\" in checkpoint_data:
            checkpoint_data[\"bar\"] = checkpoint_data.pop(\"foo\")
        return checkpoint_data

    def downgrade(checkpoint_data: dict) -> dict:
        # Downgrade не поддерживается в production (ADR-0018 §6).
        raise NotImplementedError(\"downgrade not supported\")
"""

from __future__ import annotations

REVISION_ID = "state-0001"
TARGET_SCHEMA_VERSION = 1


def upgrade(checkpoint_data: dict) -> dict:
    """Применить миграцию к десериализованному state.

    Для baseline — no-op: просто гарантируем наличие schema_version.

    Args:
        checkpoint_data: десериализованный TaskState (dict).

    Returns:
        Тот же dict с актуальным schema_version.
    """
    if "schema_version" not in checkpoint_data:
        checkpoint_data["schema_version"] = TARGET_SCHEMA_VERSION
    return checkpoint_data


def downgrade(checkpoint_data: dict) -> dict:
    """Откатить миграцию.

    Downgrade не поддерживается в production (ADR-0018 §6).

    Raises:
        NotImplementedError: всегда.
    """
    raise NotImplementedError("downgrade not supported (ADR-0018 §6)")
