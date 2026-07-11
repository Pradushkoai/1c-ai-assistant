"""parsers.models — общие Pydantic v2 модели проекта.

Все модели frozen + extra=forbid + strict (см. ADR-0007).
JSON Schema доступна через Model.model_json_schema().

Категории моделей:
- common: базовые типы (ObjectRef, Version, ExecutionEnvironment, ContextAvailability)
- module: BSL-модули (BslModule, Method, Region, MethodParameter)
- metadata: метаданные 1С (CatalogMetadata, DocumentMetadata, ...)
- method: методы платформы (PlatformMethod, PlatformProperty)
- config: конфигурация (ConfigMeta, VersionInfo, ConfigRegistryEntry)
- graph: графы (DependencyEdge, CallEdge, GraphStats)

Examples:
    >>> from parsers.models import ObjectRef, BslModule, CatalogMetadata
    >>> ref = ObjectRef.from_string("Catalog.Товары")
    >>> str(ref)
    'Catalog.Товары'
"""

from __future__ import annotations

from .common import (
    ContextAvailability,
    ExecutionEnvironment,
    ModelConfig,
    ObjectRef,
    Version,
)
from .config import (
    ConfigMeta,
    ConfigRegistryEntry,
    VersionInfo,
)
from .graph import (
    CallEdge,
    DependencyEdge,
    GraphStats,
)
from .metadata import (
    Attribute,
    AttributeKind,
    CatalogMetadata,
    CommonModuleMetadata,
    DocumentMetadata,
    FormElement,
    FormMetadata,
    MetadataType,
    ObjectMetadata,
)
from .method import (
    PlatformMethod,
    PlatformProperty,
)
from .module import (
    BslModule,
    Method,
    MethodParameter,
    Region,
)

__all__ = [
    # common
    "ModelConfig",
    "ObjectRef",
    "Version",
    "ExecutionEnvironment",
    "ContextAvailability",
    # module
    "Region",
    "MethodParameter",
    "Method",
    "BslModule",
    # metadata
    "MetadataType",
    "AttributeKind",
    "Attribute",
    "ObjectMetadata",
    "CatalogMetadata",
    "DocumentMetadata",
    "CommonModuleMetadata",
    "FormElement",
    "FormMetadata",
    # method
    "PlatformMethod",
    "PlatformProperty",
    # config
    "VersionInfo",
    "ConfigMeta",
    "ConfigRegistryEntry",
    # graph
    "DependencyEdge",
    "CallEdge",
    "GraphStats",
]
