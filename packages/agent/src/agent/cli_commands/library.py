"""`1c-ai library` — управление библиотеками (БСП, БПО).

Sprint 4.2 (TD-S4.2-05): библиотеки индексируются как отдельный слой
(source_layer=library), шарится между конфигурациями.

Подкоманды:
    library add      — распаковать ZIP и зарегистрировать библиотеку
    library build    — построить индексы (metadata + api-reference + call graph)
    library list     — показать список
    library remove   — удалить
"""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import click
from data_layer import PathManager


def _load_library_registry(pm: PathManager) -> list[dict]:
    """Загрузить реестр библиотек."""
    path = pm.library_registry_path()
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _save_library_registry(pm: PathManager, entries: list[dict]) -> None:
    """Сохранить реестр библиотек."""
    path = pm.library_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def cmd_library_add(
    name: str,
    version: str,
    zip_path: Path,
    title: str | None = None,
) -> int:
    """Распаковать ZIP и зарегистрировать библиотеку.

    Returns:
        0 при успехе, 1 при ошибке.
    """
    try:
        pm = PathManager()
    except FileNotFoundError as exc:
        click.echo(f"❌ {exc}", err=True)
        return 1

    zip_path_obj = Path(zip_path)
    if not zip_path_obj.exists():
        click.echo(f"❌ ZIP не найден: {zip_path_obj}", err=True)
        return 1

    # Проверяем, нет ли уже такой библиотеки
    entries = _load_library_registry(pm)
    for e in entries:
        if e.get("name") == name and e.get("version") == version:
            click.echo(
                f"❌ Библиотека {name}/{version} уже существует. Используйте `1c-ai library remove` сначала.",
                err=True,
            )
            return 1

    # Целевая директория
    target_dir = pm.data_library_dir(name, version)
    if target_dir.exists():
        click.echo(f"⚠️  Директория уже существует, перезаписываю: {target_dir}", err=True)
        shutil.rmtree(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)

    # Распаковываем ZIP
    click.echo(f"Распаковываю {zip_path_obj.name} → {target_dir}...")
    try:
        with zipfile.ZipFile(zip_path_obj, "r") as zf:
            names = zf.namelist()
            if not names:
                click.echo("❌ ZIP архив пустой", err=True)
                return 1
            zf.extractall(target_dir)
    except zipfile.BadZipFile as exc:
        click.echo(f"❌ Повреждённый ZIP: {exc}", err=True)
        return 1

    # Регистрируем
    entry = {
        "name": name,
        "version": version,
        "added_at": datetime.now(UTC).isoformat(),
        "source_path": str(target_dir),
        "index_path": str(pm.derived_library_dir(name, version)),
        "title": title or name,
    }
    entries.append(entry)
    _save_library_registry(pm, entries)

    click.echo(f"✅ Библиотека {name}/{version} зарегистрирована")
    click.echo(f"  📁 Источник: {target_dir}")
    click.echo(f"  📁 Индексы: {pm.derived_library_dir(name, version)}")
    return 0


def cmd_library_build(
    name: str,
    version: str | None,
    force: bool,
) -> int:
    """Построить индексы для библиотеки.

    Returns:
        0 при успехе, 1 при ошибке.
    """
    try:
        pm = PathManager()
    except FileNotFoundError as exc:
        click.echo(f"❌ {exc}", err=True)
        return 1

    entries = _load_library_registry(pm)
    if version:
        entries = [e for e in entries if e.get("name") == name and e.get("version") == version]
    else:
        entries = [e for e in entries if e.get("name") == name]

    if not entries:
        click.echo(f"❌ Библиотека '{name}' не найдена. Используйте `1c-ai library list`.", err=True)
        return 1

    from parsers.bsl import build_call_graph, save_call_graph
    from parsers.indexers import build_metadata_index, save_metadata_index
    from parsers.indexers.api_reference_indexer import build_api_reference, save_api_reference

    for entry in entries:
        lib_name = entry["name"]
        lib_version = entry["version"]
        config_dir = Path(entry["source_path"])
        if not config_dir.exists():
            click.echo(f"❌ Директория не найдена: {config_dir}", err=True)
            return 1

        click.echo(f"Индексация библиотеки {lib_name}/{lib_version}...")

        # 1. Metadata index
        try:
            index = build_metadata_index(config_dir, lib_name, lib_version)
            meta_path = pm.library_metadata_index(lib_name, lib_version)
            save_metadata_index(index, meta_path)
            click.echo(f"  ✅ Объектов: {index['stats']['total_objects']}")
        except Exception as exc:
            click.echo(f"  ⚠️  metadata index: {exc}")

        # 2. api-reference
        try:
            api_ref = build_api_reference(config_dir, lib_name, lib_version)
            api_path = pm.library_api_reference_index(lib_name, lib_version)
            save_api_reference(api_ref, api_path)
            click.echo(f"  ✅ Export-методов: {api_ref['stats']['total_export_methods']}")
        except Exception as exc:
            click.echo(f"  ⚠️  api-reference: {exc}")

        # 3. call graph
        try:
            cg = build_call_graph(config_dir, lib_name, lib_version)
            cg_path = pm.library_call_graph_index(lib_name, lib_version)
            save_call_graph(cg, cg_path)
            click.echo(f"  ✅ Рёбер вызовов: {cg['stats']['total_edges']}")
        except Exception as exc:
            click.echo(f"  ⚠️  call-graph: {exc}")

    return 0


def cmd_library_list() -> int:
    """Показать список библиотек."""
    try:
        pm = PathManager()
    except FileNotFoundError as exc:
        click.echo(f"❌ {exc}", err=True)
        return 1

    entries = _load_library_registry(pm)
    if not entries:
        click.echo("Библиотеки не зарегистрированы.")
        click.echo("Используйте `1c-ai library add --name БСП --version 3.1 --zip bsp.zip`")
        return 0

    click.echo(f"Зарегистрировано библиотек: {len(entries)}\n")
    for e in entries:
        click.echo(f"  {e['name']}/{e['version']}")
        click.echo(f"    Источник: {e.get('source_path', 'N/A')}")
        click.echo(f"    Индексы:  {e.get('index_path', 'N/A')}")
        click.echo(f"    Добавлена: {e.get('added_at', 'N/A')[:10]}")
        click.echo()
    return 0


def cmd_library_remove(name: str, version: str) -> int:
    """Удалить библиотеку."""
    try:
        pm = PathManager()
    except FileNotFoundError as exc:
        click.echo(f"❌ {exc}", err=True)
        return 1

    entries = _load_library_registry(pm)
    new_entries = [e for e in entries if not (e.get("name") == name and e.get("version") == version)]

    if len(new_entries) == len(entries):
        click.echo(f"❌ Библиотека {name}/{version} не найдена.", err=True)
        return 1

    _save_library_registry(pm, new_entries)

    # Удаляем директории
    import contextlib
    with contextlib.suppress(Exception):
        shutil.rmtree(pm.data_library_dir(name, version))
    with contextlib.suppress(Exception):
        shutil.rmtree(pm.derived_library_dir(name, version))

    click.echo(f"✅ Библиотека {name}/{version} удалена")
    return 0
