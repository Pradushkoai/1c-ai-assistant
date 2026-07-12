"""Утилиты для безопасного парсинга 1С XML файлов.

1С XML использует namespace `xmlns="http://v8.1c.ru/8.3/data/core"` и
`xmlns:v8="..."`, `xmlns:xs="..."`, `xmlns:cfg="..."`. Чтобы не усложнять
код явными namespace-префиксами, все функции поиска используют `local-name()`
и игнорируют namespace.

Использует lxml (быстрее и безопаснее, чем встроенный xml.etree).

См. ADR-0007 (Pydantic v2 — модели, в которые парсеры возвращают результат).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree

if TYPE_CHECKING:
    from lxml.etree import _Element as Element  # type: ignore[assignment]

    from parsers.models import Attribute, AttributeKind


# ─── Парсинг ────────────────────────────────────────────────────────────────


def parse_xml(path: Path) -> Element:
    """Безопасно распарсить XML файл.

    Args:
        path: путь к XML файлу.

    Returns:
        lxml Element — корневой элемент.

    Raises:
        FileNotFoundError: если файл не существует.
        etree.XMLSyntaxError: если XML повреждён.
    """
    if not path.exists():
        raise FileNotFoundError(f"XML file not found: {path}")
    # recover=True — игнорировать мелкие ошибки (например, незакрытые комментарии в синтаксисе 1С)
    # huge_tree=True — поддерживать большие файлы (Конфигурации 100+ МБ)
    parser = etree.XMLParser(recover=True, huge_tree=True, remove_blank_text=False)
    tree = etree.parse(str(path), parser=parser)
    return tree.getroot()  # type: ignore[no-any-return]


def parse_xml_string(xml_string: str) -> Element:
    """Распарсить XML из строки (для тестов)."""
    parser = etree.XMLParser(recover=True, huge_tree=True)
    root = etree.fromstring(xml_string.encode("utf-8"), parser=parser)
    return root  # type: ignore[no-any-return]


# ─── Helpers для namespace-agnostic поиска ──────────────────────────────────


def _xpath_path(path: str) -> str:
    """Преобразовать путь 'Properties/Name' в XPath с local-name().

    'Properties/Name' → './*[local-name()="Properties"]/*[local-name()="Name"]'
    """
    parts = path.split("/")
    xpath_parts = [f'*[local-name()="{p}"]' for p in parts if p]
    if not xpath_parts:
        return "."
    return "./" + "/".join(xpath_parts)


def _local_name(elem: Element) -> str:
    """Вернуть local-name элемента (без namespace).

    Работает с любой формой тега: 'Name', '{ns}Name', 'v8:Name'.
    Возвращает 'Name' во всех случаях.
    """
    tag = elem.tag if hasattr(elem, "tag") else None
    if tag is None:
        return ""
    if isinstance(tag, str):
        # {namespace}localname → localname
        if tag.startswith("{"):
            return tag.rsplit("}", 1)[-1]
        # prefix:localname → localname (нечастый случай)
        if ":" in tag:
            return tag.rsplit(":", 1)[-1]
        return tag
    return ""


# ─── Поиск элементов (namespace-agnostic) ───────────────────────────────────


def find_text(elem: Element, path: str, default: str | None = None) -> str | None:
    """Найти текст элемента по пути (namespace-agnostic).

    Args:
        elem: родительский элемент.
        path: путь (например, 'Properties/Name').
        default: значение по умолчанию, если элемент не найден.

    Returns:
        Текст элемента (stripped) или default.
    """
    found = elem.xpath(_xpath_path(path))
    if not found:
        return default
    element = found[0]
    if element.text is None:
        return default
    text = element.text.strip()
    return text if text else default


def find_all(elem: Element, path: str) -> list[Element]:
    """Найти все элементы по пути (namespace-agnostic)."""
    result = elem.xpath(_xpath_path(path))
    return list(result)  # type: ignore[arg-type]


def find_first(elem: Element, path: str) -> Element | None:
    """Найти первый элемент по пути (namespace-agnostic) или None."""
    found = elem.xpath(_xpath_path(path))
    if not found:
        return None
    return found[0]  # type: ignore[return-value]


def find_child(elem: Element, tag: str) -> Element | None:
    """Найти первый дочерний элемент с указанным local-name (без пути)."""
    for child in elem:
        if _local_name(child) == tag:
            return child
    return None


def find_all_children(elem: Element, tag: str) -> list[Element]:
    """Найти все дочерние элементы с указанным local-name."""
    return [child for child in elem if _local_name(child) == tag]


# ─── Извлечение типичных полей 1С ──────────────────────────────────────────


def get_synonym(properties_elem: Element) -> str | None:
    """Извлечь синоним из элемента Properties.

    Синоним в 1С XML имеет структуру:
        <Synonym>
          <v8:item>
            <v8:lang>ru</v8:lang>
            <v8:content>Управление торговлей</v8:content>
          </v8:item>
        </Synonym>

    Возвращает содержимое первого v8:item (обычно русский язык).
    """
    synonym_elem = find_child(properties_elem, "Synonym")
    if synonym_elem is None:
        return None

    # Ищем первый item → content (независимо от namespace)
    for item in synonym_elem.iter():
        if _local_name(item) == "content" and item.text:
            text = str(item.text.strip())
            if text:
                return text
    return None


def get_comment(properties_elem: Element) -> str | None:
    """Извлечь комментарий из Properties."""
    return find_text(properties_elem, "Comment")


def get_name(properties_elem: Element) -> str | None:
    """Извлечь имя из Properties."""
    return find_text(properties_elem, "Name")


def get_uuid(elem: Element) -> str | None:
    """Извлечь uuid атрибут элемента."""
    value = elem.get("uuid")
    return str(value) if value is not None else None


# ─── Извлечение атрибутов (реквизитов) ─────────────────────────────────────


def extract_type(properties_elem: Element) -> str:
    """Извлечь тип 1С из Properties реквизита.

    Тип в 1С XML имеет структуру:
        <Type>
          <v8:Type>xs:string</v8:Type>
          <v8:Type>cfg:CatalogRef.Контрагенты</v8:Type>
        </Type>

    Возвращает строковое представление:
    - 'Строка', 'Число', 'Дата', 'Булево' для примитивов
    - 'СправочникСсылка.Контрагенты' для ссылок

    Если типов несколько (union), возвращает первый.
    """
    type_elem = find_child(properties_elem, "Type")
    if type_elem is None:
        return "Неизвестно"

    # Ищем все элементы с local-name='Type' внутри (это v8:Type)
    types: list[str] = []
    for child in type_elem.iter():
        if _local_name(child) == "Type" and child.text:
            text = child.text.strip()
            if text:
                types.append(text)

    if not types:
        return "Неизвестно"

    first_type = types[0]

    # Конвертация xs: → русское имя для совместимости с моделями
    type_map = {
        "xs:string": "Строка",
        "xs:decimal": "Число",
        "xs:integer": "Число",
        "xs:byte": "Число",
        "xs:short": "Число",
        "xs:int": "Число",
        "xs:long": "Число",
        "xs:negativeInteger": "Число",
        "xs:nonNegativeInteger": "Число",
        "xs:positiveInteger": "Число",
        "xs:nonPositiveInteger": "Число",
        "xs:unsignedByte": "Число",
        "xs:unsignedShort": "Число",
        "xs:unsignedInt": "Число",
        "xs:unsignedLong": "Число",
        "xs:boolean": "Булево",
        "xs:dateTime": "Дата",
        "xs:date": "Дата",
        "xs:time": "Дата",
    }
    if first_type in type_map:
        return type_map[first_type]

    # cfg:CatalogRef.Контрагенты → СправочникСсылка.Контрагенты
    if first_type.startswith("cfg:"):
        ref_map = {
            "CatalogRef": "СправочникСсылка",
            "DocumentRef": "ДокументСсылка",
            "EnumRef": "ПеречислениеСсылка",
            "InformationRegisterRef": "РегистрСведенийСсылка",
            "AccumulationRegisterRef": "РегистрНакопленияСсылка",
            "AccountingRegisterRef": "РегистрБухгалтерииСсылка",
            "CalculationRegisterRef": "РегистрРасчетаСсылка",
            "ChartOfCharacteristicTypesRef": "ПланВидовХарактеристикСсылка",
            "ChartOfAccountsRef": "ПланСчетовСсылка",
            "ChartOfCalculationTypesRef": "ПланВидовРасчетаСсылка",
            "DataProcessorRef": "ОбработкаСсылка",
            "ReportRef": "ОтчетСсылка",
            "TaskRef": "ЗадачаСсылка",
            "BusinessProcessRef": "БизнесПроцессСсылка",
            "ExchangePlanRef": "ПланОбменаСсылка",
            "SequenceRef": "ПоследовательностьСсылка",
            "DocumentJournalRef": "ЖурналДокументовСсылка",
            "FilterCriterionRef": "КритерийОтбораСсылка",
            "DefinedType": "ОпределяемыйТип",
        }
        parts = first_type[4:].split(".", 1)
        if len(parts) == 2 and parts[0] in ref_map:
            return f"{ref_map[parts[0]]}.{parts[1]}"

    return first_type or "Неизвестно"


def extract_attribute(
    attr_elem: Element,
    kind: AttributeKind,
    tabular_section: str | None = None,
) -> Attribute | None:
    """Извлечь один атрибут из <Attribute> элемента.

    Args:
        attr_elem: lxml Element с тегом Attribute (с uuid атрибутом).
        kind: тип реквизита (Attribute | TabularSection | Standard).
        tabular_section: имя табличной части (если атрибут табличный).

    Returns:
        Attribute или None, если не удалось извлечь (например, нет Properties).
    """
    from parsers.models import Attribute

    properties = find_child(attr_elem, "Properties")
    if properties is None:
        return None

    name = get_name(properties)
    if not name:
        return None

    type_str = extract_type(properties)

    # FillChecking=Show означает required и check
    fill_checking = find_text(properties, "FillChecking", "DontCheck")
    required = fill_checking == "Show"

    return Attribute(
        name=name,
        type=type_str,
        kind=kind,
        tabular_section=tabular_section,
        required=required,
        check=required,
    )


def extract_attributes(
    parent_elem: Element,
) -> tuple[list[Attribute], list[str]]:
    """Извлечь все атрибуты объекта метаданных.

    Обрабатывает:
    - <ChildObjects><Attribute uuid="...">...</Attribute></ChildObjects>
      (обычные реквизиты шапки)
    - <ChildObjects><TabularSection uuid="..."><Properties><Name>...</Name></Properties>
      <ChildObjects><Attribute uuid="...">...</Attribute></ChildObjects></TabularSection></ChildObjects>
      (табличные части и их реквизиты)

    Args:
        parent_elem: элемент Catalog/Document/... (не Properties, не ChildObjects).

    Returns:
        Кортеж (атрибуты, имена табличных частей).
    """
    from parsers.models import AttributeKind

    attributes: list[Attribute] = []
    tabular_sections: list[str] = []

    child_objects = find_child(parent_elem, "ChildObjects")
    if child_objects is None:
        return attributes, tabular_sections

    # Сначала обычные атрибуты (в ChildObjects/Attribute)
    for attr_elem in find_all_children(child_objects, "Attribute"):
        attr = extract_attribute(attr_elem, AttributeKind.ATTRIBUTE)
        if attr is not None:
            attributes.append(attr)

    # Потом табличные части
    for ts_elem in find_all_children(child_objects, "TabularSection"):
        ts_properties = find_child(ts_elem, "Properties")
        if ts_properties is None:
            continue
        ts_name = get_name(ts_properties)
        if not ts_name:
            continue
        tabular_sections.append(ts_name)

        # Атрибуты табличной части
        ts_child_objects = find_child(ts_elem, "ChildObjects")
        if ts_child_objects is not None:
            for attr_elem in find_all_children(ts_child_objects, "Attribute"):
                attr = extract_attribute(attr_elem, AttributeKind.TABULAR_SECTION, tabular_section=ts_name)
                if attr is not None:
                    attributes.append(attr)

    return attributes, tabular_sections


# ─── Извлечение дочерних объектов (Forms, Templates, Commands) ─────────────


def extract_child_object_names(
    parent_elem: Element,
    child_tag: str,
) -> list[str]:
    """Извлечь имена дочерних объектов (Forms, Templates, Commands, ...).

    Дочерние объекты в 1С XML:
        <ChildObjects>
          <Form>ФормаСписка</Form>
          <Template>МакетПечати</Template>
          <Command>Команда1</Command>
        </ChildObjects>

    Текст элемента = имя объекта.

    Args:
        parent_elem: элемент Catalog/Document/... (не ChildObjects).
        child_tag: local-name тега дочернего объекта (Form, Template, Command, ...).

    Returns:
        Список имён дочерних объектов.
    """
    child_objects = find_child(parent_elem, "ChildObjects")
    if child_objects is None:
        return []

    names: list[str] = []
    for elem in find_all_children(child_objects, child_tag):
        if elem.text:
            name = elem.text.strip()
            if name:
                names.append(name)
    return names


def extract_child_object_refs(
    parent_elem: Element,
    child_type: str,
) -> list[str]:
    """Извлечь ссылки на дочерние объекты (Catalog, Document, ...).

    В Configuration.xml дочерние объекты:
        <ChildObjects>
          <Catalog>Товары</Catalog>
          <Document>Продажа</Document>
          <CommonModule>ОбщегоНазначения</CommonModule>
        </ChildObjects>

    Args:
        parent_elem: элемент Configuration (не ChildObjects).
        child_type: local-name тега (Catalog, Document, CommonModule, ...).

    Returns:
        Список имён объектов.
    """
    return extract_child_object_names(parent_elem, child_type)


# ─── Итерация по объектам метаданных ────────────────────────────────────────


def iter_metadata_files(config_dir: Path) -> Iterable[tuple[str, str, Path]]:
    """Итератор по XML файлам метаданных в распакованной конфигурации.

    Sprint 3.2 (исправлено 2026-07-12): .xml файлы лежат в корне {Type}s/,
    НЕ внутри подкаталогов. Имя файла = имя объекта.
    Например: Catalogs/Заметки.xml (а Catalogs/Заметки/ — поддиректория с формами).

    Yields:
        Кортежи (metadata_type, object_name, xml_path).
    """
    config_xml = config_dir / "Configuration.xml"
    if config_xml.exists():
        yield ("Configuration", "Configuration", config_xml)

    type_dirs = {
        "Catalogs": "Catalog",
        "Documents": "Document",
        "CommonModules": "CommonModule",
        "Enums": "Enum",
        "InformationRegisters": "InformationRegister",
        "AccumulationRegisters": "AccumulationRegister",
        "ChartsOfCharacteristicTypes": "ChartOfCharacteristicTypes",
        "ChartsOfAccounts": "ChartOfAccounts",
        "ChartsOfCalculationTypes": "ChartOfCalculationTypes",
        "DataProcessors": "DataProcessor",
        "Reports": "Report",
        "Subsystems": "Subsystem",
        "Roles": "Role",
        "CommonForms": "CommonForm",
        "CommonTemplates": "CommonTemplate",
        "CommonCommands": "CommonCommand",
        "CommonAttributes": "CommonAttribute",
        "DefinedTypes": "DefinedType",
        "ExchangePlans": "ExchangePlan",
        "FilterCriteria": "FilterCriterion",
        "FunctionalOptions": "FunctionalOption",
        "FunctionalOptionsParameters": "FunctionalOptionsParameter",
        "SettingsStorages": "SettingsStorage",
        "HTTPServices": "HttpService",
        "WebServices": "WebService",
        "WSReferences": "WSReference",
        "XDTOPackages": "XDTOPackage",
        "BusinessProcesses": "BusinessProcess",
        "Tasks": "Task",
        "Sequences": "Sequence",
        "DocumentJournals": "DocumentJournal",
        "DocumentNumerators": "DocumentNumerator",
        "Constants": "Constant",
        "EventSubscriptions": "EventSubscription",
        "ScheduledJobs": "ScheduledJob",
        "Languages": "Language",
        "SessionParameters": "SessionParameter",
        "StyleItems": "StyleItem",
        "Styles": "Style",
        "CommandGroups": "CommandGroup",
        "CommonPictures": "CommonPicture",
    }

    for dir_name, metadata_type in type_dirs.items():
        type_dir = config_dir / dir_name
        if not type_dir.exists():
            continue
        for xml_file in type_dir.glob("*.xml"):
            object_name = xml_file.stem
            yield (metadata_type, object_name, xml_file)
