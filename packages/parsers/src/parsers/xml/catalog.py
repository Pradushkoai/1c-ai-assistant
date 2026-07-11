"""Парсер Catalog.xml — справочник 1С.

Возвращает CatalogMetadata (см. parsers.models.metadata).
"""

from __future__ import annotations

from pathlib import Path

from parsers.models import CatalogMetadata, MetadataType, ObjectRef

from ._xml_utils import (
    extract_attributes,
    extract_child_object_names,
    find_child,
    find_text,
    get_comment,
    get_name,
    get_synonym,
    parse_xml,
)


def parse_catalog(xml_path: Path, config_name: str | None = None) -> CatalogMetadata:
    """Распарсить Catalog.xml → CatalogMetadata.

    Args:
        xml_path: путь к Catalog.xml.
        config_name: имя конфигурации (для object_ref, опционально).

    Returns:
        CatalogMetadata.

    Raises:
        FileNotFoundError: если файл не существует.
        ValueError: если XML не содержит <Catalog>.

    Examples:
        >>> from pathlib import Path
        >>> from parsers.xml import parse_catalog
        >>> cat = parse_catalog(Path("data/configs/ut11/4.5.3/Catalogs/Товары/Товары.xml"))
        >>> cat.name
        'Товары'
        >>> cat.code_length
        9
    """
    root = parse_xml(xml_path)

    catalog_elem = find_child(root, "Catalog")
    if catalog_elem is None:
        from ._xml_utils import _local_name

        raise ValueError(f"Catalog.xml: expected <Catalog> element, got <{_local_name(root)}>")

    properties = find_child(catalog_elem, "Properties")
    if properties is None:
        raise ValueError("Catalog.xml: missing <Properties> element")

    name = get_name(properties) or xml_path.parent.name
    synonym = get_synonym(properties)
    comment = get_comment(properties)

    hierarchy_type = find_text(properties, "HierarchyType", "HierarchyItems") or "HierarchyItems"
    code_length_str = find_text(properties, "CodeLength", "9")
    try:
        code_length = int(code_length_str or "9")
    except ValueError:
        code_length = 9

    code_series = find_text(properties, "CodeSeries", "WholeCatalog") or "WholeCatalog"
    description_length_str = find_text(properties, "DescriptionLength", "50")
    try:
        description_length = int(description_length_str or "50")
    except ValueError:
        description_length = 50

    # Owners — справочники-владельцы
    owners: list[str] = []
    owners_elem = find_child(properties, "Owners")
    if owners_elem is not None:
        from ._xml_utils import _local_name

        for item in owners_elem.iter():
            if _local_name(item) == "Item" and item.text:
                text = item.text.strip()
                if ":" in text and text:
                    owners.append(text)

    predefined: list[str] = []

    # Атрибуты (обычные + табличные)
    attributes, _tabular_sections = extract_attributes(catalog_elem)

    # Forms, Templates, Commands
    forms = extract_child_object_names(catalog_elem, "Form")
    templates = extract_child_object_names(catalog_elem, "Template")
    commands = extract_child_object_names(catalog_elem, "Command")

    return CatalogMetadata(
        object_ref=ObjectRef(type="Catalog", name=name),
        metadata_type=MetadataType.CATALOG,
        name=name,
        synonym=synonym,
        comment=comment,
        attributes=attributes,
        forms=forms,
        templates=templates,
        commands=commands,
        hierarchy_type=hierarchy_type,
        owners=owners,
        predefined=predefined,
        code_length=code_length,
        code_series=code_series,
        description_length=description_length,
    )
