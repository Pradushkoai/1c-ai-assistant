"""`1c-ai validate` — preflight check."""

from __future__ import annotations

import click
from data_layer import PathManager


def cmd_validate() -> int:
    """Проверить готовность окружения.

    Returns:
        0 если всё готово, 1 если есть проблемы.
    """
    try:
        pm = PathManager()
    except FileNotFoundError as exc:
        click.echo(f"❌ {exc}", err=True)
        click.echo("Запустите `1c-ai init` сначала.", err=True)
        return 1

    click.echo("Проверка окружения...")
    click.echo("")

    validation = pm.validate()
    all_ok = True

    # Группы проверок
    critical_paths = ["data_dir", "derived_dir", "runtime_dir"]
    optional_paths = ["knowledge_base_dir", "vendor_dir", "config_registry", "kb_index"]

    click.echo("Критичные директории:")
    for key in critical_paths:
        exists = validation[key]
        status = "✅" if exists else "❌"
        click.echo(f"  {status} {key}")
        if not exists:
            all_ok = False

    click.echo("")
    click.echo("Опциональные (могут отсутствовать на старте):")
    for key in optional_paths:
        exists = validation[key]
        status = "✅" if exists else "⚠️ "
        click.echo(f"  {status} {key}")

    # Конфигурации
    click.echo("")
    click.echo("Конфигурации:")
    from data_layer import ConfigRegistry

    registry = ConfigRegistry(pm.config_registry_path())
    entries = list(registry.list())
    if not entries:
        click.echo("  (нет загруженных конфигураций)")
        click.echo("  Используйте: 1c-ai config add --name X --version Y --zip X.zip")
    else:
        for entry in entries:
            click.echo(f"  • {entry.name}/{entry.version}")

    click.echo("")
    if all_ok:
        click.echo("✅ Окружение готово.")
        if not entries:
            click.echo("   Но конфигурации не загружены. См. подсказку выше.")
        return 0

    click.echo("❌ Окружение не готово. Запустите `1c-ai init`.", err=True)
    return 1
