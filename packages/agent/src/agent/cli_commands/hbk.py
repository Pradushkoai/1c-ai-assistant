"""`1c-ai hbk` — управление .hbk файлами синтакс-помощника.

Использует parsers.hbk.syntax_helper для распаковки и парсинга.
"""

from __future__ import annotations

import time
from pathlib import Path

import click
from data_layer import PathManager


def cmd_hbk_load(platform_version: str, hbk_path: Path) -> int:
    """Загрузить .hbk файлы в SQLite platform-methods.db."""
    try:
        pm = PathManager()
    except FileNotFoundError as exc:
        click.echo(f"❌ {exc}", err=True)
        return 1

    hbk_dir = Path(hbk_path)
    if not hbk_dir.exists():
        click.echo(f"❌ Директория не найдена: {hbk_dir}", err=True)
        return 1

    hbk_files = list(hbk_dir.rglob("*.hbk"))
    if not hbk_files:
        click.echo(f"⚠️  .hbk файлы не найдены в {hbk_dir}")
        return 1

    db_path = pm.platform_methods_db(platform_version)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    click.echo(f"Загрузка .hbk файлов для платформы {platform_version}...")
    click.echo(f"  Найдено файлов: {len(hbk_files)}")
    click.echo(f"  Целевая БД: {db_path}")
    click.echo("  Парсер: container32 + HTML")

    from parsers.hbk.syntax_helper import build_platform_methods_index

    start_time = time.monotonic()
    try:
        count = build_platform_methods_index(hbk_dir, platform_version, db_path)
    except Exception as exc:
        click.echo(f"❌ Ошибка парсинга: {exc}", err=True)
        return 1
    elapsed = time.monotonic() - start_time

    db_size = db_path.stat().st_size
    click.echo(f"✅ БД создана: {db_path} ({db_size:,} байт)")
    click.echo(f"✅ Методов загружено: {count:,}")
    click.echo(f"⏱  Время: {elapsed:.1f}s")

    if count == 0:
        click.echo("")
        click.echo("⚠️  Методов не найдено. Проверьте, что .hbk файлы не повреждены.")
    elif count < 100:
        click.echo("")
        click.echo("⚠️  Мало методов (<100).")

    return 0
