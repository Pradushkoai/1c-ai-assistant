"""`1c-ai init` — создать базовую структуру директорий."""

from __future__ import annotations

import click
from data_layer import PathManager


def cmd_init(quiet: bool = False) -> int:
    """Создать data/, derived/, runtime/ директории.

    Returns:
        0 при успехе, 1 при ошибке.
    """
    try:
        pm = PathManager()
    except FileNotFoundError as exc:
        click.echo(f"❌ {exc}", err=True)
        click.echo("Создайте paths.env в корне проекта. Пример:", err=True)
        click.echo("  DATA_DIR=./data", err=True)
        click.echo("  DERIVED_DIR=./derived", err=True)
        click.echo("  RUNTIME_DIR=./runtime", err=True)
        click.echo("  KNOWLEDGE_BASE_DIR=./knowledge-base", err=True)
        click.echo("  VENDOR_DIR=./vendor", err=True)
        return 1

    if not quiet:
        click.echo("Создание директорий...")

    pm.ensure_dirs()

    if not quiet:
        # Показать, что создано
        click.echo(f"  ✅ data/    → {pm._resolve('${DATA_DIR}')}")  # type: ignore[attr-defined]
        click.echo(f"  ✅ derived/ → {pm._resolve('${DERIVED_DIR}')}")  # type: ignore[attr-defined]
        click.echo(f"  ✅ runtime/ → {pm.runtime_dir()}")
        click.echo(f"  ✅ kb/      → {pm.knowledge_base_dir()}")
        click.echo(f"  ✅ vendor/  → {pm.vendor_dir()}")
        click.echo("")
        click.echo("Готово. Теперь можно:")
        click.echo("  1c-ai config add --name <X> --version <Y> --zip <X.zip>")
        click.echo("  1c-ai config build --name <X>")

    return 0
