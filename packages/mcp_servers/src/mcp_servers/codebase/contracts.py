"""codebase-server: BSL-код конфигурации.

Источник: data/configs/{name}/{version}/*.bsl → embeddings + call-graph.json
Парсер: parsers.bsl
Рантайм: Python + pgvector/Qdrant (Docker)

См. ADR-0010 (MCP tool contracts) и ADR-0017 (VectorStoreProtocol).
"""

from __future__ import annotations

from typing import Any, Literal

from parsers.models import BslModule, CallEdge
from pydantic import BaseModel, Field

# ─── Inputs ──────────────────────────────────────────────────────────────────


class SemanticSearchInput(BaseModel):
    """Input для codebase.semantic_search."""

    query: str = Field(description="ОбработкаПроведения, регистрация движений, ...")
    config_name: str
    config_version: str
    top_k: int = Field(default=5, ge=1, le=20)
    filters: dict[str, Any] | None = Field(
        default=None,
        description="{'module_kind': 'ObjectModule', 'object_type': 'Document'}",
    )


class GetModuleInput(BaseModel):
    """Input для codebase.get_module."""

    object_ref: str = Field(description="CommonModule.ОбщегоНазначения")
    module_kind: str = Field(
        default="ObjectModule",
        description="ObjectModule | ManagerModule | FormModule | CommonModule",
    )
    config_name: str
    config_version: str


class GetSimilarInput(BaseModel):
    """Input для codebase.get_similar."""

    object_ref: str = Field(description="Найти похожие на этот модуль")
    config_name: str
    config_version: str
    top_k: int = Field(default=5, ge=1, le=20)


class CallGraphInput(BaseModel):
    """Input для codebase.call_graph."""

    config_name: str
    config_version: str
    object_ref: str | None = Field(default=None, description="Подграф для объекта")
    method_name: str | None = Field(default=None, description="Только вызовы из этого метода")


# ─── Outputs ─────────────────────────────────────────────────────────────────


class SemanticSearchOutput(BaseModel):
    """Output для codebase.semantic_search."""

    query: str
    results: list[dict[str, Any]] = Field(description="[{module, score, snippet, object_ref}]")


class GetModuleOutput(BaseModel):
    """Output для codebase.get_module."""

    module: BslModule


class GetSimilarOutput(BaseModel):
    """Output для codebase.get_similar."""

    object_ref: str
    similar: list[dict[str, Any]] = Field(description="[{module, score}]")


class CallGraphOutput(BaseModel):
    """Output для codebase.call_graph."""

    object_ref: str | None
    edges: list[CallEdge]
    stats: dict[str, Any]


# ─── Tool contracts ──────────────────────────────────────────────────────────


class SemanticSearch:
    """codebase.semantic_search — гибридный поиск по BSL-кодам."""

    name: str = "codebase.semantic_search"
    description: str = (
        "Гибридный поиск (BM25 + vector) по BSL-кодам конфигурации. "
        "Возвращает top-K релевантных модулей со сниппетами. "
        "Пример: codebase.semantic_search(query='ОбработкаПроведения', "
        "config_name='ut11', config_version='4.5.3')"
    )
    input_schema: dict[str, Any] = SemanticSearchInput.model_json_schema()
    output_model: type[BaseModel] = SemanticSearchOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 10
    idempotent: bool = True
    required_role: str = "GATHERER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("codebase.semantic_search — реализация в Sprint 4")


class GetModule:
    """codebase.get_module — получить полный BslModule."""

    name: str = "codebase.get_module"
    description: str = "Получить полный BslModule (с методами, регионами, AST)."
    input_schema: dict[str, Any] = GetModuleInput.model_json_schema()
    output_model: type[BaseModel] = GetModuleOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 10
    idempotent: bool = True
    required_role: str = "GATHERER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("codebase.get_module — реализация в Sprint 4")


class GetSimilar:
    """codebase.get_similar — найти похожие модули."""

    name: str = "codebase.get_similar"
    description: str = "Найти модули, похожие на заданный (через embeddings)."
    input_schema: dict[str, Any] = GetSimilarInput.model_json_schema()
    output_model: type[BaseModel] = GetSimilarOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 10
    idempotent: bool = True
    required_role: str = "REVIEWER"  # Reviewer смотрит похожие — может, есть pattern

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("codebase.get_similar — реализация в Sprint 4")


class CallGraph:
    """codebase.call_graph — граф вызовов BSL-методов."""

    name: str = "codebase.call_graph"
    description: str = (
        "Граф вызовов BSL-методов. Используется для анализа: что вызывает данный метод, кто вызывает его."
    )
    input_schema: dict[str, Any] = CallGraphInput.model_json_schema()
    output_model: type[BaseModel] = CallGraphOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 15
    idempotent: bool = True
    required_role: str = "GATHERER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("codebase.call_graph — реализация в Sprint 4")


CODEBASE_TOOLS: list[type[Any]] = [
    SemanticSearch,
    GetModule,
    GetSimilar,
    CallGraph,
]
