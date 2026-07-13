"""tests/mcp_servers/test_metadata_server.py — MetadataServer (TD-S6-01).

Покрытие:
- 4 tools (get_metadata, get_form_structure, get_api_reference, get_dependency_graph):
  happy path (mock PathManager + load_*), error cases.
- Tool Implementations (GetMetadataImplementation etc.) — обёртки.
- Errors: MetadataNotFoundError, IndexNotFoundError, MetadataServerError.

См. ADR-0003, ADR-0010, D-2026-07-13-10.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from mcp_servers.metadata import (
    GetApiReferenceImplementation,
    GetDependencyGraphImplementation,
    GetFormStructureImplementation,
    GetMetadataImplementation,
    IndexNotFoundError,
    MetadataNotFoundError,
    MetadataServer,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_path_manager(tmp_path: Path) -> MagicMock:
    """Mock PathManager с указателями на tmp_path файлы."""
    pm = MagicMock()
    pm.unified_metadata_index.return_value = tmp_path / "unified-metadata-index.json"
    pm.api_reference_index.return_value = tmp_path / "api-reference.json"
    pm.dependency_graph_index.return_value = tmp_path / "dependency-graph.json"
    pm.data_config_dir.return_value = tmp_path / "configs" / "ut11" / "4.5.3"
    return pm


@pytest.fixture
def metadata_index_data() -> dict[str, Any]:
    """Тестовый unified-metadata-index (формат как в реальном JSON)."""
    return {
        "objects": {
            "Catalog": [
                {
                    "object_ref": {"type": "Catalog", "name": "Товары"},
                    "metadata_type": "Catalog",
                    "name": "Товары",
                    "synonym": "Товары",
                    "attributes": [],
                    "forms": ["ФормаСписка", "ФормаЭлемента"],
                    "templates": [],
                    "commands": [],
                }
            ],
            "CommonModule": [
                {
                    "object_ref": {"type": "CommonModule", "name": "ОбщегоНазначения"},
                    "metadata_type": "CommonModule",
                    "name": "ОбщегоНазначения",
                    "synonym": "Общего назначения",
                }
            ],
        }
    }


@pytest.fixture
def api_reference_data() -> dict[str, Any]:
    """Тестовый api-reference."""
    return {
        "modules": [
            {
                "object_ref": "CommonModule.ОбщегоНазначения",
                "export_methods": [
                    {"name": "ВыполнитьЗапрос", "parameters": ["Запрос"], "is_function": True},
                    {"name": "ЗаписатьЛог", "parameters": ["Сообщение"], "is_function": False},
                ],
            },
            {
                "object_ref": "CommonModule.ДругойМодуль",
                "export_methods": [],
            },
        ]
    }


@pytest.fixture
def dependency_graph_data() -> dict[str, Any]:
    """Тестовый dependency-graph."""
    return {
        "edges": [
            {
                "source": {"type": "Catalog", "name": "Товары"},
                "target": {"type": "Catalog", "name": "Контрагенты"},
                "edge_type": "Attribute",
                "detail": "Владелец",
            },
            {
                "source": {"type": "Document", "name": "Продажа"},
                "target": {"type": "Catalog", "name": "Товары"},
                "edge_type": "Attribute",
                "detail": "Товар",
            },
        ],
        "nodes": ["Catalog.Товары", "Catalog.Контрагенты", "Document.Продажа"],
    }


# ─── get_metadata ────────────────────────────────────────────────────────────


class TestGetMetadata:
    @pytest.mark.asyncio
    async def test_get_metadata_happy_path(
        self,
        mock_path_manager: MagicMock,
        metadata_index_data: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        # Write index file.
        index_path = mock_path_manager.unified_metadata_index.return_value
        index_path.write_text(json.dumps(metadata_index_data), encoding="utf-8")

        server = MetadataServer(path_manager=mock_path_manager)
        result = await server.get_metadata(
            object_ref="Catalog.Товары",
            config_name="ut11",
            config_version="4.5.3",
        )
        assert result.object_ref == "Catalog.Товары"
        assert result.metadata.name == "Товары"
        assert result.metadata.metadata_type == "Catalog"

    @pytest.mark.asyncio
    async def test_get_metadata_index_not_found(self, mock_path_manager: MagicMock) -> None:
        # Файл не существует.
        server = MetadataServer(path_manager=mock_path_manager)
        with pytest.raises(IndexNotFoundError, match="unified-metadata-index.json not found"):
            await server.get_metadata("Catalog.Товары", "ut11", "4.5.3")

    @pytest.mark.asyncio
    async def test_get_metadata_object_not_found(
        self,
        mock_path_manager: MagicMock,
        metadata_index_data: dict[str, Any],
    ) -> None:
        index_path = mock_path_manager.unified_metadata_index.return_value
        index_path.write_text(json.dumps(metadata_index_data), encoding="utf-8")

        server = MetadataServer(path_manager=mock_path_manager)
        with pytest.raises(MetadataNotFoundError, match="not found in index"):
            await server.get_metadata("Catalog.Несуществующий", "ut11", "4.5.3")

    @pytest.mark.asyncio
    async def test_get_metadata_common_module(
        self,
        mock_path_manager: MagicMock,
        metadata_index_data: dict[str, Any],
    ) -> None:
        index_path = mock_path_manager.unified_metadata_index.return_value
        index_path.write_text(json.dumps(metadata_index_data), encoding="utf-8")

        server = MetadataServer(path_manager=mock_path_manager)
        result = await server.get_metadata("CommonModule.ОбщегоНазначения", "ut11", "4.5.3")
        assert result.metadata.name == "ОбщегоНазначения"
        assert result.metadata.metadata_type == "CommonModule"


# ─── get_api_reference ───────────────────────────────────────────────────────


class TestGetApiReference:
    @pytest.mark.asyncio
    async def test_get_api_reference_happy_path(
        self,
        mock_path_manager: MagicMock,
        api_reference_data: dict[str, Any],
    ) -> None:
        api_path = mock_path_manager.api_reference_index.return_value
        api_path.write_text(json.dumps(api_reference_data), encoding="utf-8")

        server = MetadataServer(path_manager=mock_path_manager)
        result = await server.get_api_reference(
            module_name="ОбщегоНазначения",
            config_name="ut11",
            config_version="4.5.3",
        )
        assert result.module_name == "ОбщегоНазначения"
        assert len(result.methods) == 2
        assert result.methods[0]["name"] == "ВыполнитьЗапрос"

    @pytest.mark.asyncio
    async def test_get_api_reference_index_not_found(self, mock_path_manager: MagicMock) -> None:
        server = MetadataServer(path_manager=mock_path_manager)
        with pytest.raises(IndexNotFoundError, match="api-reference.json not found"):
            await server.get_api_reference("ОбщегоНазначения", "ut11", "4.5.3")

    @pytest.mark.asyncio
    async def test_get_api_reference_module_not_found(
        self,
        mock_path_manager: MagicMock,
        api_reference_data: dict[str, Any],
    ) -> None:
        api_path = mock_path_manager.api_reference_index.return_value
        api_path.write_text(json.dumps(api_reference_data), encoding="utf-8")

        server = MetadataServer(path_manager=mock_path_manager)
        with pytest.raises(MetadataNotFoundError, match="not found in api-reference"):
            await server.get_api_reference("НесуществующийМодуль", "ut11", "4.5.3")

    @pytest.mark.asyncio
    async def test_get_api_reference_module_no_methods(
        self,
        mock_path_manager: MagicMock,
        api_reference_data: dict[str, Any],
    ) -> None:
        """Модуль существует, но export_methods=[] → MetadataNotFoundError."""
        api_path = mock_path_manager.api_reference_index.return_value
        api_path.write_text(json.dumps(api_reference_data), encoding="utf-8")

        server = MetadataServer(path_manager=mock_path_manager)
        with pytest.raises(MetadataNotFoundError, match="no export methods"):
            await server.get_api_reference("ДругойМодуль", "ut11", "4.5.3")


# ─── get_dependency_graph ────────────────────────────────────────────────────


class TestGetDependencyGraph:
    @pytest.mark.asyncio
    async def test_get_dependency_graph_depends_on(
        self,
        mock_path_manager: MagicMock,
        dependency_graph_data: dict[str, Any],
    ) -> None:
        dep_path = mock_path_manager.dependency_graph_index.return_value
        dep_path.write_text(json.dumps(dependency_graph_data), encoding="utf-8")

        server = MetadataServer(path_manager=mock_path_manager)
        result = await server.get_dependency_graph(
            config_name="ut11",
            config_version="4.5.3",
            object_ref="Catalog.Товары",
            direction="depends_on",
            depth=1,
        )
        assert result.object_ref == "Catalog.Товары"
        # Catalog.Товары → Catalog.Контрагенты (1 edge).
        assert len(result.edges) == 1
        assert str(result.edges[0].target) == "Catalog.Контрагенты"

    @pytest.mark.asyncio
    async def test_get_dependency_graph_depended_by(
        self,
        mock_path_manager: MagicMock,
        dependency_graph_data: dict[str, Any],
    ) -> None:
        dep_path = mock_path_manager.dependency_graph_index.return_value
        dep_path.write_text(json.dumps(dependency_graph_data), encoding="utf-8")

        server = MetadataServer(path_manager=mock_path_manager)
        result = await server.get_dependency_graph(
            config_name="ut11",
            config_version="4.5.3",
            object_ref="Catalog.Товары",
            direction="depended_by",
            depth=1,
        )
        # Document.Продажа → Catalog.Товары (1 edge).
        assert len(result.edges) == 1
        assert str(result.edges[0].source) == "Document.Продажа"

    @pytest.mark.asyncio
    async def test_get_dependency_graph_whole_graph(
        self,
        mock_path_manager: MagicMock,
        dependency_graph_data: dict[str, Any],
    ) -> None:
        dep_path = mock_path_manager.dependency_graph_index.return_value
        dep_path.write_text(json.dumps(dependency_graph_data), encoding="utf-8")

        server = MetadataServer(path_manager=mock_path_manager)
        result = await server.get_dependency_graph(
            config_name="ut11",
            config_version="4.5.3",
            object_ref=None,
        )
        assert result.object_ref is None
        assert len(result.edges) == 2
        assert result.stats["total_edges"] == 2

    @pytest.mark.asyncio
    async def test_get_dependency_graph_index_not_found(self, mock_path_manager: MagicMock) -> None:
        server = MetadataServer(path_manager=mock_path_manager)
        with pytest.raises(IndexNotFoundError, match="dependency-graph.json not found"):
            await server.get_dependency_graph("ut11", "4.5.3", object_ref="Catalog.Товары")

    @pytest.mark.asyncio
    async def test_get_dependency_graph_object_not_found(
        self,
        mock_path_manager: MagicMock,
        dependency_graph_data: dict[str, Any],
    ) -> None:
        dep_path = mock_path_manager.dependency_graph_index.return_value
        dep_path.write_text(json.dumps(dependency_graph_data), encoding="utf-8")

        server = MetadataServer(path_manager=mock_path_manager)
        with pytest.raises(MetadataNotFoundError, match="No dependencies found"):
            await server.get_dependency_graph(
                "ut11", "4.5.3", object_ref="Catalog.Несуществующий"
            )

    @pytest.mark.asyncio
    async def test_get_dependency_graph_invalid_direction(
        self,
        mock_path_manager: MagicMock,
        dependency_graph_data: dict[str, Any],
    ) -> None:
        dep_path = mock_path_manager.dependency_graph_index.return_value
        dep_path.write_text(json.dumps(dependency_graph_data), encoding="utf-8")

        server = MetadataServer(path_manager=mock_path_manager)
        with pytest.raises(Exception, match="Invalid direction"):
            await server.get_dependency_graph(
                "ut11",
                "4.5.3",
                object_ref="Catalog.Товары",
                direction="invalid",  # type: ignore[arg-type]
            )


# ─── get_form_structure ──────────────────────────────────────────────────────


class TestGetFormStructure:
    @pytest.mark.asyncio
    async def test_get_form_structure_form_not_found(
        self,
        mock_path_manager: MagicMock,
    ) -> None:
        server = MetadataServer(path_manager=mock_path_manager)
        with pytest.raises(MetadataNotFoundError, match="Form.xml not found"):
            await server.get_form_structure(
                object_ref="Catalog.Товары",
                form_name="ФормаСписка",
                config_name="ut11",
                config_version="4.5.3",
            )

    @pytest.mark.asyncio
    async def test_get_form_structure_invalid_object_ref(self, mock_path_manager: MagicMock) -> None:
        server = MetadataServer(path_manager=mock_path_manager)
        with pytest.raises(MetadataNotFoundError, match="Invalid object_ref"):
            await server.get_form_structure(
                object_ref="NoDot",
                form_name="ФормаСписка",
                config_name="ut11",
                config_version="4.5.3",
            )

    @pytest.mark.asyncio
    async def test_get_form_structure_happy_path(
        self,
        mock_path_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Form.xml существует → parse_form возвращает FormMetadata."""
        # Создаём Form.xml по ожидаемому пути.
        form_xml = (
            mock_path_manager.data_config_dir.return_value
            / "Catalogs"
            / "Товары"
            / "Forms"
            / "ФормаСписка.xml"
        )
        form_xml.parent.mkdir(parents=True, exist_ok=True)
        form_xml.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<MetaDataObject xmlns="http://v8.1c.ru/8.3/data/enterprise/current-config" xmlns:xs="http://www.w3.org/2001/XMLSchema">'
            '<Form><Name>ФормаСписка</Name><Synonym><key>ru</key><value>Форма списка</value></Synonym>'
            '<UseForFoldersAndItems>Items</UseForFoldersAndItems></Form></MetaDataObject>',
            encoding="utf-8",
        )

        # Mock parse_form чтобы не зависеть от реального парсера XML.
        from parsers.models import FormMetadata, ObjectRef

        mock_form = FormMetadata(
            object_ref=ObjectRef(type="Catalog", name="Товары"),
            form_name="ФормаСписка",
            title="Форма списка",
        )
        with patch("parsers.xml.parse_form", return_value=mock_form):
            server = MetadataServer(path_manager=mock_path_manager)
            result = await server.get_form_structure(
                object_ref="Catalog.Товары",
                form_name="ФормаСписка",
                config_name="ut11",
                config_version="4.5.3",
            )
        assert result.form_name == "ФормаСписка"
        assert result.form.title == "Форма списка"


# ─── Tool Implementations ────────────────────────────────────────────────────


class TestImplementations:
    """Обёртки GetMetadataImplementation / etc."""

    @pytest.mark.asyncio
    async def test_get_metadata_implementation(
        self,
        mock_path_manager: MagicMock,
        metadata_index_data: dict[str, Any],
    ) -> None:
        index_path = mock_path_manager.unified_metadata_index.return_value
        index_path.write_text(json.dumps(metadata_index_data), encoding="utf-8")

        impl = GetMetadataImplementation(server=MetadataServer(mock_path_manager))
        result = await impl(
            object_ref="Catalog.Товары",
            config_name="ut11",
            config_version="4.5.3",
        )
        assert result["object_ref"] == "Catalog.Товары"
        assert result["metadata"]["name"] == "Товары"

    @pytest.mark.asyncio
    async def test_get_api_reference_implementation(
        self,
        mock_path_manager: MagicMock,
        api_reference_data: dict[str, Any],
    ) -> None:
        api_path = mock_path_manager.api_reference_index.return_value
        api_path.write_text(json.dumps(api_reference_data), encoding="utf-8")

        impl = GetApiReferenceImplementation(server=MetadataServer(mock_path_manager))
        result = await impl(
            module_name="ОбщегоНазначения",
            config_name="ut11",
            config_version="4.5.3",
        )
        assert result["module_name"] == "ОбщегоНазначения"
        assert len(result["methods"]) == 2

    @pytest.mark.asyncio
    async def test_get_dependency_graph_implementation(
        self,
        mock_path_manager: MagicMock,
        dependency_graph_data: dict[str, Any],
    ) -> None:
        dep_path = mock_path_manager.dependency_graph_index.return_value
        dep_path.write_text(json.dumps(dependency_graph_data), encoding="utf-8")

        impl = GetDependencyGraphImplementation(server=MetadataServer(mock_path_manager))
        result = await impl(
            config_name="ut11",
            config_version="4.5.3",
            object_ref="Catalog.Товары",
            direction="depends_on",
            depth=1,
        )
        assert result["object_ref"] == "Catalog.Товары"
        assert len(result["edges"]) == 1

    @pytest.mark.asyncio
    async def test_implementation_validates_input(self) -> None:
        """Pydantic ValidationError при невалидном input."""
        from pydantic import ValidationError

        impl = GetMetadataImplementation(server=MagicMock())
        with pytest.raises(ValidationError):
            await impl(object_ref="X")  # нет config_name, config_version


# ─── Integration: Facade run_cli proxy metadata.* ────────────────────────────


class TestFacadeRunCliMetadataProxy:
    """Проверка что FacadeHandlers.run_cli проксирует metadata.* (Stage 4)."""

    @pytest.mark.asyncio
    async def test_run_cli_metadata_proxy(
        self,
        mock_path_manager: MagicMock,
        metadata_index_data: dict[str, Any],
    ) -> None:
        from mcp_servers.facade.handlers import FacadeHandlers

        index_path = mock_path_manager.unified_metadata_index.return_value
        index_path.write_text(json.dumps(metadata_index_data), encoding="utf-8")

        metadata_server = MetadataServer(path_manager=mock_path_manager)
        h = FacadeHandlers(metadata_server=metadata_server)
        result = await h.handle_run_cli(
            {
                "tool_name": "metadata.get_metadata",
                "args": {
                    "object_ref": "Catalog.Товары",
                    "config_name": "ut11",
                    "config_version": "4.5.3",
                },
            }
        )
        assert result["warning"] is None
        assert result["result"]["object_ref"] == "Catalog.Товары"
        assert result["result"]["metadata"]["name"] == "Товары"

    @pytest.mark.asyncio
    async def test_run_cli_metadata_not_configured_warning(self) -> None:
        """Без metadata_server → warning."""
        from mcp_servers.facade.handlers import FacadeHandlers

        h = FacadeHandlers()  # нет metadata_server
        result = await h.handle_run_cli(
            {"tool_name": "metadata.get_metadata", "args": {}}
        )
        assert result["warning"] is not None
        assert "not available" in result["warning"]

    @pytest.mark.asyncio
    async def test_run_cli_metadata_unknown_method(
        self,
        mock_path_manager: MagicMock,
    ) -> None:
        from mcp_servers.facade.handlers import FacadeHandlers

        metadata_server = MetadataServer(path_manager=mock_path_manager)
        h = FacadeHandlers(metadata_server=metadata_server)
        result = await h.handle_run_cli(
            {"tool_name": "metadata.unknown_method", "args": {}}
        )
        assert result["warning"] is not None
        assert "failed" in result["warning"]
