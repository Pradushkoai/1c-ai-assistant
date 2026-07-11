"""`1c-ai hbk` — управление .hbk файлами синтакс-помощника.

Минимальная версия для MVP — извлечение списка методов платформы.
Полная версия (с availability, version_since, и т.д.) — в Спринте 3.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import click
from data_layer import PathManager


def cmd_hbk_load(platform_version: str, hbk_path: Path) -> int:
    """Загрузить .hbk файлы в SQLite platform-methods.db.

    Минимальная версия: просто создаёт БД и записывает версию платформы.
    Полный парсинг .hbk — в Спринте 3.

    Returns:
        0 при успехе, 1 при ошибке.
    """
    try:
        pm = PathManager()
    except FileNotFoundError as exc:
        click.echo(f"❌ {exc}", err=True)
        return 1

    hbk_dir = Path(hbk_path)
    if not hbk_dir.exists():
        click.echo(f"❌ Директория не найдена: {hbk_dir}", err=True)
        return 1

    # Подсчитываем .hbk файлы
    hbk_files = list(hbk_dir.rglob("*.hbk"))
    if not hbk_files:
        # Возможно, это сами файлы (а не директория с ними)
        click.echo(f"⚠️  .hbk файлы не найдены в {hbk_dir}")
        click.echo("    Проверьте, что вы указали правильную директорию.")
        click.echo("    Обычно .hbk файлы лежат в shcntx_ru/ поддиректории.")
        return 1

    db_path = pm.platform_methods_db(platform_version)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    click.echo(f"Загрузка .hbk файлов для платформы {platform_version}...")
    click.echo(f"  Найдено файлов: {len(hbk_files)}")
    click.echo(f"  Целевая БД: {db_path}")

    # Создаём минимальную структуру БД
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS platform_methods (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                signature TEXT,
                description TEXT,
                is_procedure INTEGER DEFAULT 0,
                category TEXT,
                source_file TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_methods_name
                ON platform_methods(name);

            CREATE TABLE IF NOT EXISTS platform_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        # Метаданные — через параметры (защита от SQL injection)
        conn.executemany(
            "INSERT OR REPLACE INTO platform_meta (key, value) VALUES (?, ?)",
            [
                ("platform_version", platform_version),
                ("loaded_at", datetime.now(UTC).isoformat()),
                ("source_path", str(hbk_dir)),
                ("hbk_files_count", str(len(hbk_files))),
            ],
        )
        conn.commit()

    db_size = db_path.stat().st_size
    click.echo(f"✅ БД создана: {db_path} ({db_size} байт)")
    click.echo("")
    click.echo("ℹ️  Полный парсинг .hbk файлов будет реализован в Спринте 3.")
    click.echo("   Сейчас БД содержит только метаданные о загрузке.")
    return 0
