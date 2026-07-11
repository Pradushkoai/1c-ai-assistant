"""metadata-server: метаданные 1С.

Источник: data/configs/{name}/{version}/ → unified-metadata-index.json
Парсер: parsers.xml
Рантайм: Python

См. ADR-0010 (MCP tool contracts).
"""

from __future__ import annotations

from typing import Any, Literal

from parsers.models import (
    CatalogMetadata,
    CommonModuleMetadata,
    DependencyEdge,
    DocumentMetadata,
    FormMetadata,
    ObjectMetadata,
)
from pydantic import BaseModel, ConfigDict, Field

# ─── Inputs ──────────────────────────────────────────────────────────────────


class GetMetadataInput(BaseModel):
    """Input для metadata.get_metadata."""

    object_ref: str = Field(description="Catalog.Контрагенты | Document.Реализация | CommonModule.ОбщегоНазначения")
    config_name: str
    config_version: str


class GetFormStructureInput(BaseModel):
    """Input для metadata.get_form_structure."""

    object_ref: str = Field(description="Catalog.Контрагенты")
    form_name: str = Field(description="ФормаСписка | ФормаЭлемента | ФормаВыбора")
    config_name: str
    config_version: str


class GetApiReferenceInput(BaseModel):
    """Input для metadata.get_api_reference."""

    module_name: str = Field(description="ОбщегоНазначения")
    config_name: str
    config_version: str


class GetDependencyGraphInput(BaseModel):
    """Input для metadata.get_dependency_graph."""

    config_name: str
    config_version: str
    object_ref: str | None = Field(default=None, description="Если None — весь граф")
    direction: Literal["depends_on", "depended_by"] = "depends_on"
    depth: int = Field(default=1, ge=1, le=5)


# ─── Outputs ─────────────────────────────────────────────────────────────────


class GetMetadataOutput(BaseModel):
    """Output для metadata.get_metadata."""

    object_ref: str
    metadata: ObjectMetadata | CatalogMetadata | DocumentMetadata | CommonModuleMetadata


class GetFormStructureOutput(BaseModel):
    """Output для metadata.get_form_structure."""

    object_ref: str
    form_name: str
    form: FormMetadata


class GetApiReferenceOutput(BaseModel):
    """Output для metadata.get_api_reference."""

    module_name: str
    methods: list[dict[str, Any]] = Field(description="Экспортные методы с сигнатурами")


class GetDependencyGraphOutput(BaseModel):
    """Output для metadata.get_dependency_graph."""

    object_ref: str | None
    edges: list[DependencyEdge]
    stats: dict[str, Any]


# ─── Tool contracts ──────────────────────────────────────────────────────────
# Используем BaseModel как mixin для атрибутов, чтобы Protocol ToolContract
# был удовлетворён. Реализация __call__ — NotImplementedError (Sprint 1.5 каркас).


class _ContractBase(BaseModel):
    """Базовый класс для tool contracts с метаданными.

    Не frozen — контракты хранят атрибуты класса, не инстанс.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)


class GetMetadata:
    """metadata.get_metadata — получить метаданные объекта 1С."""

    name: str = "metadata.get_metadata"
    description: str = (
        "Получить метаданные объекта 1С (Catalog, Document, CommonModule, ...). "
        "Возвращает: атрибуты, формы, шаблоны, команды. "
        "Пример: metadata.get_metadata(object_ref='Catalog.Контрагенты', "
        "config_name='ut11', config_version='4.5.3')"
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "object_ref": {"type": "string", "description": "Catalog.Контрагенты"},
            "config_name": {"type": "string"},
            "config_version": {"type": "string"},
        },
        "required": ["object_ref", "config_name", "config_version"],
    }
    output_model: type[BaseModel] = GetMetadataOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 30
    idempotent: bool = True
    required_role: str = "GATHERER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        """Выполнить tool. Реализация в Sprint 4 (metadata server)."""
        raise NotImplementedError("metadata.get_metadata — реализация в Sprint 4")


class GetFormStructure:
    """metadata.get_form_structure — получить структуру управляемой формы."""

    name: str = "metadata.get_form_structure"
    description: str = (
        "Получить структуру управляемой формы: элементы, дата-пути, события, реквизиты. "
        "Пример: metadata.get_form_structure(object_ref='Catalog.Контрагенты', "
        "form_name='ФормаЭлемента', config_name='ut11', config_version='4.5.3')"
    )
    input_schema: dict[str, Any] = GetFormStructureInput.model_json_schema()
    output_model: type[BaseModel] = GetFormStructureOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 30
    idempotent: bool = True
    required_role: str = "GATHERER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("metadata.get_form_structure — реализация в Sprint 4")


class GetApiReference:
    """metadata.get_api_reference — API-справочник общего модуля."""

    name: str = "metadata.get_api_reference"
    description: str = (
        "API-справочник общего модуля: список экспортных методов с сигнатурами. "
        "Пример: metadata.get_api_reference(module_name='ОбщегоНазначения', "
        "config_name='ut11', config_version='4.5.3')"
    )
    input_schema: dict[str, Any] = GetApiReferenceInput.model_json_schema()
    output_model: type[BaseModel] = GetApiReferenceOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 30
    idempotent: bool = True
    required_role: str = "GATHERER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("metadata.get_api_reference — реализация в Sprint 4")


class GetDependencyGraph:
    """metadata.get_dependency_graph — граф зависимостей метаданных."""

    name: str = "metadata.get_dependency_graph"
    description: str = (
        "Граф зависимостей метаданных: кто на кого ссылается. "
        "Используется Planner'ом для структурного анализа. "
        "Пример: metadata.get_dependency_graph(config_name='ut11', "
        "config_version='4.5.3', object_ref='Catalog.Контрагенты', depth=2)"
    )
    input_schema: dict[str, Any] = GetDependencyGraphInput.model_json_schema()
    output_model: type[BaseModel] = GetDependencyGraphOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 30
    idempotent: bool = True
    required_role: str = "PLANNER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("metadata.get_dependency_graph — реализация в Sprint 4")


# Реестр tools metadata-server'а
METADATA_TOOLS: list[type[Any]] = [
    GetMetadata,
    GetFormStructure,
    GetApiReference,
    GetDependencyGraph,
]
