"""mcp_servers.codebase — BSL-код конфигурации.

Sprint 4.2 (TD-S4.2-02): codebase MCP server — 4 tools.
"""

from __future__ import annotations

from .contracts import CODEBASE_TOOLS
from .server import CodebaseServer
from .vector_store import (
    InMemoryVectorStore,
    PgVectorStore,
    VectorStoreProtocol,
    make_vector_store,
)

__all__ = [
    "CODEBASE_TOOLS",
    "CodebaseServer",
    "VectorStoreProtocol",
    "PgVectorStore",
    "InMemoryVectorStore",
    "make_vector_store",
]
