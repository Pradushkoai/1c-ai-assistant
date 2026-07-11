"""Парсер Document.xml — документ 1С.

Возвращает DocumentMetadata (см. parsers.models.metadata).
"""

from __future__ import annotations

from pathlib import Path

from parsers.models import DocumentMetadata, MetadataType, ObjectRef

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


def parse_document(xml_path: Path) -> DocumentMetadata:
    """Распарсить Document.xml → DocumentMetadata.

    Args:
        xml_path: путь к Document.xml.

    Returns:
        DocumentMetadata.

    Raises:
        FileNotFoundError: если файл не существует.
        ValueError: если XML не содержит <Document>.

    Examples:
        >>> from pathlib import Path
        >>> from parsers.xml import parse_document
        >>> doc = parse_document(Path("data/configs/ut11/4.5.3/Documents/Продажа/Продажа.xml"))
        >>> doc.name
        'Продажа'
        >>> doc.register_records
        ['AccumulationRegister.Продажи']
    """
    root = parse_xml(xml_path)

    document_elem = find_child(root, "Document")
    if document_elem is None:
        from ._xml_utils import _local_name

        raise ValueError(f"Document.xml: expected <Document> element, got <{_local_name(root)}>")

    properties = find_child(document_elem, "Properties")
    if properties is None:
        raise ValueError("Document.xml: missing <Properties> element")

    name = get_name(properties) or xml_path.parent.name
    synonym = get_synonym(properties)
    comment = get_comment(properties)

    number_length_str = find_text(properties, "NumberLength", "9")
    try:
        number_length = int(number_length_str or "9")
    except ValueError:
        number_length = 9

    number_type = find_text(properties, "NumberType", "String") or "String"
    posting = find_text(properties, "Posting", "Allow") or "Allow"
    realtime_posting = find_text(properties, "RealTimePosting", "Deny") or "Deny"

    # RegisterRecords (регистры, по которым документ делает движения)
    # Структура:
    # <RegisterRecords>
    #   <xr:Item>AccumulationRegister.Продажи</xr:Item>
    #   <xr:Item>InformationRegister.КурсыВалют</xr:Item>
    # </RegisterRecords>
    register_records: list[str] = []
    rr_elem = find_child(properties, "RegisterRecords")
    if rr_elem is not None:
        # Ищем все дочерние элементы с local-name='Item'
        from ._xml_utils import _local_name

        for item in rr_elem.iter():
            if _local_name(item) == "Item" and item.text:
                text = item.text.strip()
                if text:
                    register_records.append(text)

    # Атрибуты (обычные + табличные)
    attributes, _tabular_sections = extract_attributes(document_elem)

    # Forms, Templates, Commands
    forms = extract_child_object_names(document_elem, "Form")
    templates = extract_child_object_names(document_elem, "Template")
    commands = extract_child_object_names(document_elem, "Command")

    return DocumentMetadata(
        object_ref=ObjectRef(type="Document", name=name),
        metadata_type=MetadataType.DOCUMENT,
        name=name,
        synonym=synonym,
        comment=comment,
        attributes=attributes,
        forms=forms,
        templates=templates,
        commands=commands,
        number_length=number_length,
        number_type=number_type,
        register_records=register_records,
        posting=posting,
        realtime_posting=realtime_posting,
    )
