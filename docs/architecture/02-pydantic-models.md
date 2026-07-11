# Шаг 2 — Общие Pydantic-модели (`parsers/models/`)

> **ADR-0007:** Pydantic v2 frozen models как клей проекта
> **Зависимости:** Шаг 1 (структура пакетов)
> **Артефакт:** `packages/parsers/src/parsers/models/*.py` с моделями + JSON Schema

## 1. Почему это второй шаг

`parsers/models/` — **самый нижний слой контрактов**. От него зависят:

- `parsers/xml/` — возвращает эти модели
- `parsers/bsl/` — возвращает эти модели
- `parsers/hbk/` — возвращает эти модели
- `mcp_servers/metadata/` — отдаёт модели через MCP
- `mcp_servers/codebase/` — отдаёт модели через MCP
- `mcp_servers/kb/` — `PlatformMethod` для `check_method_availability`
- `orchestrator/state.py` — `Iteration` содержит `BslModule`
- `orchestrator/contracts.py` — `GatherResult` содержит метаданные

Любая ошибка здесь будет эхом отдаваться во всём проекте. Поэтому модели фиксируются **до** контрактов pipeline и MCP.

## 2. Принципы

### 2.1. Pydantic v2, не dataclass

Pydantic v2 даёт:
- валидацию из коробки (типы, обязательность, диапазоны)
- `model_dump()` / `model_validate()` для (де)сериализации
- `model_json_schema()` для JSON Schema (нужно для MCP `inputSchema`)
- `model_config = {"frozen": True}` для иммутабельности
- интеграцию с LangChain `with_structured_output()`

Dataclasses дешевле, но не дают валидацию и JSON Schema. Для контрактов это критично.

### 2.2. Frozen по умолчанию

Все модели в `parsers/models/` — `frozen=True`. Это соответствует принципу иммутабельности state в LangGraph (Шаг 4). Если кому-то нужна мутабельная модель — это явный red flag, требует ADR.

### 2.3. Strict по умолчанию, extra=forbid

`model_config = ConfigDict(frozen=True, extra="forbid", strict=True)` —禁止 лишние поля. Это ловит опечатки в полях на этапе парсинга, а не в рантайме pipeline.

Исключения — явно задокументированы (`extra="allow"` для forward-compat с будущими версиями 1С XML).

### 2.4. JSON Schema export

Каждая модель должна уметь экспортировать JSON Schema:

```python
from parsers.models.module import BslModule
schema = BslModule.model_json_schema()
```

Это используется:
- MCP-серверами для `inputSchema` tool definitions (Шаг 5)
- `with_structured_output()` в LangChain (Шаг 4)
- snapshot-тестами контрактов

## 3. Каталог моделей

```
packages/parsers/src/parsers/models/
├── __init__.py              ← re-export всех моделей
├── common.py                ← базовые типы (ObjectRef, Version, ContextAvailability)
├── metadata.py              ← метаданные 1С (CatalogMeta, DocumentMeta, FormMeta, ...)
├── module.py                ← BSL-модули (BslModule, Method, Region)
├── method.py                ← методы платформы (PlatformMethod, ContextAvailability)
├── config.py                ← конфигурация (ConfigMeta, VersionInfo)
└── graph.py                 ← графы (DependencyEdge, CallEdge, GraphStats)
```

## 4. Модели — детали

### 4.1. `common.py` — базовые типы

```python
"""Базовые типы, общие для всех моделей."""
from __future__ import annotations

from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ModelConfig(BaseModel):
    """Базовый конфиг для всех моделей проекта."""
    model_config = ConfigDict(
        frozen=True,        # иммутабельность
        extra="forbid",     # лишние поля → ошибка
        strict=True,        # строгая типизация
        populate_by_name=True,  # alias → field name
    )


class ObjectRef(ModelConfig):
    """Ссылка на объект метаданных 1С.

    Формат: 'Catalog.Контрагенты', 'Document.Реализация', 'CommonModule.ОбщегоНазначения'.
    """
    type: str = Field(description="Тип объекта: Catalog, Document, CommonModule, ...")
    name: str = Field(description="Имя объекта на русском")

    @classmethod
    def from_string(cls, ref: str) -> "ObjectRef":
        """Парсинг 'Catalog.Контрагенты' → ObjectRef(type='Catalog', name='Контрагенты')."""
        if "." not in ref:
            raise ValueError(f"Invalid ObjectRef: {ref!r}, expected 'Type.Name'")
        type_, name = ref.split(".", 1)
        return cls(type=type_, name=name)

    def __str__(self) -> str:
        return f"{self.type}.{self.name}"


class Version(ModelConfig):
    """Версия 1С: '8.3.20', '8.3.21.62'."""
    major: int
    minor: int
    patch: int
    build: int | None = None

    @classmethod
    def from_string(cls, version: str) -> "Version":
        parts = version.split(".")
        if len(parts) < 3:
            raise ValueError(f"Invalid version: {version!r}")
        return cls(
            major=int(parts[0]),
            minor=int(parts[1]),
            patch=int(parts[2]),
            build=int(parts[3]) if len(parts) > 3 else None,
        )

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        return f"{s}.{self.build}" if self.build else s


class ExecutionEnvironment(str, Enum):
    """Контекст выполнения BSL-кода."""
    SERVER = "server"
    THIN_CLIENT = "thin_client"
    WEB_CLIENT = "web_client"
    MOBILE_CLIENT = "mobile_client"
    RICH_CLIENT = "rich_client"
    EXTERNAL_CONNECTION = "external_connection"
    MOBILE_APPLICATION = "mobile_application"
    MOBILE_CLIENT_APPLICATION = "mobile_client_application"
    UNKNOWN = "unknown"


class ContextAvailability(ModelConfig):
    """Доступность метода платформы в контекстах.

    Источник: .hbk файлы синтакс-помощника.
    Используется kb.check_method_availability.
    """
    server: bool = True
    thin_client: bool = True
    web_client: bool = True
    mobile_client: bool = False
    rich_client: bool = True
    external_connection: bool = True
    mobile_application: bool = False
    mobile_client_application: bool = False

    def available_in(self, env: ExecutionEnvironment) -> bool:
        """Проверка доступности в конкретном контексте."""
        return getattr(self, env.value, False)
```

### 4.2. `module.py` — BSL-модули

```python
"""Модели BSL-модулей 1С."""
from __future__ import annotations

from pydantic import Field
from .common import ModelConfig, ObjectRef, ExecutionEnvironment


class Region(ModelConfig):
    """Область BSL-модуля (#Область ... #КонецОбласти)."""
    name: str = Field(description="Имя области, например 'ПрограммныйИнтерфейс'")
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    parent: str | None = Field(default=None, description="Имя родительской области")
    methods: list[str] = Field(default_factory=list, description="Имена методов внутри области")


class MethodParameter(ModelConfig):
    """Параметр метода BSL."""
    name: str
    by_value: bool = Field(default=False, description="Знач или нет")
    default_value: str | None = None
    has_default: bool = False


class Method(ModelConfig):
    """Метод BSL-модуля."""
    name: str
    is_export: bool = False
    is_async: bool = False
    is_procedure: bool = Field(description="True = процедура, False = функция")
    parameters: list[MethodParameter] = Field(default_factory=list)
    return_type_hint: str | None = None
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    region: str | None = None
    docstring: str | None = None
    cyclomatic_complexity: int | None = Field(default=None, ge=0)


class BslModule(ModelConfig):
    """BSL-модуль целиком.

    Один .bsl файл = один BslModule.
    Соответствует ObjectModule.bsl, ManagerModule.bsl, Form/Module.bsl, CommonModule.bsl, ...
    """
    object_ref: ObjectRef = Field(description="Catalog.Контрагенты, Document.Реализация, ...")
    module_kind: str = Field(description="ObjectModule | ManagerModule | FormModule | CommonModule | CommandModule")
    source: str = Field(description="Полный исходный код .bsl")
    methods: list[Method] = Field(default_factory=list)
    regions: list[Region] = Field(default_factory=list)
    line_count: int = Field(ge=0)
    encoding: str = "utf-8"
    # Опциональные — заполняются при наличии tree-sitter
    imports: list[str] = Field(default_factory=list, description="Используемые модули (из '#Использовать' или анализа)")
    call_targets: list[str] = Field(default_factory=list, description="Имена вызываемых методов")
    parse_warnings: list[str] = Field(default_factory=list, description="Предупреждения парсера (regex fallback и т.д.)")
```

### 4.3. `metadata.py` — метаданные 1С

```python
"""Метаданные 1С из XML-выгрузки."""
from __future__ import annotations

from enum import Enum
from pydantic import Field
from .common import ModelConfig, ObjectRef


class MetadataType(str, Enum):
    """Типы объектов метаданных 1С (35 типов)."""
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
    XDTOPACKAGE = "XDTOPackage"


class Attribute(ModelConfig):
    """Реквизит объекта метаданных."""
    name: str
    type: str = Field(description="Тип 1С: 'Строка', 'СправочникСсылка.Контрагенты', ...")
    kind: str = Field(description="Attribute | TabularSection | Standard")
    tabular_section: str | None = None
    required: bool = False
    check: bool = False  # Проверка заполнения


class ObjectMetadata(ModelConfig):
    """Базовая модель метаданных объекта 1С.

    Расширяется конкретными типами (CatalogMeta, DocumentMeta, ...).
    """
    object_ref: ObjectRef
    metadata_type: MetadataType
    name: str = Field(description="Синоним или имя")
    synonym: str | None = None
    comment: str | None = None
    attributes: list[Attribute] = Field(default_factory=list)
    forms: list[str] = Field(default_factory=list, description="Имена форм")
    templates: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    # Расширения для конкретных типов — в подклассах


class CatalogMetadata(ObjectMetadata):
    """Метаданные справочника."""
    metadata_type: MetadataType = MetadataType.CATALOG
    hierarchy_type: str = Field(default="HierarchicalItems", description="HierarchicalItems | HierarchyOfItems | HierarchyOfFolders")
    owners: list[str] = Field(default_factory=list)
    predefined: list[str] = Field(default_factory=list)
    code_length: int = Field(default=9, ge=0)
    code_series: str = Field(default="WholeSeries", description="WholeSeries | WithinSubordination")
    description_length: int = Field(default=25, ge=0)


class DocumentMetadata(ObjectMetadata):
    """Метаданные документа."""
    metadata_type: MetadataType = MetadataType.DOCUMENT
    number_length: int = Field(default=9, ge=0)
    number_type: str = "Number"
    register_records: list[str] = Field(default_factory=list, description="Имена регистров, по которым документ делает движения")
    posting: str = Field(default="Allow", description="Allow | Deny")
    realtime_posting: str = "Deny"


class CommonModuleMetadata(ObjectMetadata):
    """Метаданные общего модуля."""
    metadata_type: MetadataType = MetadataType.COMMON_MODULE
    server: bool = True
    global: bool = False
    client: bool = False
    client_managed_application: bool = False
    external_connection: bool = False
    privileged: bool = False


class FormElement(ModelConfig):
    """Элемент управляемой формы."""
    name: str
    type: str = Field(description="Button | InputField | Table | Group | Label | ...")
    data_path: str | None = None
    title: str | None = None
    visible: bool = True
    enabled: bool = True
    children: list["FormElement"] = Field(default_factory=list)


class FormMetadata(ModelConfig):
    """Метаданные управляемой формы."""
    object_ref: ObjectRef
    form_name: str = Field(description="Имя формы: ФормаСписка, ФормаЭлемента, ...")
    title: str | None = None
    use_for_filling: bool = False
    use_for_opening: bool = False
    elements: list[FormElement] = Field(default_factory=list)
    attributes: list[Attribute] = Field(default_factory=list, description="Реквизиты формы")
    handlers: dict[str, str] = Field(default_factory=dict, description="Событие → имя обработчика")


FormElement.model_rebuild()  # forward reference для children
```

### 4.4. `method.py` — методы платформы

```python
"""Методы платформы 1С (из .hbk синтакс-помощника)."""
from __future__ import annotations

from pydantic import Field
from .common import ModelConfig, Version, ContextAvailability


class PlatformMethod(ModelConfig):
    """Метод платформы 1С.

    Источник: .hbk файлы (8141 методов в платформе 8.3.20).
    Используется kb.check_method_availability для валидации контекста.
    """
    name: str = Field(description="Имя метода, например 'ЗаписьЖурналаРегистрации'")
    signature: str = Field(description="Полная сигнатура с параметрами")
    description: str = Field(description="Описание из синтакс-помощника")
    is_procedure: bool = Field(description="True = процедура, False = функция")
    return_type: str | None = None
    availability: ContextAvailability = Field(default_factory=ContextAvailability)
    version_since: Version | None = Field(default=None, description="Версия, в которой метод добавлен")
    version_deprecated: Version | None = Field(default=None, description="Версия, в которой метод устарел")
    deprecated_replacement: str | None = Field(default=None, description="Чем заменить устаревший метод")
    category: str = Field(default="Uncategorized", description="Категория: Глобальный контекст, Документы, ...")
    examples: list[str] = Field(default_factory=list)


class PlatformProperty(ModelConfig):
    """Свойство платформы (например, Метаданные, ПараметрыСеанса)."""
    name: str
    description: str
    type: str
    availability: ContextAvailability = Field(default_factory=ContextAvailability)
    version_since: Version | None = None
    version_deprecated: Version | None = None
```

### 4.5. `config.py` — конфигурация

```python
"""Конфигурация 1С как целое."""
from __future__ import annotations

from datetime import datetime
from pydantic import Field
from .common import ModelConfig, Version, ObjectRef
from .metadata import MetadataType


class VersionInfo(ModelConfig):
    """Версия конфигурации: '11.4.5.3', редакция 'Управление торговлей'."""
    version: str
    edition: str | None = None
    vendor: str | None = None
    description: str | None = None


class ConfigMeta(ModelConfig):
    """Метаданные конфигурации целиком (Configuration.xml)."""
    name: str = Field(description="Имя конфигурации: 'УправлениеТорговлей'")
    synonym: str | None = None
    version_info: VersionInfo
    platform_version: Version = Field(description="Версия платформы, для которой собрана конфигурация")
    default_data_lock_mode: str = "Managed"
    default_language: str = "ru"
    data separators: list[str] = Field(default_factory=list)
    object_counts: dict[MetadataType, int] = Field(
        default_factory=dict,
        description="Количество объектов каждого типа в конфигурации"
    )


class ConfigRegistryEntry(ModelConfig):
    """Запись в runtime/config-registry.json — реестр загруженных конфигов."""
    name: str
    version: str
    title: str | None = None
    added_at: datetime
    source_zip: str | None = None
    source_path: str
    index_path: str
    freshness_checked_at: datetime | None = None
    is_fresh: bool | None = None
```

### 4.6. `graph.py` — графы

```python
"""Графы зависимостей и вызовов."""
from __future__ import annotations

from pydantic import Field
from .common import ModelConfig, ObjectRef


class DependencyEdge(ModelConfig):
    """Ребро графа зависимостей метаданных.

    A зависит от B (A references B в XML).
    """
    source: ObjectRef
    target: ObjectRef
    edge_type: str = Field(description="Attribute | Form | TabularSection | Template | Command")
    detail: str | None = Field(default=None, description="Какой именно атрибут/форма ссылается")


class CallEdge(ModelConfig):
    """Ребро графа вызовов BSL-методов."""
    source_module: ObjectRef
    source_method: str
    target_module: ObjectRef | None = Field(default=None, description="None = вызов в том же модуле")
    target_method: str
    line: int = Field(ge=1)
    is_platform: bool = Field(default=False, description="True = метод платформы, False = метод конфигурации")


class GraphStats(ModelConfig):
    """Статистика графа."""
    nodes: int
    edges: int
    cycles: int
    avg_degree: float
    top_hubs: list[str] = Field(default_factory=list, description="Топ-10 узлов по степени")
```

## 5. `__init__.py` — единый re-export

```python
"""parsers.models — общие Pydantic-модели проекта.

Все модели frozen + extra=forbid + strict.
JSON Schema доступна через Model.model_json_schema().
"""
from .common import (
    ModelConfig,
    ObjectRef,
    Version,
    ExecutionEnvironment,
    ContextAvailability,
)
from .module import (
    BslModule,
    Method,
    MethodParameter,
    Region,
)
from .metadata import (
    MetadataType,
    Attribute,
    ObjectMetadata,
    CatalogMetadata,
    DocumentMetadata,
    CommonModuleMetadata,
    FormMetadata,
    FormElement,
)
from .method import (
    PlatformMethod,
    PlatformProperty,
)
from .config import (
    VersionInfo,
    ConfigMeta,
    ConfigRegistryEntry,
)
from .graph import (
    DependencyEdge,
    CallEdge,
    GraphStats,
)

__all__ = [
    # common
    "ModelConfig", "ObjectRef", "Version", "ExecutionEnvironment", "ContextAvailability",
    # module
    "BslModule", "Method", "MethodParameter", "Region",
    # metadata
    "MetadataType", "Attribute", "ObjectMetadata",
    "CatalogMetadata", "DocumentMetadata", "CommonModuleMetadata",
    "FormMetadata", "FormElement",
    # method
    "PlatformMethod", "PlatformProperty",
    # config
    "VersionInfo", "ConfigMeta", "ConfigRegistryEntry",
    # graph
    "DependencyEdge", "CallEdge", "GraphStats",
]
```

## 6. Версионирование моделей

### 6.1. Когда менять модель

- Добавление опционального поля с default — **minor** bump (0.1.0 → 0.2.0). Обратно-совместимо.
- Удаление поля или изменение типа — **major** bump (0.x → 1.0). Требует ADR.
- Переименование поля — **major** bump + alias для обратной совместимости на 1 minor-цикл.

### 6.2. Forward-compat с версиями 1С

Если 1С 8.3.22 добавит новые типы объектов метаданных — `MetadataType` enum扩展. Это breaking change для strict-моделей. Решение: `extra="allow"` только для `ObjectMetadata` (не для всех), чтобы новые поля не ломали парсинг. Но новые значения enum — это явное изменение, требующее bump.

### 6.3. JSON Schema для MCP

Каждая модель, которая возвращается через MCP, экспортирует JSON Schema:

```python
# В mcp_servers/metadata/contracts.py (Шаг 5)
from parsers.models import CatalogMetadata
input_schema = {
    "type": "object",
    "properties": {
        "object_ref": {"type": "string", "description": "Catalog.Контрагенты"},
        "config_name": {"type": "string"},
    },
    "required": ["object_ref", "config_name"],
}
output_schema = CatalogMetadata.model_json_schema()
```

Это даёт end-to-end типизацию: MCP-клиент знает схему ответа, orchestrator получает Pydantic-модель.

## 7. Тесты

```python
# tests/parsers/test_models.py
import pytest
from parsers.models import ObjectRef, BslModule, CatalogMetadata


class TestObjectRef:
    def test_from_string_valid(self):
        ref = ObjectRef.from_string("Catalog.Контрагенты")
        assert ref.type == "Catalog"
        assert ref.name == "Контрагенты"

    def test_from_string_invalid(self):
        with pytest.raises(ValueError):
            ObjectRef.from_string("invalid")

    def test_frozen(self):
        ref = ObjectRef.from_string("Catalog.Контрагенты")
        with pytest.raises(ValidationError):
            ref.name = "Другое"  # type: ignore

    def test_extra_forbidden(self):
        with pytest.raises(ValidationError):
            ObjectRef(type="Catalog", name="X", extra_field="bad")  # type: ignore


class TestBslModule:
    def test_json_schema_export(self):
        schema = BslModule.model_json_schema()
        assert "properties" in schema
        assert "object_ref" in schema["properties"]
        assert "source" in schema["properties"]

    def test_round_trip(self):
        module = BslModule(
            object_ref=ObjectRef.from_string("CommonModule.ОбщегоНазначения"),
            module_kind="CommonModule",
            source="// ...",
            line_count=1,
        )
        dumped = module.model_dump_json()
        restored = BslModule.model_validate_json(dumped)
        assert restored == module


class TestProperty:
    """Property-based tests через hypothesis."""
    @given(ref_type=st.text(min_size=1, max_size=20), name=st.text(min_size=1, max_size=20))
    def test_object_ref_round_trip(self, ref_type, name):
        ref = ObjectRef(type=ref_type, name=name)
        assert ObjectRef.from_string(str(ref)) == ref
```

## 8. Что НЕ вошло в модели

- **LLM-промпты и их структура** — это в `orchestrator/contracts.py` (Шаг 4), не в моделях данных. Модели — про данные 1С, не про agent state.
- **MCP tool definitions** — в `mcp_servers/{server}/contracts.py` (Шаг 5).
- **KB rules (YAML)** — это отдельный формат, парсится в `kb-server` (Шаг 7), не Pydantic.
- **State pipeline** (`TaskState`, `Subtask`) — в `orchestrator/state.py` (Шаг 4). Использует `BslModule` из `parsers.models`, но сам живёт в orchestrator.

---

**Шаг 2 завершён.** Следующий — Шаг 3: `PathManager` + data layer protocol, от которого зависят все MCP-серверы и pipeline.
