"""Парсер Configuration.xml — корневой файл конфигурации 1С.

Возвращает ConfigMeta (см. parsers.models.config).
"""

from __future__ import annotations

from pathlib import Path

from parsers.models import ConfigMeta, MetadataType, Version, VersionInfo

from ._xml_utils import (
    extract_child_object_refs,
    find_child,
    find_text,
    get_name,
    get_synonym,
    parse_xml,
)


def parse_configuration(xml_path: Path) -> ConfigMeta:
    """Распарсить Configuration.xml → ConfigMeta.

    Args:
        xml_path: путь к Configuration.xml.

    Returns:
        ConfigMeta — корневые метаданные конфигурации.

    Raises:
        FileNotFoundError: если файл не существует.
        ValueError: если XML не содержит ожидаемых элементов.

    Examples:
        >>> from pathlib import Path
        >>> from parsers.xml import parse_configuration
        >>> config = parse_configuration(Path("data/configs/ut11/4.5.3/Configuration.xml"))
        >>> config.name
        'УправлениеТорговлей'
    """
    root = parse_xml(xml_path)

    # Структура: <MetaDataObject><Configuration uuid="..."><Properties>...</Properties>
    #             <ChildObjects>...</ChildObjects></Configuration></MetaDataObject>
    config_elem = find_child(root, "Configuration")
    if config_elem is None:
        raise ValueError(f"Configuration.xml: expected <Configuration> element, got <{_local_name_safe(root)}>")

    properties = find_child(config_elem, "Properties")
    if properties is None:
        raise ValueError("Configuration.xml: missing <Properties> element")

    # Извлекаем основные поля
    name = get_name(properties) or "Unknown"
    synonym = get_synonym(properties)

    # Version (из <Version> в Properties)
    version_str = find_text(properties, "Version", "0.0.0.0")
    version_info = VersionInfo(
        version=version_str or "0.0.0.0",
        edition=None,
        vendor=find_text(properties, "Vendor"),
        description=synonym,
    )

    # Platform version (из <CompatibilityMode>)
    compatibility = find_text(properties, "CompatibilityMode")
    if compatibility and compatibility.startswith("Version8_3_"):
        parts = compatibility.replace("Version8_3_", "").split("_")
        platform_version_str = "8.3." + parts[0]
    else:
        platform_version_str = "8.3.20"  # дефолт
    platform_version = Version.from_string(platform_version_str)

    # DataLockControlMode
    lock_mode = find_text(properties, "DataLockControlMode", "Managed") or "Managed"

    # Default language
    default_language_elem = find_text(properties, "DefaultLanguage")
    if default_language_elem and "." in default_language_elem:
        # Language.Русский → 'Русский'
        default_language = default_language_elem.split(".", 1)[1]
    else:
        default_language = "ru"

    # Подсчёт объектов каждого типа
    object_counts: dict[MetadataType, int] = {}
    child_objects = find_child(config_elem, "ChildObjects")
    if child_objects is not None:
        for mt in MetadataType:
            if mt == MetadataType.CONFIGURATION:
                continue
            # Считаем дочерние элементы с local-name == mt.value
            count = sum(1 for child in child_objects if _local_name_safe(child) == mt.value)
            if count > 0:
                object_counts[mt] = count

    data_separators: list[str] = []

    return ConfigMeta(
        name=name,
        synonym=synonym,
        version_info=version_info,
        platform_version=platform_version,
        default_data_lock_mode=lock_mode,
        default_language=default_language,
        data_separators=data_separators,
        object_counts=object_counts,
    )


def get_configuration_child_objects(
    xml_path: Path,
) -> dict[str, list[str]]:
    """Получить дочерние объекты конфигурации.

    Returns:
        Словарь {MetadataType: [имена объектов]}.
    """
    root = parse_xml(xml_path)
    config_elem = find_child(root, "Configuration")
    if config_elem is None:
        return {}

    result: dict[str, list[str]] = {}
    for mt in MetadataType:
        if mt == MetadataType.CONFIGURATION:
            continue
        refs = extract_child_object_refs(config_elem, mt.value)
        if refs:
            result[mt.value] = refs
    return result


def _local_name_safe(elem: object) -> str:
    """Безопасное извлечение local-name (для любых элементов)."""
    from ._xml_utils import _local_name  # type: ignore

    try:
        return _local_name(elem)  # type: ignore[arg-type]
    except Exception:
        return ""
