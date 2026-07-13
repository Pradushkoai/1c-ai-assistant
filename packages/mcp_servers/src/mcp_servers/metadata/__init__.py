"""mcp_servers.metadata — метаданные 1С (4 tools).

Контракты: GetMetadata, GetFormStructure, GetApiReference, GetDependencyGraph.
Реализация: MetadataServer — читает из PathManager (unified-metadata-index.json,
api-reference.json, dependency-graph.json, Form.xml).
"""

from __future__ import annotations

from .contracts import METADATA_TOOLS
from .server import (
    GetApiReferenceImplementation,
    GetDependencyGraphImplementation,
    GetFormStructureImplementation,
    GetMetadataImplementation,
    IndexNotFoundError,
    MetadataNotFoundError,
    MetadataServer,
    MetadataServerError,
)

__all__ = [
    "METADATA_TOOLS",
    "MetadataServer",
    # Tool implementations
    "GetMetadataImplementation",
    "GetFormStructureImplementation",
    "GetApiReferenceImplementation",
    "GetDependencyGraphImplementation",
    # Errors
    "MetadataServerError",
    "MetadataNotFoundError",
    "IndexNotFoundError",
]
