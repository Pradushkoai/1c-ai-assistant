"""1c-ai CLI — точка входа.

Поддерживает подкоманды:
    1c-ai init                     — создать data/, derived/, runtime/ директории
    1c-ai config add               — добавить конфигурацию из ZIP
    1c-ai config build             — построить индексы
    1c-ai config list              — список конфигураций
    1c-ai config remove            — удалить конфигурацию
    1c-ai validate                 — preflight check
    1c-ai health                   — health check (persistence + BSL LS) для Docker
    1c-ai mcp serve --server NAME  — запустить MCP stdio-сервер (facade/metadata/codebase/kb/bsl_ls/git)
    1c-ai serve                    — запустить HTTP REST API server (FastAPI :8000)
    1c-ai bsl-ls download|status   — управление BSL Language Server (jar download, статус)
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
def bsl_ls() -> None:
    """Управление BSL Language Server (Stage 6 TD-S8-02).

    download — скачать bsl-language-server.jar.
    status   — проверить Java + jar + версию + mode.
    """


@bsl_ls.command("download")
@click.option(
    "--version",
    "-v",
    default="0.25.5",
    help="Версия BSL LS (default: 0.25.5).",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Перезаписать если jar уже существует.",
)
def bsl_ls_download(version: str, force: bool) -> None:
    """Скачать bsl-language-server.jar с GitHub releases.

    Примеры:

        1c-ai bsl-ls download                   # default v0.25.5

        1c-ai bsl-ls download --version 0.26.0  # конкретная версия

        1c-ai bsl-ls download --force            # перезаписать
    """
    from .cli_commands.bsl_ls import cmd_bsl_ls_download

    sys.exit(cmd_bsl_ls_download(version=version, force=force))


@bsl_ls.command("status")
def bsl_ls_status() -> None:
    """Показать статус BSL LS (Java, jar, version, mode, backend, health)."""
    from .cli_commands.bsl_ls import cmd_bsl_ls_status

    sys.exit(cmd_bsl_ls_status())


@main.command()
@click.option(
    "--host",
    "-h",
    default="0.0.0.0",
    help="Bind host (default 0.0.0.0 — для Docker).",
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=8000,
    help="Bind port (default 8000).",
)
def serve(host: str, port: int) -> None:
    """Запустить HTTP REST API server (Stage 5 TD-S7-02).

    FastAPI/uvicorn на :8000 (default). Endpoints:
    - GET  /health — health check
    - GET  /servers — список MCP серверов
    - GET  /tools/{server} — список tools
    - POST /facade/{tool} — Facade lifecycle tools
    - POST /domain/{server}/{tool} — доменные tools

    Примеры:

        1c-ai serve                          # default 0.0.0.0:8000

        1c-ai serve --host 127.0.0.1 --port 9000

    Docs: http://localhost:8000/docs (Swagger UI).
    """
    from .cli_commands.serve import cmd_serve

    sys.exit(cmd_serve(host=host, port=port))


@main.group()
def mcp() -> None:
    """Управление MCP-серверами (Stage 4 TD-S6-03).

    Поддерживает 6 серверов: facade, metadata, codebase, kb, bsl_ls, git.
    """


@mcp.command("serve")
@click.option(
    "--server",
    "-s",
    type=click.Choice(["facade", "metadata", "codebase", "kb", "bsl_ls", "git"]),
    default=None,
    help="Имя MCP-сервера для запуска (stdio).",
)
@click.option(
    "--list",
    "list_only",
    is_flag=True,
    help="Показать доступные серверы и выйти.",
)
def mcp_serve(server: str | None, list_only: bool) -> None:
    """Запустить MCP stdio-сервер.

    Cursor подключается к MCP через stdio. Поддерживается 6 серверов (ADR-0003).

    Примеры:

        1c-ai mcp serve --list

        1c-ai mcp serve --server facade      # Facade (8 lifecycle tools)

        1c-ai mcp serve --server metadata    # metadata MCP (4 tools)

        1c-ai mcp serve --server kb          # KB MCP (7 tools)
    """
    from .cli_commands.mcp import cmd_mcp_serve

    sys.exit(cmd_mcp_serve(server=server or "", list_only=list_only))


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
