"""metadata_indexer — сборка unified-metadata-index.json из XML конфигурации.

Сканирует data/configs/{name}/{version}/ через iter_metadata_files,
парсит каждый XML, собирает unified индекс в derived/configs/{name}/{version}/.

Структура индекса:
    {
        "config_meta": {...},        # ConfigMeta как dict
        "objects": {
            "Catalog": [...],         # список CatalogMetadata
            "Document": [...],
            "CommonModule": [...],
            "<OtherType>": [...],     # минимальный ObjectMetadata для неизвестных
        },
        "stats": {
            "total_objects": N,
            "by_type": {"Catalog": N1, "Document": N2, ...},
            "parse_errors": [{"type": "...", "name": "...", "error": "..."}],
        },
        "generated_at": "2026-...",
        "config_name": "...",
        "config_version": "...",
    }

См. ADR-0006 (Data Layer) и ADR-0008 (PathManager).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from parsers.models import (
    CatalogMetadata,
    CommonModuleMetadata,
    DocumentMetadata,
    MetadataType,
    ObjectMetadata,
    ObjectRef,
)
from parsers.xml import (
    iter_metadata_files,
    parse_catalog,
    parse_common_module,
    parse_configuration,
    parse_document,
)
from parsers.xml._xml_utils import (
    find_child,
    get_comment,
    get_name,
    get_synonym,
    parse_xml,
)

log = logging.getLogger(__name__)


# Типы объектов, для которых есть полные парсеры
SUPPORTED_TYPES: dict[str, Any] = {
    "Catalog": CatalogMetadata,
    "Document": DocumentMetadata,
    "CommonModule": CommonModuleMetadata,
}


def build_metadata_index(
    config_dir: Path,
    config_name: str,
    config_version: str,
) -> dict[str, Any]:
    """Собрать unified-metadata-index.json из XML конфигурации.

    Args:
        config_dir: директория с распакованной конфигурацией
            (содержит Configuration.xml и поддиректории Catalogs/, Documents/, ...).
        config_name: имя конфигурации (для логов и метаданных).
        config_version: версия конфигурации.

    Returns:
        Словарь с индексом (готов к сериализации в JSON).

    Raises:
        FileNotFoundError: если config_dir не существует.
        ValueError: если Configuration.xml отсутствует или невалидна.

    Examples:
        >>> from pathlib import Path
        >>> from parsers.indexers import build_metadata_index
        >>> index = build_metadata_index(
        ...     Path("data/configs/ut11/4.5.3"),
        ...     "ut11", "4.5.3",
        ... )
        >>> index["stats"]["total_objects"]
        42
    """
    if not config_dir.exists():
        raise FileNotFoundError(f"Config directory not found: {config_dir}")

    log.info("Building metadata index for %s/%s from %s", config_name, config_version, config_dir)

    # 1. Парсим Configuration.xml
    config_xml = config_dir / "Configuration.xml"
    if not config_xml.exists():
        raise ValueError(f"Configuration.xml not found in {config_dir}")

    config_meta = parse_configuration(config_xml)

    # 2. Итерируем по всем XML файлам метаданных
    objects_by_type: dict[str, list[dict[str, Any]]] = {}
    parse_errors: list[dict[str, str]] = []
    total_objects = 0

    for metadata_type, object_name, xml_path in iter_metadata_files(config_dir):
        # Пропускаем Configuration — уже обработали
        if metadata_type == "Configuration":
            continue

        try:
            obj_dict = _parse_object(metadata_type, xml_path)
            if obj_dict is not None:
                objects_by_type.setdefault(metadata_type, []).append(obj_dict)
                total_objects += 1
        except Exception as exc:
            log.warning("Failed to parse %s %s (%s): %s", metadata_type, object_name, xml_path, exc)
            parse_errors.append(
                {
                    "type": metadata_type,
                    "name": object_name,
                    "error": str(exc),
                    "path": str(xml_path),
                }
            )

    # 3. Статистика
    by_type = {k: len(v) for k, v in objects_by_type.items()}

    log.info(
        "Index built: %d objects (%s), %d errors",
        total_objects,
        ", ".join(f"{k}={v}" for k, v in by_type.items()),
        len(parse_errors),
    )

    return {
        "config_meta": config_meta.model_dump(mode="json"),
        "objects": objects_by_type,
        "stats": {
            "total_objects": total_objects,
            "by_type": by_type,
            "parse_errors": parse_errors,
        },
        "generated_at": datetime.now(UTC).isoformat(),
        "config_name": config_name,
        "config_version": config_version,
    }


def _parse_object(metadata_type: str, xml_path: Path) -> dict[str, Any] | None:
    """Парсить один объект метаданных по типу.

    Для известных типов (Catalog, Document, CommonModule) — использует полный парсер.
    Для остальных — универсальный парсер (имя, синоним, тип).

    Args:
        metadata_type: тип объекта ('Catalog', 'Document', ...).
        xml_path: путь к XML файлу.

    Returns:
        Словарь с метаданными объекта (готов к JSON), или None если парсинг не удался.
    """
    if metadata_type == "Catalog":
        obj = parse_catalog(xml_path)
        return obj.model_dump(mode="json")
    if metadata_type == "Document":
        obj_doc = parse_document(xml_path)
        return obj_doc.model_dump(mode="json")
    if metadata_type == "CommonModule":
        obj_cm = parse_common_module(xml_path)
        return obj_cm.model_dump(mode="json")

    # Универсальный парсер для остальных типов
    return _parse_generic_object(metadata_type, xml_path)


def _parse_generic_object(metadata_type: str, xml_path: Path) -> dict[str, Any] | None:
    """Универсальный парсер для типов без специализированного парсера.

    Извлекает минимум: object_ref, metadata_type, name, synonym, comment.
    Используется для Enum, InformationRegister, AccumulationRegister, Subsystem, Role,
    DataProcessor, Report, и т.д.

    Args:
        metadata_type: тип объекта ('Enum', 'InformationRegister', ...).
        xml_path: путь к XML файлу.

    Returns:
        Словарь с минимальными метаданными объекта.
    """
    root = parse_xml(xml_path)

    # Находим элемент с именем типа (Catalog, Document, Enum, ...)
    obj_elem = find_child(root, metadata_type)
    if obj_elem is None:
        # Иногда корень уже сам объект (без MetaDataObject обёртки)
        from parsers.xml._xml_utils import _local_name

        if _local_name(root) == metadata_type:
            obj_elem = root
        else:
            log.warning("Expected <%s>, got <%s> in %s", metadata_type, _local_name(root), xml_path)
            return None

    properties = find_child(obj_elem, "Properties")
    if properties is None:
        return None

    name = get_name(properties) or xml_path.parent.name
    synonym = get_synonym(properties)
    comment = get_comment(properties)

    try:
        mt = MetadataType(metadata_type)
    except ValueError:
        # Неизвестный тип — пропускаем (не должен случаться, но safety)
        return None

    obj = ObjectMetadata(
        object_ref=ObjectRef(type=metadata_type, name=name),
        metadata_type=mt,
        name=name,
        synonym=synonym,
        comment=comment,
    )
    return obj.model_dump(mode="json")


def save_metadata_index(
    index: dict[str, Any],
    output_path: Path,
) -> None:
    """Сохранить индекс в JSON файл.

    Args:
        index: словарь с индексом (из build_metadata_index).
        output_path: путь для сохранения (обычно derived/.../unified-metadata-index.json).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Index saved to %s (%d KB)", output_path, output_path.stat().st_size // 1024)


def load_metadata_index(index_path: Path) -> dict[str, Any] | None:
    """Загрузить ранее сохранённый индекс.

    Args:
        index_path: путь к unified-metadata-index.json.

    Returns:
        Словарь с индексом, или None если файл не существует.
    """
    if not index_path.exists():
        return None
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def get_object_from_index(
    index: dict[str, Any],
    object_ref: str,
) -> dict[str, Any] | None:
    """Найти объект в индексе по ссылке.

    Args:
        index: словарь с индексом.
        object_ref: строка вида 'Catalog.Товары', 'Document.Продажа'.

    Returns:
        Словарь с метаданными объекта, или None если не найден.
    """
    if "." not in object_ref:
        return None
    type_, name = object_ref.split(".", 1)

    objects_by_type = index.get("objects", {})
    objects = objects_by_type.get(type_, [])
    for obj in objects:
        # object_ref внутри dict — это {type, name}
        ref = obj.get("object_ref", {}) if isinstance(obj, dict) else {}
        if ref.get("name") == name:
            return obj if isinstance(obj, dict) else None
    return None
