"""Парсер CommonModule.xml — общий модуль 1С.

Возвращает CommonModuleMetadata (см. parsers.models.metadata).
"""

from __future__ import annotations

from pathlib import Path

from parsers.models import CommonModuleMetadata, MetadataType, ObjectRef

from ._xml_utils import (
    find_child,
    find_text,
    get_comment,
    get_name,
    get_synonym,
    parse_xml,
)


def parse_common_module(xml_path: Path) -> CommonModuleMetadata:
    """Распарсить CommonModule.xml → CommonModuleMetadata.

    Args:
        xml_path: путь к CommonModule.xml.

    Returns:
        CommonModuleMetadata.

    Raises:
        FileNotFoundError: если файл не существует.
        ValueError: если XML не содержит <CommonModule>.

    Examples:
        >>> from pathlib import Path
        >>> from parsers.xml import parse_common_module
        >>> cm = parse_common_module(Path("data/configs/ut11/4.5.3/CommonModules/ОбщегоНазначения/ОбщегоНазначения.xml"))
        >>> cm.name
        'ОбщегоНазначения'
        >>> cm.server
        True
    """
    root = parse_xml(xml_path)

    cm_elem = find_child(root, "CommonModule")
    if cm_elem is None:
        from ._xml_utils import _local_name

        raise ValueError(f"CommonModule.xml: expected <CommonModule> element, got <{_local_name(root)}>")

    properties = find_child(cm_elem, "Properties")
    if properties is None:
        raise ValueError("CommonModule.xml: missing <Properties> element")

    name = get_name(properties) or xml_path.parent.name
    synonym = get_synonym(properties)
    comment = get_comment(properties)

    def _get_bool(tag_name: str, default: bool = False) -> bool:
        value = find_text(properties, tag_name)
        if value is None:
            return default
        return value.strip().lower() == "true"

    server = _get_bool("Server", default=True)
    global_ = _get_bool("Global", default=False)
    client = _get_bool("Client", default=False)
    client_managed_application = _get_bool("ClientManagedApplication", default=False)
    external_connection = _get_bool("ExternalConnection", default=False)
    privileged = _get_bool("Privileged", default=False)

    # 'global' — Python keyword, используем alias через model_validate
    return CommonModuleMetadata.model_validate(
        {
            "object_ref": ObjectRef(type="CommonModule", name=name),
            "metadata_type": MetadataType.COMMON_MODULE,
            "name": name,
            "synonym": synonym,
            "comment": comment,
            "server": server,
            "global": global_,  # alias → field global_
            "client": client,
            "client_managed_application": client_managed_application,
            "external_connection": external_connection,
            "privileged": privileged,
        }
    )
