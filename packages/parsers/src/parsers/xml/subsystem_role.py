"""Парсер Subsystem.xml → SubsystemMetadata и Role.xml → RoleMetadata.

Sprint 4.1 (TD-S4.1-01): Form/Subsystem/Role парсеры для metadata MCP.

Subsystem — ключевая для Planner: content (список объектов) показывает
какие объекты связаны логически (например, Catalog.Товары + Document.Продажа
в подсистеме «Продажи»).
"""

from __future__ import annotations

import logging
from pathlib import Path

from parsers.models import (
    ObjectRef,
    RoleMetadata,
    SubsystemMetadata,
)
from parsers.xml._xml_utils import (
    _local_name,
    find_child,
    get_comment,
    get_name,
    get_synonym,
    parse_xml,
)

log = logging.getLogger(__name__)


def parse_subsystem(xml_path: Path) -> SubsystemMetadata:
    """Распарсить Subsystem.xml → SubsystemMetadata.

    Извлекает:
    - name, synonym, comment (из Properties)
    - content: список ObjectRef объектов подсистемы (из Content/xr:Item)
    - child_subsystems: имена дочерних подсистем

    Args:
        xml_path: путь к Subsystem.xml.

    Returns:
        SubsystemMetadata.

    Examples:
        >>> from pathlib import Path
        >>> sub = parse_subsystem(Path("Subsystems/Продажи.xml"))
        >>> sub.name
        'Продажи'
        >>> len(sub.content)
        15
        >>> sub.content[0]
        ObjectRef(type='Catalog', name='Товары')
    """
    root = parse_xml(xml_path)

    sub_elem = find_child(root, "Subsystem")
    if sub_elem is None:
        if _local_name(root) == "Subsystem":
            sub_elem = root
        else:
            raise ValueError(f"Expected <Subsystem> in {xml_path}")

    properties = find_child(sub_elem, "Properties")
    if properties is None:
        raise ValueError(f"No <Properties> in subsystem {xml_path}")

    name = get_name(properties) or xml_path.stem
    synonym = get_synonym(properties)
    comment = get_comment(properties)

    # Content — список объектов подсистемы
    content: list[ObjectRef] = []
    content_elem = find_child(properties, "Content")
    if content_elem is not None:
        for item in content_elem:
            if _local_name(item) == "Item":
                # Текст элемента — ссылка вида "Catalog.Товары"
                ref_text = item.text or ""
                if ref_text and "." in ref_text:
                    try:
                        ref = ObjectRef.from_string(ref_text)
                        content.append(ref)
                    except ValueError:
                        log.debug("Cannot parse subsystem content ref: %s", ref_text)

    # Child subsystems — ищем вложенные <Subsystem> или <ChildSubsystems>
    child_subsystems: list[str] = []
    child_subs_elem = find_child(properties, "ChildSubsystems")
    if child_subs_elem is not None:
        for item in child_subs_elem:
            if _local_name(item) == "Item" and item.text:
                child_subsystems.append(item.text)

    return SubsystemMetadata(
        object_ref=ObjectRef(type="Subsystem", name=name),
        name=name,
        synonym=synonym,
        comment=comment,
        content=content,
        child_subsystems=child_subsystems,
    )


def parse_role(xml_path: Path) -> RoleMetadata:
    """Распарсить Role.xml → RoleMetadata.

    Простая модель: name, synonym, comment.

    Args:
        xml_path: путь к Role.xml.

    Returns:
        RoleMetadata.

    Examples:
        >>> from pathlib import Path
        >>> role = parse_role(Path("Roles/ПолныеПрава.xml"))
        >>> role.name
        'ПолныеПрава'
    """
    root = parse_xml(xml_path)

    role_elem = find_child(root, "Role")
    if role_elem is None:
        if _local_name(root) == "Role":
            role_elem = root
        else:
            raise ValueError(f"Expected <Role> in {xml_path}")

    properties = find_child(role_elem, "Properties")
    if properties is None:
        raise ValueError(f"No <Properties> in role {xml_path}")

    name = get_name(properties) or xml_path.stem
    synonym = get_synonym(properties)
    comment = get_comment(properties)

    return RoleMetadata(
        object_ref=ObjectRef(type="Role", name=name),
        name=name,
        synonym=synonym,
        comment=comment,
    )
