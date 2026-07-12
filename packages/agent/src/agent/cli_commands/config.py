"""`1c-ai config` — управление конфигурациями 1С.

Подкоманды:
    config add      — распаковать ZIP и зарегистрировать
    config build    — построить индексы
    config list     — показать список
    config remove   — удалить
"""

from __future__ import annotations

import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import click
from data_layer import ConfigRegistry, PathManager
from parsers.indexers import build_metadata_index, save_metadata_index
from parsers.models import ConfigRegistryEntry


def cmd_config_add(
    name: str,
    version: str,
    zip_path: Path,
    title: str | None = None,
) -> int:
    """Распаковать ZIP и зарегистрировать конфигурацию.

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

    # Проверяем, нет ли уже такой конфигурации
    registry = ConfigRegistry(pm.config_registry_path())
    existing = registry.get(name, version)
    if existing is not None:
        click.echo(
            f"❌ Конфигурация {name}/{version} уже существует. Используйте `1c-ai config remove` сначала.",
            err=True,
        )
        return 1

    # Целевая директория
    target_dir = pm.data_config_dir(name, version)
    if target_dir.exists():
        click.echo(
            f"⚠️  Директория уже существует, перезаписываю: {target_dir}",
            err=True,
        )
        shutil.rmtree(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)

    # Распаковываем ZIP
    click.echo(f"Распаковываю {zip_path_obj.name} → {target_dir}...")
    try:
        with zipfile.ZipFile(zip_path_obj, "r") as zf:
            # Проверяем, что ZIP не пустой
            names = zf.namelist()
            if not names:
                click.echo("❌ ZIP архив пустой", err=True)
                return 1
            zf.extractall(target_dir)
    except zipfile.BadZipFile as exc:
        click.echo(f"❌ Повреждённый ZIP: {exc}", err=True)
        return 1

    # Проверяем, что в распакованном есть Configuration.xml
    # (может быть в корне или в поддиректории — например, ZIP может содержать
    # папку с именем конфигурации)
    config_xml = target_dir / "Configuration.xml"
    if not config_xml.exists():
        # Ищем в поддиректориях
        found = list(target_dir.rglob("Configuration.xml"))
        if len(found) == 1:
            # Переносим содержимое поддиректории в target_dir
            subdir = found[0].parent
            click.echo(f"Перемещаю содержимое {subdir.name}/ в корень...")
            for item in subdir.iterdir():
                shutil.move(str(item), str(target_dir / item.name))
            subdir.rmdir()
        elif len(found) > 1:
            click.echo(
                "❌ Найдено несколько Configuration.xml в ZIP. Структура ZIP должна быть плоской.",
                err=True,
            )
            return 1
        else:
            click.echo(
                "❌ Configuration.xml не найден в ZIP. Это действительно выгрузка 1С?",
                err=True,
            )
            return 1

    # Регистрируем в реестре
    entry = ConfigRegistryEntry(
        name=name,
        version=version,
        title=title,
        added_at=datetime.now(UTC),
        source_zip=str(zip_path_obj),
        source_path=str(target_dir),
        index_path=str(pm.derived_config_dir(name, version)),
        freshness_checked_at=None,
        is_fresh=None,
    )
    registry.add(entry)

    # Подсчитываем количество XML файлов
    xml_count = sum(1 for _ in target_dir.rglob("*.xml"))

    click.echo(f"✅ Конфигурация {name}/{version} добавлена")
    click.echo(f"   Распаковано в: {target_dir}")
    click.echo(f"   XML файлов: {xml_count}")
    click.echo("   Зарегистрировано в реестре")
    click.echo("")
    click.echo(f"Теперь: 1c-ai config build --name {name} --version {version}")

    return 0


def cmd_config_build(
    name: str,
    version: str | None,
    force: bool,
    check_freshness: bool,
) -> int:
    """Построить индексы для конфигурации.

    Returns:
        0 при успехе, 1 при ошибке.
    """
    try:
        pm = PathManager()
    except FileNotFoundError as exc:
        click.echo(f"❌ {exc}", err=True)
        return 1

    registry = ConfigRegistry(pm.config_registry_path())

    # Найти все записи с данным name
    entries = [e for e in registry.list() if e.name == name]
    if not entries:
        click.echo(
            f"❌ Конфигурация '{name}' не найдена. Используйте `1c-ai config list` для списка.",
            err=True,
        )
        return 1

    # Фильтр по версии
    if version:
        entries = [e for e in entries if e.version == version]
        if not entries:
            click.echo(f"❌ Конфигурация {name}/{version} не найдена.", err=True)
            return 1

    if check_freshness:
        # Только проверка свежести
        click.echo(f"Проверка свежести для {name}:")
        for entry in entries:
            freshness = pm.freshness_check(entry.name, entry.version)
            # is_fresh в реестре = True если unified_metadata свежий
            unified_fresh = freshness.get("unified_metadata", False)
            registry.update_freshness(entry.name, entry.version, unified_fresh)

            click.echo(f"  {entry.name}/{entry.version}:")
            for index_name, is_fresh in freshness.items():
                status = "✅ fresh" if is_fresh else "❌ stale"
                click.echo(f"    {index_name}: {status}")
        return 0

    if not force:
        # Проверяем свежесть и пропускаем свежие (если не --force)
        # Внимание: проверяем только unified_metadata, так как api_reference,
        # call_graph, dependency_graph строятся в других спринтах.
        for entry in entries:
            freshness = pm.freshness_check(entry.name, entry.version)
            if freshness.get("unified_metadata", False):
                click.echo(
                    f"ℹ️  {entry.name}/{entry.version}: индексы уже свежие "
                    f"(используйте --force для принудительной пересборки)"
                )
                return 0

    # Строим индексы
    for entry in entries:
        config_dir = Path(entry.source_path)
        if not config_dir.exists():
            click.echo(f"❌ Директория не найдена: {config_dir}", err=True)
            return 1

        output_path = pm.unified_metadata_index(entry.name, entry.version)

        click.echo(f"Индексация {entry.name}/{entry.version}...")

        try:
            index = build_metadata_index(config_dir, entry.name, entry.version)
        except Exception as exc:
            click.echo(f"❌ Ошибка индексации: {exc}", err=True)
            return 1

        save_metadata_index(index, output_path)

        # Обновляем статус свежести в реестре
        registry.update_freshness(entry.name, entry.version, True)

        # Статистика
        stats = index["stats"]
        click.echo(f"  ✅ Объектов: {stats['total_objects']}")
        for type_, count in stats["by_type"].items():
            click.echo(f"     {type_}: {count}")
        if stats["parse_errors"]:
            click.echo(f"  ⚠️  Ошибок парсинга: {len(stats['parse_errors'])}")
            for err in stats["parse_errors"][:5]:
                click.echo(f"     {err['type']}/{err['name']}: {err['error']}")
            if len(stats["parse_errors"]) > 5:
                click.echo(f"     ... и ещё {len(stats['parse_errors']) - 5} ошибок")
        click.echo(f"  📁 Индекс: {output_path}")

        # ─── Sprint 4.2 (TD-S4.2-07): api-reference ────────────────────────
        try:
            from parsers.indexers import save_api_reference
            from parsers.indexers.api_reference_indexer import build_api_reference as _build_api_ref

            api_ref = _build_api_ref(config_dir, entry.name, entry.version)
            api_ref_path = output_path.parent / "api-reference.json"
            save_api_reference(api_ref, api_ref_path)
            click.echo(f"  ✅ Export-методов: {api_ref['stats']['total_export_methods']}")
            click.echo(f"     Модулей с методами: {api_ref['stats']['total_modules']}")
        except Exception as exc:
            click.echo(f"  ⚠️  api-reference не построен: {exc}")

        # ─── Sprint 4.1 (TD-S4.1-02): call graph ───────────────────────────
        try:
            from parsers.bsl import build_call_graph, save_call_graph

            cg = build_call_graph(config_dir, entry.name, entry.version)
            cg_path = output_path.parent / "call-graph.json"
            save_call_graph(cg, cg_path)
            click.echo(f"  ✅ Рёбер вызовов: {cg['stats']['total_edges']}")
        except Exception as exc:
            click.echo(f"  ⚠️  call-graph не построен: {exc}")

        # ─── Sprint 4.1 (TD-S4.1-04): dependency graph ─────────────────────
        try:
            from parsers.xml import build_dependency_graph, save_dependency_graph

            dg = build_dependency_graph(config_dir, entry.name, entry.version)
            dg_path = output_path.parent / "dependency-graph.json"
            save_dependency_graph(dg, dg_path)
            click.echo(f"  ✅ Зависимостей: {dg['stats']['total_edges']}")
        except Exception as exc:
            click.echo(f"  ⚠️  dependency-graph не построен: {exc}")

    return 0


def cmd_config_list() -> int:
    """Показать список конфигураций.

    Returns:
        0 при успехе, 1 при ошибке.
    """
    try:
        pm = PathManager()
    except FileNotFoundError as exc:
        click.echo(f"❌ {exc}", err=True)
        return 1

    registry = ConfigRegistry(pm.config_registry_path())
    entries = list(registry.list())

    if not entries:
        click.echo("Конфигурации не загружены.")
        click.echo("Используйте: 1c-ai config add --name X --version Y --zip X.zip")
        return 0

    click.echo("Загруженные конфигурации:")
    click.echo("")

    for entry in entries:
        # Статус свежести
        if entry.is_fresh is None:
            fresh_status = "?  не проверено"
        elif entry.is_fresh:
            fresh_status = "✅ fresh"
        else:
            fresh_status = "❌ stale"

        click.echo(f"  {entry.name}/{entry.version}  {fresh_status}")

        if entry.title:
            click.echo(f"    title: {entry.title}")

        # Размер директории
        source_path = Path(entry.source_path)
        if source_path.exists():
            xml_count = sum(1 for _ in source_path.rglob("*.xml"))
            click.echo(f"    XML: {xml_count} файлов в {source_path}")

        # Индекс
        index_path = pm.unified_metadata_index(entry.name, entry.version)
        if index_path.exists():
            size_kb = index_path.stat().st_size // 1024
            click.echo(f"    Индекс: {index_path} ({size_kb} КБ)")
        else:
            click.echo(f"    Индекс: не построен (запустите 1c-ai config build --name {entry.name})")

        click.echo("")

    return 0


def cmd_config_remove(name: str, version: str, keep_data: bool) -> int:
    """Удалить конфигурацию.

    Returns:
        0 при успехе, 1 при ошибке.
    """
    try:
        pm = PathManager()
    except FileNotFoundError as exc:
        click.echo(f"❌ {exc}", err=True)
        return 1

    registry = ConfigRegistry(pm.config_registry_path())
    entry = registry.get(name, version)
    if entry is None:
        click.echo(f"❌ Конфигурация {name}/{version} не найдена.", err=True)
        return 1

    # Удаляем из реестра
    registry.remove(name, version)

    # Удаляем данные с диска
    if not keep_data:
        source_path = Path(entry.source_path)
        if source_path.exists():
            click.echo(f"Удаляю {source_path}...")
            shutil.rmtree(source_path)

        # Удаляем индексы
        derived_dir = pm.derived_config_dir(name, version)
        if derived_dir.exists():
            click.echo(f"Удаляю {derived_dir}...")
            shutil.rmtree(derived_dir)

    click.echo(f"✅ Конфигурация {name}/{version} удалена")
    return 0
