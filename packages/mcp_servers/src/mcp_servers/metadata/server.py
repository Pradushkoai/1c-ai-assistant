"""MetadataServer — реализация 4 metadata MCP tools (TD-S6-01).

4 tools (ADR-0010):
1. get_metadata — метаданные объекта (Catalog, Document, CommonModule, ...) из
   unified-metadata-index.json.
2. get_form_structure — структура управляемой формы (элементы, события, реквизиты)
   через парсинг Form.xml.
3. get_api_reference — экспортные методы общего модуля из api-reference.json.
4. get_dependency_graph — граф зависимостей метаданных (для Planner, blast radius).

Источник данных: PathManager → derived/configs/{name}/{version}/*.json +
data/configs/{name}/{version}/*.xml (для форм).

DI через конструктор: ``path_manager: PathManager | None = None``. Если None —
создаётся через ``PathManager()``.

См. ADR-0003 (MCP-архитектура), ADR-0010 (MCP tool contracts), ADR-0008 (PathManager),
D-2026-07-13-10.
"""

from __future__ import annotations

import logging
from typing import Any

from parsers.models import (
    CatalogMetadata,
    CommonModuleMetadata,
    DependencyEdge,
    DocumentMetadata,
    ObjectMetadata,
    RoleMetadata,
    SubsystemMetadata,
)

from .contracts import (
    GetApiReferenceInput,
    GetApiReferenceOutput,
    GetDependencyGraphInput,
    GetDependencyGraphOutput,
    GetFormStructureInput,
    GetFormStructureOutput,
    GetMetadataInput,
    GetMetadataOutput,
)

log = logging.getLogger(__name__)

# Mapping MetadataType → Pydantic class для get_metadata.
_METADATA_CLASSES: dict[str, type[ObjectMetadata]] = {
    "Catalog": CatalogMetadata,
    "Document": DocumentMetadata,
    "CommonModule": CommonModuleMetadata,
    "Subsystem": SubsystemMetadata,
    "Role": RoleMetadata,
}


class MetadataServerError(Exception):
    """Базовая ошибка MetadataServer."""

    code: str = "METADATA_ERROR"

    def __init__(
        self,
        message: str,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if code:
            self.code = code
        self.details = details or {}


class MetadataNotFoundError(MetadataServerError):
    """Объект/форма/модуль не найден."""

    code = "METADATA_NOT_FOUND"


class IndexNotFoundError(MetadataServerError):
    """Индекс (unified-metadata, api-reference, dependency-graph) не найден."""

    code = "INDEX_NOT_FOUND"


class MetadataServer:
    """Реализация 4 metadata MCP tools.

    Attributes:
        path_manager: PathManager для путей к индексам и XML. Если None —
            создаётся через ``PathManager()`` (может поднять FileNotFoundError
            если paths.env не найден).
    """

    def __init__(self, path_manager: Any = None) -> None:
        if path_manager is None:
            try:
                from data_layer import PathManager

                path_manager = PathManager()
            except FileNotFoundError as exc:
                log.warning("MetadataServer: PathManager init failed: %s", exc)
                raise
        self.path_manager = path_manager

    # ─── 1. get_metadata ─────────────────────────────────────────────────────

    async def get_metadata(
        self,
        object_ref: str,
        config_name: str,
        config_version: str,
    ) -> GetMetadataOutput:
        """Получить метаданные объекта 1С.

        Args:
            object_ref: строка вида 'Catalog.Контрагенты', 'Document.Реализация'.
            config_name: имя конфигурации.
            config_version: версия.

        Returns:
            GetMetadataOutput с Pydantic metadata моделью.

        Raises:
            IndexNotFoundError: unified-metadata-index.json не найден.
            MetadataNotFoundError: объект не найден в индексе.
        """
        log.info("metadata_get_metadata: %s %s/%s", object_ref, config_name, config_version)
        from parsers.indexers import get_object_from_index, load_metadata_index

        index_path = self.path_manager.unified_metadata_index(config_name, config_version)
        if not index_path.exists():
            raise IndexNotFoundError(
                f"unified-metadata-index.json not found: {index_path}. Run: 1c-ai config build",
                details={"path": str(index_path)},
            )

        index = load_metadata_index(index_path)
        if index is None:
            raise IndexNotFoundError(
                f"unified-metadata-index.json is empty/invalid: {index_path}",
                details={"path": str(index_path)},
            )

        obj_dict = get_object_from_index(index, object_ref)
        if obj_dict is None:
            raise MetadataNotFoundError(
                f"Object {object_ref!r} not found in index",
                details={"object_ref": object_ref},
            )

        # Определяем тип и выбираем Pydantic класс.
        # metadata_type в JSON — str ("Catalog"), в модели — MetadataType enum.
        # Конвертируем для model_validate (ModelConfig strict=True).
        metadata_type_str = obj_dict.get("metadata_type", "")
        cls = _METADATA_CLASSES.get(metadata_type_str, ObjectMetadata)
        obj_dict = {**obj_dict}
        if metadata_type_str:
            from parsers.models import MetadataType

            obj_dict["metadata_type"] = MetadataType(metadata_type_str)
        metadata = cls.model_validate(obj_dict)

        return GetMetadataOutput(object_ref=object_ref, metadata=metadata)

    # ─── 2. get_form_structure ───────────────────────────────────────────────

    async def get_form_structure(
        self,
        object_ref: str,
        form_name: str,
        config_name: str,
        config_version: str,
    ) -> GetFormStructureOutput:
        """Получить структуру управляемой формы.

        Args:
            object_ref: 'Catalog.Контрагенты'.
            form_name: 'ФормаСписка' | 'ФормаЭлемента' | ...
            config_name: имя конфигурации.
            config_version: версия.

        Returns:
            GetFormStructureOutput с FormMetadata.

        Raises:
            MetadataNotFoundError: Form.xml не найден.
        """
        log.info(
            "metadata_get_form: %s/%s %s/%s",
            object_ref,
            form_name,
            config_name,
            config_version,
        )
        from parsers.xml import parse_form

        # Путь к Form.xml: data/configs/{name}/{version}/{Type}s/{Name}/Forms/{form_name}.xml
        # object_ref = "Catalog.Товары" → type="Catalog", name="Товары"
        if "." not in object_ref:
            raise MetadataNotFoundError(
                f"Invalid object_ref: {object_ref!r}. Expected 'Type.Name'.",
                details={"object_ref": object_ref},
            )
        type_, name = object_ref.split(".", 1)
        config_dir = self.path_manager.data_config_dir(config_name, config_version)
        form_xml_path = config_dir / f"{type_}s" / name / "Forms" / f"{form_name}.xml"

        if not form_xml_path.exists():
            raise MetadataNotFoundError(
                f"Form.xml not found: {form_xml_path}",
                details={"path": str(form_xml_path)},
            )

        form = parse_form(form_xml_path)
        return GetFormStructureOutput(object_ref=object_ref, form_name=form_name, form=form)

    # ─── 3. get_api_reference ────────────────────────────────────────────────

    async def get_api_reference(
        self,
        module_name: str,
        config_name: str,
        config_version: str,
    ) -> GetApiReferenceOutput:
        """API-справочник общего модуля: экспортные методы с сигнатурами.

        Args:
            module_name: имя общего модуля ('ОбщегоНазначения').
            config_name: имя конфигурации.
            config_version: версия.

        Returns:
            GetApiReferenceOutput с списком методов.

        Raises:
            IndexNotFoundError: api-reference.json не найден.
            MetadataNotFoundError: модуль не найден в api-reference.
        """
        log.info(
            "metadata_get_api_ref: %s %s/%s",
            module_name,
            config_name,
            config_version,
        )
        from parsers.indexers import load_api_reference

        api_ref_path = self.path_manager.api_reference_index(config_name, config_version)
        if not api_ref_path.exists():
            raise IndexNotFoundError(
                f"api-reference.json not found: {api_ref_path}. Run: 1c-ai config build",
                details={"path": str(api_ref_path)},
            )

        api_ref = load_api_reference(api_ref_path)
        if api_ref is None:
            raise IndexNotFoundError(
                f"api-reference.json is empty/invalid: {api_ref_path}",
                details={"path": str(api_ref_path)},
            )

        # Ищем модуль по имени (CommonModule.{module_name}).
        target_ref = f"CommonModule.{module_name}"
        methods: list[dict[str, Any]] = []
        for module in api_ref.get("modules", []):
            mod_obj_ref = module.get("object_ref", "")
            if mod_obj_ref == target_ref or mod_obj_ref.endswith(f".{module_name}"):
                methods = list(module.get("export_methods", []))
                break

        if not methods:
            raise MetadataNotFoundError(
                f"Module {module_name!r} not found in api-reference (or has no export methods)",
                details={"module_name": module_name},
            )

        return GetApiReferenceOutput(module_name=module_name, methods=methods)

    # ─── 4. get_dependency_graph ─────────────────────────────────────────────

    async def get_dependency_graph(
        self,
        config_name: str,
        config_version: str,
        object_ref: str | None = None,
        direction: str = "depends_on",
        depth: int = 1,
    ) -> GetDependencyGraphOutput:
        """Граф зависимостей метаданных.

        Args:
            config_name: имя конфигурации.
            config_version: версия.
            object_ref: если None — весь граф; иначе — фильтр по объекту.
            direction: 'depends_on' (исходящие) или 'depended_by' (входящие).
            depth: 1 — прямой сосед; >1 — transitive (до 5).

        Returns:
            GetDependencyGraphOutput с рёбрами и статистикой.

        Raises:
            IndexNotFoundError: dependency-graph.json не найден.
            MetadataNotFoundError: object_ref не найден в графе.
        """
        log.info(
            "metadata_get_dep_graph: %s/%s object=%s dir=%s depth=%s",
            config_name,
            config_version,
            object_ref,
            direction,
            depth,
        )
        from parsers.xml.dependency_graph import (
            get_dependencies,
            get_dependents,
            get_transitive_dependencies,
            get_transitive_dependents,
            load_dependency_graph,
        )

        dep_path = self.path_manager.dependency_graph_index(config_name, config_version)
        if not dep_path.exists():
            raise IndexNotFoundError(
                f"dependency-graph.json not found: {dep_path}. Run: 1c-ai config build",
                details={"path": str(dep_path)},
            )

        dep_graph = load_dependency_graph(dep_path)
        if dep_graph is None:
            raise IndexNotFoundError(
                f"dependency-graph.json is empty/invalid: {dep_path}",
                details={"path": str(dep_path)},
            )

        # Если object_ref не задан — возвращаем весь граф (с лимитом рёбер для safety).
        if object_ref is None:
            all_edges = dep_graph.get("edges", [])[:500]  # cap для MCP response
            stats = {
                "total_edges": len(dep_graph.get("edges", [])),
                "returned_edges": len(all_edges),
                "truncated": len(dep_graph.get("edges", [])) > 500,
            }
            edges = [DependencyEdge.model_validate(e) for e in all_edges]
            return GetDependencyGraphOutput(object_ref=None, edges=edges, stats=stats)

        # Фильтр по object_ref + direction + depth.
        if direction == "depends_on":
            if depth == 1:
                raw_edges = get_dependencies(dep_graph, object_ref)
            else:
                # Transitive: все объекты, на которые зависит object_ref.
                transitive_refs = get_transitive_dependencies(dep_graph, object_ref, max_depth=depth)
                raw_edges = _collect_edges_for_targets(dep_graph, object_ref, transitive_refs, "depends_on")
        elif direction == "depended_by":
            if depth == 1:
                raw_edges = get_dependents(dep_graph, object_ref)
            else:
                transitive_refs = get_transitive_dependents(dep_graph, object_ref, max_depth=depth)
                raw_edges = _collect_edges_for_targets(dep_graph, object_ref, transitive_refs, "depended_by")
        else:
            raise MetadataServerError(
                f"Invalid direction: {direction!r}. Expected 'depends_on' or 'depended_by'.",
                code="INVALID_DIRECTION",
            )

        if not raw_edges:
            raise MetadataNotFoundError(
                f"No dependencies found for {object_ref!r} (direction={direction}, depth={depth})",
                details={"object_ref": object_ref, "direction": direction, "depth": depth},
            )

        edges = [DependencyEdge.model_validate(e) for e in raw_edges]
        stats = {
            "edges_count": len(edges),
            "direction": direction,
            "depth": depth,
        }
        return GetDependencyGraphOutput(object_ref=object_ref, edges=edges, stats=stats)


def _collect_edges_for_targets(
    dep_graph: dict[str, Any],
    root_ref: str,
    transitive_refs: list[str],
    direction: str,
) -> list[dict[str, Any]]:
    """Собрать рёбра для transitive closure (вспомогательная функция)."""
    from parsers.xml.dependency_graph import get_dependencies, get_dependents

    all_edges: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    # Рёбра от root → его прямые соседи.
    direct = get_dependencies(dep_graph, root_ref) if direction == "depends_on" else get_dependents(dep_graph, root_ref)
    for e in direct:
        tgt = e.get("target") if direction == "depends_on" else e.get("source")
        tgt_str = f"{tgt.get('type')}.{tgt.get('name')}" if isinstance(tgt, dict) else ""
        if tgt_str and tgt_str not in seen_targets:
            all_edges.append(e)
            seen_targets.add(tgt_str)
    # Рёбра от transitive соседей → их прямые соседи (1-hop каждый).
    for ref in transitive_refs:
        if ref == root_ref or ref in seen_targets:
            continue
        sub_edges = get_dependencies(dep_graph, ref) if direction == "depends_on" else get_dependents(dep_graph, ref)
        for e in sub_edges:
            tgt = e.get("target") if direction == "depends_on" else e.get("source")
            tgt_str = f"{tgt.get('type')}.{tgt.get('name')}" if isinstance(tgt, dict) else ""
            key = f"{ref}->{tgt_str}"
            if key not in seen_targets:
                all_edges.append(e)
                seen_targets.add(key)
    return all_edges


# ─── Tool implementations (для MCP server) ───────────────────────────────────


class GetMetadataImplementation:
    """Реализация metadata.get_metadata tool — обёртка над MetadataServer.get_metadata()."""

    def __init__(self, server: MetadataServer | None = None) -> None:
        self._server = server or MetadataServer()

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        input_data = GetMetadataInput.model_validate(kwargs)
        result = await self._server.get_metadata(
            object_ref=input_data.object_ref,
            config_name=input_data.config_name,
            config_version=input_data.config_version,
        )
        return result.model_dump(mode="json")


class GetFormStructureImplementation:
    """Реализация metadata.get_form_structure tool."""

    def __init__(self, server: MetadataServer | None = None) -> None:
        self._server = server or MetadataServer()

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        input_data = GetFormStructureInput.model_validate(kwargs)
        result = await self._server.get_form_structure(
            object_ref=input_data.object_ref,
            form_name=input_data.form_name,
            config_name=input_data.config_name,
            config_version=input_data.config_version,
        )
        return result.model_dump(mode="json")


class GetApiReferenceImplementation:
    """Реализация metadata.get_api_reference tool."""

    def __init__(self, server: MetadataServer | None = None) -> None:
        self._server = server or MetadataServer()

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        input_data = GetApiReferenceInput.model_validate(kwargs)
        result = await self._server.get_api_reference(
            module_name=input_data.module_name,
            config_name=input_data.config_name,
            config_version=input_data.config_version,
        )
        return result.model_dump(mode="json")


class GetDependencyGraphImplementation:
    """Реализация metadata.get_dependency_graph tool."""

    def __init__(self, server: MetadataServer | None = None) -> None:
        self._server = server or MetadataServer()

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        input_data = GetDependencyGraphInput.model_validate(kwargs)
        result = await self._server.get_dependency_graph(
            config_name=input_data.config_name,
            config_version=input_data.config_version,
            object_ref=input_data.object_ref,
            direction=input_data.direction,
            depth=input_data.depth,
        )
        return result.model_dump(mode="json")
