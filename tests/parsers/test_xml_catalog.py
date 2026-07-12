"""Тесты для parsers.xml.catalog — парсер Catalog.xml."""

from __future__ import annotations

from pathlib import Path

import pytest

from parsers.models import AttributeKind, CatalogMetadata, MetadataType
from parsers.xml import parse_catalog


# ─── Smoke ─────────────────────────────────────────────────────────────────


class TestParseCatalogSmoke:
    """Базовые тесты."""

    @pytest.mark.smoke
    def test_parse_returns_catalog_metadata(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        assert isinstance(cat, CatalogMetadata)

    def test_parse_nonexistent_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            parse_catalog(tmp_path / "nonexistent.xml")


# ─── Основные поля ─────────────────────────────────────────────────────────


class TestCatalogFields:
    """Парсинг основных полей Catalog.xml."""

    def test_name(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        assert cat.name == "Товары"

    def test_synonym(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        assert cat.synonym == "Товары"

    def test_comment(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        assert cat.comment == "Справочник товаров"

    def test_metadata_type(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        assert cat.metadata_type == MetadataType.CATALOG

    def test_object_ref(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        assert cat.object_ref.type == "Catalog"
        assert cat.object_ref.name == "Товары"


# ─── Каталог-специфичные поля ──────────────────────────────────────────────


class TestCatalogSpecific:
    """Поля, специфичные для справочника."""

    def test_code_length(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        assert cat.code_length == 9

    def test_description_length(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        assert cat.description_length == 50

    def test_hierarchy_type(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        assert cat.hierarchy_type == "HierarchyItems"

    def test_code_series(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        assert cat.code_series == "WholeCatalog"


# ─── Атрибуты ──────────────────────────────────────────────────────────────


class TestCatalogAttributes:
    """Парсинг атрибутов (реквизитов) справочника."""

    def test_has_attributes(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        assert len(cat.attributes) >= 2  # Артикул + Цена

    def test_attribute_names(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        names = [a.name for a in cat.attributes]
        assert "Артикул" in names
        assert "Цена" in names

    def test_attribute_types(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        attr_by_name = {a.name: a for a in cat.attributes}

        # Артикул — строка (xs:string → Строка)
        assert attr_by_name["Артикул"].type == "Строка"
        # Цена — число (xs:decimal → Число)
        assert attr_by_name["Цена"].type == "Число"

    def test_attribute_kind(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        for attr in cat.attributes:
            assert attr.kind == AttributeKind.ATTRIBUTE
            assert attr.tabular_section is None

    def test_attribute_required(self, mini_config_dir: Path):
        """Артикул имеет FillChecking=Show → required=True."""
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        attr_by_name = {a.name: a for a in cat.attributes}
        assert attr_by_name["Артикул"].required is True
        assert attr_by_name["Артикул"].check is True


# ─── Forms, Templates, Commands ────────────────────────────────────────────


class TestCatalogChildObjects:
    """Дочерние объекты справочника (Forms, Templates, Commands)."""

    def test_forms_empty_by_default(self, mini_config_dir: Path):
        """В мини-конфигурации у справочника Товары нет форм."""
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        assert cat.forms == []

    def test_templates_empty_by_default(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        assert cat.templates == []

    def test_commands_empty_by_default(self, mini_config_dir: Path):
        path = mini_config_dir / "Catalogs" / "Товары.xml"
        cat = parse_catalog(path)
        assert cat.commands == []


# ─── Edge cases ────────────────────────────────────────────────────────────


class TestCatalogEdgeCases:
    """Граничные случаи."""

    def test_missing_catalog_element_raises(self, tmp_path: Path):
        xml = '<?xml version="1.0"?><Other xmlns="http://v8.1c.ru/8.3/data/core"/>'
        path = tmp_path / "X.xml"
        path.write_text(xml, encoding="utf-8")
        with pytest.raises(ValueError, match="expected <Catalog>"):
            parse_catalog(path)

    def test_missing_properties_raises(self, tmp_path: Path):
        xml = '<?xml version="1.0"?><MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core"><Catalog uuid="x"/></MetaDataObject>'
        path = tmp_path / "X.xml"
        path.write_text(xml, encoding="utf-8")
        with pytest.raises(ValueError, match="missing <Properties>"):
            parse_catalog(path)

    def test_no_attributes_returns_empty_list(self, tmp_path: Path):
        """Справочник без атрибутов — пустой список."""
        xml = """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core">
  <Catalog uuid="x">
    <Properties>
      <Name>Пустой</Name>
      <CodeLength>9</CodeLength>
      <DescriptionLength>50</DescriptionLength>
    </Properties>
  </Catalog>
</MetaDataObject>
"""
        path = tmp_path / "Пустой.xml"
        path.write_text(xml, encoding="utf-8")
        cat = parse_catalog(path)
        assert cat.attributes == []
        assert cat.name == "Пустой"
