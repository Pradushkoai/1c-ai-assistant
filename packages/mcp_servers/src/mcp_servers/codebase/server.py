"""CodebaseServer — реализация 4 codebase MCP tools.

Sprint 4.2 (TD-S4.2-02 ч.2): codebase MCP server.

4 tools (ADR-0010, ADR-0020):
1. semantic_search — гибридный BM25+vector+RRF поиск по BSL-коду
2. get_module — получить полный BslModule по object_ref
3. get_similar — найти похожие модули через embeddings
4. call_graph — граф вызовов (из call-graph.json)

Использует VectorStoreProtocol (ADR-0017) для search.
Использует parsers.bsl для get_module.
Использует parsers.bsl.call_graph для call_graph.

См. ADR-0010, ADR-0017, ADR-0020, CONCEPTUAL.md §1.2.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from parsers.models import CallEdge, ObjectRef

from .contracts import (
    CallGraphInput,
    CallGraphOutput,
    GetModuleInput,
    GetModuleOutput,
    GetSimilarInput,
    GetSimilarOutput,
    SemanticSearchInput,
    SemanticSearchOutput,
)
from .vector_store import VectorStoreProtocol, make_vector_store

log = logging.getLogger(__name__)


class CodebaseServer:
    """Реализация 4 codebase MCP tools.

    Attributes:
        vector_store: VectorStoreProtocol для search (pgvector или memory).
    """

    def __init__(self, vector_store: VectorStoreProtocol | None = None) -> None:
        """Инициализация.

        Args:
            vector_store: VectorStore для search. Если None — создаётся через factory.
        """
        self.vector_store = vector_store or make_vector_store()

    # ─── 1. semantic_search ──────────────────────────────────────────────────

    async def semantic_search(
        self,
        query: str,
        config_name: str,
        config_version: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> SemanticSearchOutput:
        """Гибридный поиск (BM25 + vector + RRF) по BSL-коду.

        Args:
            query: текст запроса ('ОбработкаПроведения', 'регистрация движений').
            config_name: имя конфигурации.
            config_version: версия.
            top_k: максимум результатов.
            filters: доп. фильтры ({'module_kind': 'ObjectModule', ...}).

        Returns:
            SemanticSearchOutput с результатами.
        """
        log.info(
            "semantic_search: query=%r config=%s/%s top_k=%d",
            query[:50], config_name, config_version, top_k,
        )

        # Фильтры: config + library (ADR-0020 multi-layer)
        search_filters = {
            "source_config": config_name,
            "source_version": config_version,
        }
        if filters:
            search_filters.update(filters)

        # Генерируем embedding для запроса
        from parsers.indexers.embeddings_indexer import embed_texts

        query_embeddings = embed_texts([query])
        if not query_embeddings:
            log.warning("semantic_search: failed to generate query embedding")
            # Fallback: только BM25
            results = await self.vector_store.search_bm25(
                query=query,
                top_k=top_k,
                filters=search_filters,
            )
        else:
            query_embedding = query_embeddings[0]

            # Гибридный поиск (BM25 + vector + RRF)
            results = await self.vector_store.search_hybrid(
                query=query,
                query_embedding=query_embedding,
                top_k=top_k,
                filters=search_filters,
            )

        # Форматируем результаты
        formatted: list[dict[str, Any]] = []
        for r in results:
            meta = r.get("metadata", {})
            formatted.append({
                "module": meta.get("object_ref", "unknown"),
                "method": meta.get("method_name", ""),
                "score": r.get("rrf_score", r.get("score", 0.0)),
                "snippet": r.get("code_text", "")[:200],
                "object_ref": meta.get("object_ref", ""),
                "module_kind": meta.get("module_kind", ""),
            })

        return SemanticSearchOutput(query=query, results=formatted)

    # ─── 2. get_module ───────────────────────────────────────────────────────

    async def get_module(
        self,
        object_ref: str,
        module_kind: str,
        config_name: str,
        config_version: str,
    ) -> GetModuleOutput:
        """Получить полный BslModule по object_ref.

        Args:
            object_ref: 'CommonModule.ОбщегоНазначения'.
            module_kind: 'ObjectModule' | 'ManagerModule' | 'CommonModule' | 'FormModule'.
            config_name: имя конфигурации.
            config_version: версия.

        Returns:
            GetModuleOutput с BslModule.
        """
        log.info("get_module: ref=%s kind=%s", object_ref, module_kind)

        from data_layer import PathManager
        from parsers.bsl import parse_bsl_module

        pm = PathManager()
        config_dir = pm.data_config_dir(config_name, config_version)

        # Находим .bsl файл для объекта
        bsl_path = _find_bsl_file(config_dir, object_ref, module_kind)
        if bsl_path is None:
            raise ValueError(f"Module not found: {object_ref} ({module_kind})")

        code = bsl_path.read_text(encoding="utf-8-sig", errors="replace")
        module = parse_bsl_module(code, object_ref=object_ref, module_kind=module_kind)

        return GetModuleOutput(module=module)

    # ─── 3. get_similar ──────────────────────────────────────────────────────

    async def get_similar(
        self,
        object_ref: str,
        config_name: str,
        config_version: str,
        top_k: int = 5,
    ) -> GetSimilarOutput:
        """Найти похожие модули через embeddings.

        Args:
            object_ref: 'CommonModule.ОбщегоНазначения'.
            config_name: имя конфигурации.
            config_version: версия.
            top_k: максимум результатов.

        Returns:
            GetSimilarOutput со списком похожих модулей.
        """
        log.info("get_similar: ref=%s top_k=%d", object_ref, top_k)

        # Ищем embedding для object_ref в vector store
        # Сначала ищем чанк с этим object_ref
        search_filters = {
            "source_config": config_name,
            "source_version": config_version,
        }

        # BM25 поиск по object_ref (точное имя)
        bm25_results = await self.vector_store.search_bm25(
            query=object_ref,
            top_k=1,
            filters=search_filters,
        )

        if not bm25_results:
            return GetSimilarOutput(object_ref=object_ref, similar=[])

        # Получаем embedding первого результата
        # В реальной реализации: SELECT embedding FROM code_chunks WHERE chunk_id = ?
        # Для InMemoryVectorStore: ищем в _chunks
        ref_embedding = _get_embedding_from_result(self.vector_store, bm25_results[0])

        if ref_embedding is None:
            return GetSimilarOutput(object_ref=object_ref, similar=[])

        # Vector search: находим похожие
        results = await self.vector_store.search(
            query_embedding=ref_embedding,
            top_k=top_k + 1,  # +1 потому что первый — сам объект
            filters=search_filters,
        )

        # Исключаем сам объект
        similar: list[dict[str, Any]] = []
        for r in results:
            meta = r.get("metadata", {})
            if meta.get("object_ref") == object_ref:
                continue
            similar.append({
                "module": meta.get("object_ref", "unknown"),
                "score": r.get("score", 0.0),
                "method": meta.get("method_name", ""),
            })
            if len(similar) >= top_k:
                break

        return GetSimilarOutput(object_ref=object_ref, similar=similar)

    # ─── 4. call_graph ───────────────────────────────────────────────────────

    async def call_graph(
        self,
        config_name: str,
        config_version: str,
        object_ref: str | None = None,
        method_name: str | None = None,
    ) -> CallGraphOutput:
        """Граф вызовов BSL-методов.

        Args:
            config_name: имя конфигурации.
            config_version: версия.
            object_ref: фильтр по объекту (если None — весь граф).
            method_name: фильтр по методу (если None — все методы объекта).

        Returns:
            CallGraphOutput с рёбрами и статистикой.
        """
        log.info("call_graph: config=%s/%s ref=%s method=%s",
                 config_name, config_version, object_ref, method_name)

        from data_layer import PathManager
        from parsers.bsl import load_call_graph

        pm = PathManager()
        cg_path = pm.call_graph_index(config_name, config_version)

        if not cg_path.exists():
            raise ValueError(f"Call graph not found: {cg_path}. Run: 1c-ai config build --name {config_name}")

        cg_data = load_call_graph(cg_path)
        if cg_data is None:
            raise ValueError(f"Failed to load call graph: {cg_path}")

        edges_raw = cg_data.get("edges", [])

        # Фильтрация по object_ref
        if object_ref:
            edges_raw = [
                e for e in edges_raw
                if _match_ref(e.get("source_module"), object_ref)
                or _match_ref(e.get("target_module"), object_ref)
            ]

        # Фильтрация по method_name
        if method_name:
            edges_raw = [
                e for e in edges_raw
                if e.get("source_method") == method_name
                or e.get("target_method") == method_name
            ]

        # Конвертируем в CallEdge модели
        edges: list[CallEdge] = []
        for e in edges_raw:
            try:
                source_module = _dict_to_object_ref(e.get("source_module"))
                target_module = _dict_to_object_ref(e.get("target_module"))

                edges.append(CallEdge(
                    source_module=source_module,
                    source_method=e.get("source_method", ""),
                    target_module=target_module,
                    target_method=e.get("target_method", ""),
                    line=e.get("line", 1),
                    is_platform=e.get("is_platform", False),
                ))
            except Exception as exc:
                log.debug("Failed to parse edge: %s", exc)

        stats = {
            "total_edges": len(edges),
            "unique_callers": len({e.source_module for e in edges}),
            "unique_callees": len({e.target_module for e in edges if e.target_module}),
        }

        return CallGraphOutput(
            object_ref=object_ref,
            edges=edges,
            stats=stats,
        )


# ─── Tool implementations (для MCP server) ─────────────────────────────────


class SemanticSearchImplementation:
    """Реализация codebase.semantic_search tool."""

    def __init__(self, server: CodebaseServer) -> None:
        self._server = server

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        input_data = SemanticSearchInput.model_validate(kwargs)
        result = await self._server.semantic_search(
            query=input_data.query,
            config_name=input_data.config_name,
            config_version=input_data.config_version,
            top_k=input_data.top_k,
            filters=input_data.filters,
        )
        return result.model_dump(mode="json")


class GetModuleImplementation:
    """Реализация codebase.get_module tool."""

    def __init__(self, server: CodebaseServer) -> None:
        self._server = server

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        input_data = GetModuleInput.model_validate(kwargs)
        result = await self._server.get_module(
            object_ref=input_data.object_ref,
            module_kind=input_data.module_kind,
            config_name=input_data.config_name,
            config_version=input_data.config_version,
        )
        return result.model_dump(mode="json")


class GetSimilarImplementation:
    """Реализация codebase.get_similar tool."""

    def __init__(self, server: CodebaseServer) -> None:
        self._server = server

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        input_data = GetSimilarInput.model_validate(kwargs)
        result = await self._server.get_similar(
            object_ref=input_data.object_ref,
            config_name=input_data.config_name,
            config_version=input_data.config_version,
            top_k=input_data.top_k,
        )
        return result.model_dump(mode="json")


class CallGraphImplementation:
    """Реализация codebase.call_graph tool."""

    def __init__(self, server: CodebaseServer) -> None:
        self._server = server

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        input_data = CallGraphInput.model_validate(kwargs)
        result = await self._server.call_graph(
            config_name=input_data.config_name,
            config_version=input_data.config_version,
            object_ref=input_data.object_ref,
            method_name=input_data.method_name,
        )
        return result.model_dump(mode="json")


# ─── Helpers ────────────────────────────────────────────────────────────────


def _find_bsl_file(
    config_dir: Path,
    object_ref: str,
    module_kind: str,
) -> Path | None:
    """Найти .bsl файл для объекта по object_ref и module_kind.

    Примеры:
        CommonModule.ОбщегоНазначения → CommonModules/ОбщегоНазначения/Ext/Module.bsl
        Catalog.Товары, ObjectModule → Catalogs/Товары/Ext/ObjectModule.bsl
        Document.Продажа, FormModule → Documents/Продажа/Forms/*/Ext/Form/Module.bsl
    """
    try:
        ref = ObjectRef.from_string(object_ref)
    except ValueError:
        return None

    # CommonModule: CommonModules/{name}/Ext/Module.bsl
    if ref.type == "CommonModule" and module_kind == "CommonModule":
        path = config_dir / "CommonModules" / ref.name / "Ext" / "Module.bsl"
        return path if path.exists() else None

    # Catalog/Document/etc: {Type}s/{name}/Ext/{ModuleKind}.bsl
    type_to_dir = {
        "Catalog": "Catalogs",
        "Document": "Documents",
        "DataProcessor": "DataProcessors",
        "Report": "Reports",
        "InformationRegister": "InformationRegisters",
        "AccumulationRegister": "AccumulationRegisters",
        "ChartOfCharacteristicTypes": "ChartsOfCharacteristicTypes",
    }

    type_dir = type_to_dir.get(ref.type)
    if type_dir is None:
        return None

    # ObjectModule, ManagerModule, RecordSetModule
    if module_kind in ("ObjectModule", "ManagerModule", "RecordSetModule"):
        path = config_dir / type_dir / ref.name / "Ext" / f"{module_kind}.bsl"
        return path if path.exists() else None

    # FormModule: ищем любую форму
    if module_kind == "FormModule":
        forms_dir = config_dir / type_dir / ref.name / "Forms"
        if forms_dir.exists():
            for form_dir in forms_dir.iterdir():
                if form_dir.is_dir():
                    path = form_dir / "Ext" / "Form" / "Module.bsl"
                    if path.exists():
                        return path

    return None


def _match_ref(module_dict: dict[str, Any] | None, object_ref: str) -> bool:
    """Проверить, соответствует ли module_dict строке object_ref."""
    if module_dict is None:
        return False
    ref_str = f"{module_dict.get('type', '')}.{module_dict.get('name', '')}"
    return ref_str == object_ref


def _dict_to_object_ref(d: dict[str, Any] | None) -> ObjectRef:
    """Создать ObjectRef из dict."""
    if d is None:
        return ObjectRef(type="CommonModule", name="Unknown")
    return ObjectRef(
        type=d.get("type", "CommonModule"),
        name=d.get("name", "Unknown"),
    )


def _get_embedding_from_result(
    vector_store: VectorStoreProtocol,
    result: dict[str, Any],
) -> list[float] | None:
    """Получить embedding чанка из result (для get_similar).

    Для InMemoryVectorStore: ищем в _chunks по chunk_id.
    Для PgVectorStore: отдельный SELECT.
    """
    chunk_id = result.get("chunk_id")
    if chunk_id is None:
        return None

    # InMemoryVectorStore
    if hasattr(vector_store, "_chunks"):
        for chunk in vector_store._chunks:
            if chunk.get("chunk_id") == chunk_id:
                return chunk.get("embedding")

    # PgVectorStore: нужен отдельный запрос
    # TODO: добавить метод get_embedding(chunk_id) в VectorStoreProtocol
    log.warning("get_embedding_from_result: not implemented for %s", type(vector_store).__name__)
    return None
