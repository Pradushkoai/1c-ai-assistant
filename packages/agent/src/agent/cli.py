"""1c-ai CLI — точка входа.

Поддерживает подкоманды:
    1c-ai init                     — создать data/, derived/, runtime/ директории
    1c-ai config add               — добавить конфигурацию из ZIP
    1c-ai config build             — построить индексы
    1c-ai config list              — список конфигураций
    1c-ai config remove            — удалить конфигурацию
    1c-ai validate                 — preflight check
    1c-ai health                   — health check (persistence + BSL LS) для Docker
    1c-ai hbk load                 — загрузить .hbk файлы (минимальная версия)

Использует click для CLI, data_layer.PathManager для путей,
parsers для парсинга.

См. ADR-0008 (PathManager) и ADR-0006 (Data Layer).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from . import __version__


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="1c-ai")
@click.option(
    "--project",
    "-p",
    type=click.Path(exists=False, file_okay=False, path_type=Path),
    default=None,
    envvar="ONEC_AI_PROJECT",
    help="Корневая директория проекта (где paths.env). По умолчанию — текущая директория.",
)
@click.pass_context
def main(ctx: click.Context, project: Path | None) -> None:
    """1C AI Assistant — multi-agent system for solving 1C:Enterprise 8.3 tasks.

    Поддерживает загрузку и индексацию 1С конфигураций, в будущем — генерацию
    BSL-кода через LangGraph pipeline.

    Документация: https://github.com/Pradushkoai/1c-ai-assistant
    """
    # Если указан --project, меняем cwd чтобы PathManager() нашёл paths.env
    if project is not None:
        os.chdir(project)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command()
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Минимальный вывод (только ошибки)",
)
def init(quiet: bool) -> None:
    """Создать базовую структуру директорий (data/, derived/, runtime/).

    Команда безопасна — уже существующие директории не перезаписываются.
    """
    from .cli_commands.init import cmd_init

    sys.exit(cmd_init(quiet=quiet))


@main.group()
def config() -> None:
    """Управление конфигурациями 1С."""


@config.command("add")
@click.option("--name", required=True, help="Имя конфигурации (например, 'ut11')")
@click.option("--version", required=True, help="Версия (например, '4.5.3')")
@click.option(
    "--zip",
    "zip_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Путь к ZIP-архиву с XML-выгрузкой конфигурации",
)
@click.option("--title", help="Человекочитаемое название")
def config_add(name: str, version: str, zip_path: Path, title: str | None) -> None:
    """Добавить конфигурацию из ZIP-архива.

    Распаковывает ZIP в data/configs/{name}/{version}/ и регистрирует в реестре.

    Пример:

        1c-ai config add --name ut11 --version 4.5.3 --zip ut11.zip
    """
    from .cli_commands.config import cmd_config_add

    sys.exit(cmd_config_add(name=name, version=version, zip_path=zip_path, title=title))


@config.command("build")
@click.option("--name", required=True, help="Имя конфигурации")
@click.option("--version", help="Версия (если не указана — единственная или все)")
@click.option("--force", is_flag=True, help="Перестроить индексы даже если свежие")
@click.option("--check-freshness", is_flag=True, help="Только проверить свежесть, не строить")
def config_build(
    name: str,
    version: str | None,
    force: bool,
    check_freshness: bool,
) -> None:
    """Построить индексы для конфигурации.

    Создаёт unified-metadata-index.json в derived/configs/{name}/{version}/.

    Примеры:

        1c-ai config build --name ut11 --version 4.5.3

        1c-ai config build --name ut11 --check-freshness
    """
    from .cli_commands.config import cmd_config_build

    sys.exit(
        cmd_config_build(
            name=name,
            version=version,
            force=force,
            check_freshness=check_freshness,
        )
    )


@config.command("list")
def config_list() -> None:
    """Показать список загруженных конфигураций."""
    from .cli_commands.config import cmd_config_list

    sys.exit(cmd_config_list())


@config.command("remove")
@click.option("--name", required=True, help="Имя конфигурации")
@click.option("--version", required=True, help="Версия")
@click.option(
    "--keep-data",
    is_flag=True,
    help="Не удалять данные с диска, только убрать из реестра",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Пропустить подтверждение",
)
def config_remove(name: str, version: str, keep_data: bool, yes: bool) -> None:
    """Удалить конфигурацию из реестра (и опционально с диска)."""
    if not yes:
        click.confirm(
            f"Удалить конфигурацию {name}/{version}?",
            abort=True,
        )
    from .cli_commands.config import cmd_config_remove

    sys.exit(cmd_config_remove(name=name, version=version, keep_data=keep_data))


@main.command()
def validate() -> None:
    """Preflight check — проверить, что окружение готово к работе.

    Проверяет:
    - data/, derived/, runtime/ директории существуют
    - paths.env валиден
    - config-registry.json существует
    - knowledge-base/index.json существует
    """
    from .cli_commands.validate import cmd_validate

    sys.exit(cmd_validate())


@main.command()
def health() -> None:
    """Health check — проверить состояние persistence + BSL LS (для Docker).

    Проверяет:
    - PersistenceManager.health_check() (PostgresSaver или MemorySaver)
    - BSL LS HTTP /health (если BSL_LS_HTTP_URL задан)

    Выход: 0 если OK, 1 если есть проблемы. Вывод: JSON в stdout.
    """
    from .cli_commands.health import cmd_health

    sys.exit(cmd_health())


@main.group()
def hbk() -> None:
    """Управление .hbk файлами синтакс-помощника 1С."""


@hbk.command("load")
@click.option(
    "--version",
    "platform_version",
    required=True,
    help="Версия платформы (например, '8.3.20')",
)
@click.option(
    "--path",
    "hbk_path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Путь к директории с .hbk файлами",
)
def hbk_load(platform_version: str, hbk_path: Path) -> None:
    """Загрузить .hbk файлы синтакс-помощника.

    Извлекает методы платформы в SQLite platform-methods.db.

    Пример:

        1c-ai hbk load --version 8.3.20 --path /path/to/syntaxhelp/
    """
    from .cli_commands.hbk import cmd_hbk_load

    sys.exit(cmd_hbk_load(platform_version=platform_version, hbk_path=hbk_path))


@main.command()
@click.option("--task", "-t", required=True, help="Описание задачи на естественном языке")
@click.option("--config", "config_name", required=True, help="Имя конфигурации")
@click.option("--version", "config_version", default=None, help="Версия конфигурации")
@click.option(
    "--platform",
    "platform_version",
    default="8.3.20",
    help="Версия платформы 1С (по умолчанию 8.3.20)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Сохранить результат в файл (по умолчанию — stdout)",
)
def generate(
    task: str,
    config_name: str,
    config_version: str | None,
    platform_version: str,
    output: Path | None,
) -> None:
    """Сгенерировать BSL-код через pipeline.

    Запускает полный pipeline: preflight → plan → gather → code → validate → review → commit.

    Примеры:

        1c-ai generate --task "Создать функцию Сложить(a, b)" --config mini --version 1.0

        1c-ai generate -t "ОбработкаПроведения" --config ut11 --version 4.5.3 -o result.bsl
    """
    from .cli_commands.generate import cmd_generate

    sys.exit(
        cmd_generate(
            task=task,
            config_name=config_name,
            config_version=config_version,
            platform_version=platform_version,
            output=str(output) if output else None,
        )
    )


@main.group()
def library() -> None:
    """Управление библиотеками (БСП, БПО).

    Библиотеки индексируются как отдельный слой (source_layer=library),
    шарится между конфигурациями.

    Пример:

        1c-ai library add --name БСП --version 3.1 --zip bsp.zip

        1c-ai library build --name БСП

        1c-ai library list
    """


@library.command(name="add")
@click.option("--name", required=True, help="Имя библиотеки (например, 'БСП')")
@click.option("--version", required=True, help="Версия (например, '3.1')")
@click.option(
    "--zip",
    "zip_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Путь к ZIP архиву библиотеки",
)
@click.option("--title", help="Человекочитаемое название")
def library_add(name: str, version: str, zip_path: Path, title: str | None) -> None:
    """Распаковать ZIP и зарегистрировать библиотеку."""
    from .cli_commands.library import cmd_library_add

    sys.exit(cmd_library_add(name=name, version=version, zip_path=zip_path, title=title))


@library.command(name="build")
@click.option("--name", required=True, help="Имя библиотеки")
@click.option("--version", default=None, help="Версия (если не указана — все версии)")
@click.option("--force", is_flag=True, help="Принудительная пересборка")
def library_build(name: str, version: str | None, force: bool) -> None:
    """Построить индексы для библиотеки (metadata + api-reference + call graph)."""
    from .cli_commands.library import cmd_library_build

    sys.exit(cmd_library_build(name=name, version=version, force=force))


@library.command(name="list")
def library_list() -> None:
    """Показать список зарегистрированных библиотек."""
    from .cli_commands.library import cmd_library_list

    sys.exit(cmd_library_list())


@library.command(name="remove")
@click.option("--name", required=True, help="Имя библиотеки")
@click.option("--version", required=True, help="Версия")
def library_remove(name: str, version: str) -> None:
    """Удалить библиотеку."""
    from .cli_commands.library import cmd_library_remove

    sys.exit(cmd_library_remove(name=name, version=version))


if __name__ == "__main__":
    main()
