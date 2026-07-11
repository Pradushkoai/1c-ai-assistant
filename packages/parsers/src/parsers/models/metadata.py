"""Метаданные 1С из XML-выгрузки.

Соответствие типов объектов 1С и моделей:
    Configuration.xml    → ConfigMeta (см. config.py)
    Catalog.xml          → CatalogMetadata
    Document.xml         → DocumentMetadata
    CommonModule.xml     → CommonModuleMetadata
    Form.xml             → FormMetadata
    InformationRegister.xml → (TODO: Спринт 4)
    AccumulationRegister.xml → (TODO: Спринт 4)
    ...
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .common import ModelConfig, ObjectRef


class MetadataType(StrEnum):
    """Типы объектов метаданных 1С.

    Полный список типов (35 в платформе 8.3.20+). Здесь перечислены основные,
    остальные добавляются по мере реализации парсеров.
    """

    CONFIGURATION = "Configuration"
    CATALOG = "Catalog"
    DOCUMENT = "Document"
    ENUM = "Enum"
    INFORMATION_REGISTER = "InformationRegister"
    ACCUMULATION_REGISTER = "AccumulationRegister"
    COMMON_MODULE = "CommonModule"
    COMMON_FORM = "CommonForm"
    COMMON_TEMPLATE = "CommonTemplate"
    COMMON_COMMAND = "CommonCommand"
    DATA_PROCESSOR = "DataProcessor"
    REPORT = "Report"
    CHART_OF_CHARACTERISTIC_TYPES = "ChartOfCharacteristicTypes"
    CHART_OF_ACCOUNTS = "ChartOfAccounts"
    CHART_OF_CALCULATION_TYPES = "ChartOfCalculationTypes"
    ACCOUNTING_REGISTER = "AccountingRegister"
    CALCULATION_REGISTER = "CalculationRegister"
    FILTER_CRITERION = "FilterCriterion"
    BUSINESS_PROCESS = "BusinessProcess"
    TASK = "Task"
    EXCHANGE_PLAN = "ExchangePlan"
    SEQUENCE = "Sequence"
    DOCUMENT_JOURNAL = "DocumentJournal"
    SUBSYSTEM = "Subsystem"
    STYLE = "Style"
    LANGUAGE = "Language"
    ROLE = "Role"
    FUNCTIONAL_OPTION = "FunctionalOption"
    FUNCTIONAL_OPTIONS_PARAMETER = "FunctionalOptionsParameter"
    DEFINED_TYPE = "DefinedType"
    SETTINGS_STORAGE = "SettingsStorage"
    HTTP_SERVICE = "HttpService"
    WEB_SERVICE = "WebService"
    WS_REFERENCE = "WSReference"
    XDTO_PACKAGE = "XDTOPackage"


class AttributeKind(StrEnum):
    """Тип реквизита объекта метаданных."""

    ATTRIBUTE = "Attribute"  # Обычный реквизит
    TABULAR_SECTION = "TabularSection"  # Табличная часть
    STANDARD = "Standard"  # Стандартный реквизит (Ref, Code, Description, ...)


class Attribute(ModelConfig):
    """Реквизит объекта метаданных.

    Реквизиты бывают:
    - обычные (в шапке объекта)
    - табличные (в табличных частях)
    - стандартные (Code, Description, ...)

    Attributes:
        name: имя реквизита.
        type: тип 1С ('Строка', 'СправочникСсылка.Контрагенты', 'Число', ...).
        kind: тип реквизита (Attribute | TabularSection | Standard).
        tabular_section: имя табличной части (если реквизит табличный).
        required: True если обязательный (FillChecking=Show).
        check: True если проверка заполнения (FillChecking=Show).
    """

    name: str = Field(description="Имя реквизита")
    type: str = Field(
        description="Тип 1С: 'Строка', 'СправочникСсылка.Контрагенты', 'Число', ...",
    )
    kind: AttributeKind = Field(
        default=AttributeKind.ATTRIBUTE,
        description="Тип реквизита",
    )
    tabular_section: str | None = Field(
        default=None,
        description="Имя табличной части (для табличных реквизитов)",
    )
    required: bool = Field(
        default=False,
        description="True если обязательный (FillChecking=Show)",
    )
    check: bool = Field(
        default=False,
        description="True если проверка заполнения (FillChecking=Show)",
    )


class ObjectMetadata(ModelConfig):
    """Базовая модель метаданных объекта 1С.

    Расширяется конкретными типами (CatalogMetadata, DocumentMetadata, ...).

    Attributes:
        object_ref: ссылка на объект (Catalog.Товары, Document.Продажа, ...).
        metadata_type: тип метаданных (Catalog, Document, ...).
        name: имя объекта.
        synonym: синоним (отображаемое имя).
        comment: комментарий разработчика.
        attributes: реквизиты объекта.
        forms: имена форм.
        templates: имена шаблонов.
        commands: имена команд.
    """

    object_ref: ObjectRef
    metadata_type: MetadataType
    name: str = Field(description="Имя объекта")
    synonym: str | None = Field(default=None, description="Синоним (отображаемое имя)")
    comment: str | None = Field(default=None, description="Комментарий")
    attributes: list[Attribute] = Field(default_factory=list)
    forms: list[str] = Field(default_factory=list, description="Имена форм")
    templates: list[str] = Field(default_factory=list, description="Имена шаблонов")
    commands: list[str] = Field(default_factory=list, description="Имена команд")


class CatalogMetadata(ObjectMetadata):
    """Метаданные справочника.

    Соответствует Catalog.xml.
    """

    metadata_type: MetadataType = MetadataType.CATALOG
    hierarchy_type: str = Field(
        default="HierarchyItems",
        description="Тип иерархии: HierarchyItems | HierarchyOfItems | HierarchyOfFolders",
    )
    owners: list[str] = Field(
        default_factory=list,
        description="Владельцы справочника (CatalogRef.Контрагенты, ...)",
    )
    predefined: list[str] = Field(
        default_factory=list,
        description="Имена предопределенных элементов",
    )
    code_length: int = Field(default=9, ge=0, description="Длина кода")
    code_series: str = Field(
        default="WholeCatalog",
        description="Серия кодов: WholeCatalog | WithinSubordination | WithinSubordinationFolder",
    )
    description_length: int = Field(default=50, ge=0, description="Длина наименования")


class DocumentMetadata(ObjectMetadata):
    """Метаданные документа.

    Соответствует Document.xml.

    Attributes:
        number_length: длина номера.
        number_type: тип номера (String | Number).
        register_records: имена регистров, по которым документ делает движения.
        posting: режим проведения (Allow | Deny).
        realtime_posting: режим реального времени (Allow | Deny).
    """

    metadata_type: MetadataType = MetadataType.DOCUMENT
    number_length: int = Field(default=9, ge=0, description="Длина номера")
    number_type: str = Field(default="String", description="Тип номера: String | Number")
    register_records: list[str] = Field(
        default_factory=list,
        description="Имена регистров, по которым документ делает движения",
    )
    posting: str = Field(
        default="Allow",
        description="Режим проведения: Allow | Deny",
    )
    realtime_posting: str = Field(
        default="Deny",
        description="Проведение в реальном времени: Allow | Deny",
    )


class CommonModuleMetadata(ObjectMetadata):
    """Метаданные общего модуля.

    Соответствует CommonModule.xml.

    Флаги контекста определяют, где выполняется модуль:
    - server: на сервере
    - global: глобальный (доступен без префикса)
    - client: на клиенте
    - client_managed_application: в управляемом приложении
    - external_connection: во внешнем соединении
    - privileged: привилегированный
    """

    metadata_type: MetadataType = MetadataType.COMMON_MODULE
    server: bool = Field(default=True, description="Выполняется на сервере")
    global_: bool = Field(
        default=False,
        description="Глобальный (доступен без префикса)",
        alias="global",
    )
    client: bool = Field(default=False, description="Выполняется на клиенте")
    client_managed_application: bool = Field(
        default=False,
        description="Выполняется в управляемом приложении (клиент)",
    )
    external_connection: bool = Field(
        default=False,
        description="Выполняется во внешнем соединении",
    )
    privileged: bool = Field(
        default=False,
        description="Привилегированный модуль (без проверки прав)",
    )


class FormElement(ModelConfig):
    """Элемент управляемой формы.

    Формы имеют древовидную структуру — элементы могут содержать дочерние
    элементы (например, группа с кнопками).
    """

    name: str = Field(description="Имя элемента формы")
    type: str = Field(
        description="Тип элемента: Button | InputField | Table | Group | Label | ...",
    )
    data_path: str | None = Field(
        default=None,
        description="Путь к данным (например, 'Объект.Наименование')",
    )
    title: str | None = Field(default=None, description="Заголовок элемента")
    visible: bool = Field(default=True, description="Видимость элемента")
    enabled: bool = Field(default=True, description="Доступность элемента")
    children: list[FormElement] = Field(
        default_factory=list,
        description="Дочерние элементы (для групп)",
    )


class FormMetadata(ModelConfig):
    """Метаданные управляемой формы.

    Соответствует Form.xml.
    """

    object_ref: ObjectRef
    form_name: str = Field(
        description="Имя формы: ФормаСписка, ФормаЭлемента, ФормаВыбора, ...",
    )
    title: str | None = Field(default=None, description="Заголовок формы")
    use_for_filling: bool = Field(
        default=False,
        description="Используется для заполнения",
    )
    use_for_opening: bool = Field(
        default=False,
        description="Используется для открытия по умолчанию",
    )
    elements: list[FormElement] = Field(
        default_factory=list,
        description="Дерево элементов формы",
    )
    attributes: list[Attribute] = Field(
        default_factory=list,
        description="Реквизиты формы (включая ОсновнаяФорма)",
    )
    handlers: dict[str, str] = Field(
        default_factory=dict,
        description="Событие → имя обработчика (например, 'ПриОткрытии': 'ПриОткрытии')",
    )


# Forward reference для FormElement.children (рекурсивный тип)
FormElement.model_rebuild()
