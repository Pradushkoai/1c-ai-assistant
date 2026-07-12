"""Парсер Form.xml → FormMetadata.

Разбирает 2 файла:
1. Wrapper: Catalogs/Товары/Forms/ФормаСписка.xml — имя, синоним, тип формы
2. Structure: Catalogs/Товары/Forms/ФормаСписка/Ext/Form.xml — элементы, события, заголовок

Sprint 4.1 (TD-S4.1-01): Form/Subsystem/Role парсеры для metadata MCP.
Coder получает структуру формы: элементы, обработчики событий, реквизиты.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from parsers.models import Attribute, FormElement, FormMetadata, ObjectRef
from parsers.xml._xml_utils import (
    _local_name,
    find_child,
    find_text,
    get_name,
    get_synonym,
    parse_xml,
)

log = logging.getLogger(__name__)


def parse_form(wrapper_xml_path: Path) -> FormMetadata:
    """Распарсить форму метаданных 1С.

    Args:
        wrapper_xml_path: путь к wrapper XML (например, Forms/ФормаСписка.xml).

    Returns:
        FormMetadata с именем, синонимом, элементами и обработчиками.
        Если Ext/Form.xml существует — элементы и события тоже заполнены.

    Examples:
        >>> from pathlib import Path
        >>> form = parse_form(Path("Catalogs/Товары/Forms/ФормаСписка.xml"))
        >>> form.form_name
        'ФормаСписка'
        >>> form.title
        'Форма списка'
    """
    root = parse_xml(wrapper_xml_path)

    # Находим <Form> внутри <MetaDataObject>
    form_elem = find_child(root, "Form")
    if form_elem is None:
        if _local_name(root) == "Form":
            form_elem = root
        else:
            raise ValueError(f"Expected <Form> in {wrapper_xml_path}")

    properties = find_child(form_elem, "Properties")
    if properties is None:
        raise ValueError(f"No <Properties> in form {wrapper_xml_path}")

    name = get_name(properties) or wrapper_xml_path.stem
    synonym = get_synonym(properties)

    # Формируем ObjectRef — родительский объект из пути
    # Например: Catalogs/Товары/Forms/ФормаСписка.xml → Catalog.Товары
    parent_type, parent_name = _guess_parent_from_path(wrapper_xml_path)

    form_metadata = FormMetadata(
        object_ref=ObjectRef(type=parent_type, name=parent_name),
        form_name=name,
        title=synonym,
    )

    # Пытаемся найти и распарсить Ext/Form.xml
    ext_form_path = wrapper_xml_path.parent / name / "Ext" / "Form.xml"
    if ext_form_path.exists():
        form_metadata = _parse_ext_form(ext_form_path, form_metadata)
    else:
        log.debug("No Ext/Form.xml for form %s (looked at %s)", name, ext_form_path)

    return form_metadata


def _guess_parent_from_path(path: Path) -> tuple[str, str]:
    """Определить тип и имя родительского объекта из пути.

    Примеры:
        Catalogs/Товары/Forms/ФормаСписка.xml → ("Catalog", "Товары")
        Documents/Продажа/Forms/ФормаДокумента.xml → ("Document", "Продажа")
        CommonForms/МояФорма.xml → ("CommonForm", "МояФорма")
    """
    parts = path.parts
    # Находим предпоследний элемент перед "Forms"
    for i, part in enumerate(parts):
        if part == "Forms" and i > 0:
            parent_dir = parts[i - 1]
            # Тип: Catalogs → Catalog, Documents → Document, etc.
            type_map = {
                "Catalogs": "Catalog",
                "Documents": "Document",
                "CommonForms": "CommonForm",
                "DataProcessors": "DataProcessor",
                "Reports": "Report",
                "ChartsOfCharacteristicTypes": "ChartOfCharacteristicTypes",
                "InformationRegisters": "InformationRegister",
                "AccumulationRegisters": "AccumulationRegister",
                "BusinessProcesses": "BusinessProcess",
                "Tasks": "Task",
                "ExchangePlans": "ExchangePlan",
            }
            # parts[i-2] — это тип директории (Catalogs, Documents, etc.)
            if i >= 2:
                type_dir = parts[i - 2]
                parent_type = type_map.get(type_dir, "CommonForm")
            else:
                parent_type = "CommonForm"
            return (parent_type, parent_dir)

    # CommonForms: нет поддиректории с типом
    if "CommonForms" in parts:
        idx = parts.index("CommonForms")
        if idx + 1 < len(parts):
            # Имя файла с .xml — убираем расширение
            form_file = parts[idx + 1]
            form_name = form_file.rsplit(".", 1)[0] if "." in form_file else form_file
            return ("CommonForm", form_name)

    return ("Unknown", "Unknown")


def _parse_ext_form(ext_form_path: Path, form_metadata: FormMetadata) -> FormMetadata:
    """Дополнить FormMetadata данными из Ext/Form.xml.

    Возвращает НОВЫЙ FormMetadata (frozen model — model_copy).
    """
    try:
        root = parse_xml(ext_form_path)
    except Exception as exc:
        log.warning("Failed to parse Ext/Form.xml %s: %s", ext_form_path, exc)
        return form_metadata

    title: str | None = form_metadata.title
    handlers: dict[str, str] = dict(form_metadata.handlers)
    attributes: list[Attribute] = list(form_metadata.attributes)
    elements: list[FormElement] = list(form_metadata.elements)

    # Title — может отличаться от synonym
    title_elem = find_child(root, "Title")
    if title_elem is not None:
        extracted = _extract_v8_content(title_elem)
        if extracted:
            title = extracted

    # Events → handlers dict
    events_elem = find_child(root, "Events")
    if events_elem is not None:
        for event_elem in events_elem:
            if _local_name(event_elem) == "Event":
                event_name = event_elem.get("name", "")
                handler = event_elem.text or ""
                if event_name and handler:
                    handlers[event_name] = handler.strip()

    # Attributes (реквизиты формы)
    attrs_elem = find_child(root, "Attributes")
    if attrs_elem is not None:
        for attr_elem in attrs_elem:
            if _local_name(attr_elem) == "Attribute":
                attr = _parse_form_attribute(attr_elem)
                if attr is not None:
                    attributes.append(attr)

    # ChildItems — дерево элементов формы
    child_items_elem = find_child(root, "ChildItems")
    if child_items_elem is not None:
        for elem in child_items_elem:
            form_element = _parse_form_element(elem, depth=0, max_depth=2)
            if form_element is not None:
                elements.append(form_element)

    return form_metadata.model_copy(update={
        "title": title,
        "handlers": handlers,
        "attributes": attributes,
        "elements": elements,
    })


def _parse_form_element(
    elem: Any,
    depth: int = 0,
    max_depth: int = 2,
) -> FormElement | None:
    """Рекурсивно распарсить элемент формы.

    Args:
        elem: lxml Element из ChildItems.
        depth: текущая глубина рекурсии.
        max_depth: максимальная глубина (2 = элементы + их дочерние).

    Returns:
        FormElement или None.
    """
    tag = _local_name(elem)
    if not tag:
        return None

    # name атрибут
    name = elem.get("name", "") or tag
    # id атрибут (для диагностики)
    # elem_id = elem.get("id", "")

    # DataPath
    data_path = find_text(elem, "DataPath")

    # Title
    title_elem = find_child(elem, "Title")
    title = _extract_v8_content(title_elem) if title_elem is not None else None

    # Visible / Enabled (по умолчанию True)
    visible = True
    enabled = True
    vis_elem = find_child(elem, "Visible")
    if vis_elem is not None and vis_elem.text:
        visible = vis_elem.text.lower() in ("true", "истина")
    en_elem = find_child(elem, "Enabled")
    if en_elem is not None and en_elem.text:
        enabled = en_elem.text.lower() in ("true", "истина")

    # Children — рекурсивно
    children: list[FormElement] = []
    if depth < max_depth:
        child_items = find_child(elem, "ChildItems")
        if child_items is not None:
            for child_elem in child_items:
                child = _parse_form_element(child_elem, depth + 1, max_depth)
                if child is not None:
                    children.append(child)

    return FormElement(
        name=name,
        type=tag,
        data_path=data_path,
        title=title,
        visible=visible,
        enabled=enabled,
        children=children,
    )


def _parse_form_attribute(attr_elem: Any) -> Attribute | None:
    """Распарсить реквизит формы.

    Form attributes are different from object attributes — they are
    form-specific (e.g., "Объект" for the main object, custom form params).
    """
    name = attr_elem.get("name", "") or ""
    if not name:
        name_elem = find_child(attr_elem, "Name")
        if name_elem is not None and name_elem.text:
            name = name_elem.text

    if not name:
        return None

    # Type
    type_elem = find_child(attr_elem, "Type")
    attr_type = ""
    if type_elem is not None:
        # Type может быть сложным (v8:Type)
        type_text = type_elem.text or ""
        if type_text:
            attr_type = type_text
        else:
            # Ищем вложенный элемент типа
            for child in type_elem:
                tag = _local_name(child)
                if tag:
                    attr_type = tag
                    break

    return Attribute(
        name=name,
        type=attr_type or "Unknown",
    )


def _extract_v8_content(elem: Any) -> str | None:
    """Извлечь текст из элемента с v8:item/v8:content структурой."""
    # Прямой текст
    if elem.text and elem.text.strip():
        return elem.text.strip()

    # v8:item/v8:content — обходим детей по _local_name
    for item in elem:
        if _local_name(item) == "item":
            for sub in item:
                if _local_name(sub) == "content" and sub.text:
                    return sub.text.strip()

    return None
