"""parsers.xml — парсеры XML метаданных 1С.

Каждый парсер возвращает Pydantic v2 модель из parsers.models.

Функции:
    parse_configuration(path) → ConfigMeta
    parse_catalog(path) → CatalogMetadata
    parse_document(path) → DocumentMetadata
    parse_common_module(path) → CommonModuleMetadata
    parse_form(path) → FormMetadata

См. ADR-0007 (Pydantic v2 frozen models) и ADR-0006 (Data Layer).
"""

from __future__ import annotations

from ._xml_utils import (
    extract_attributes,
    extract_child_object_names,
    extract_child_object_refs,
    find_all,
    find_first,
    find_text,
    get_comment,
    get_name,
    get_synonym,
    get_uuid,
    iter_metadata_files,
    parse_xml,
    parse_xml_string,
)
from .catalog import parse_catalog
from .common_module import parse_common_module
from .configuration import get_configuration_child_objects, parse_configuration
from .document import parse_document
from .form import parse_form
from .subsystem_role import parse_role, parse_subsystem

__all__ = [
    # Парсеры
    "parse_configuration",
    "parse_catalog",
    "parse_document",
    "parse_common_module",
    "parse_form",
    "parse_subsystem",
    "parse_role",
    "get_configuration_child_objects",
    # Утилиты
    "parse_xml",
    "parse_xml_string",
    "find_text",
    "find_all",
    "find_first",
    "get_name",
    "get_synonym",
    "get_comment",
    "get_uuid",
    "extract_attributes",
    "extract_child_object_names",
    "extract_child_object_refs",
    "iter_metadata_files",
]
