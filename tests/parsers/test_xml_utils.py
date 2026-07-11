"""Тесты для parsers.xml._xml_utils — общие утилиты XML парсинга."""

from __future__ import annotations

from pathlib import Path

import pytest

from parsers.xml import (
    extract_child_object_names,
    extract_child_object_refs,
    find_all,
    find_first,
    find_text,
    get_comment,
    get_name,
    get_synonym,
    iter_metadata_files,
    parse_xml,
    parse_xml_string,
)


# ─── parse_xml / parse_xml_string ──────────────────────────────────────────


class TestParseXml:
    """Парсинг XML файлов и строк."""

    @pytest.mark.smoke
    def test_parse_xml_file(self, mini_config_dir: Path):
        """Парсинг Configuration.xml из мини-конфигурации."""
        from parsers.xml._xml_utils import _local_name

        config_xml = mini_config_dir / "Configuration.xml"
        root = parse_xml(config_xml)
        assert root is not None
        # Корневой элемент — MetaDataObject (с namespace, но local-name = 'MetaDataObject')
        assert _local_name(root) == "MetaDataObject"

    def test_parse_xml_nonexistent_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="XML file not found"):
            parse_xml(tmp_path / "nonexistent.xml")

    def test_parse_xml_string_simple(self):
        root = parse_xml_string("<root><child>text</child></root>")
        assert root.tag == "root"
        assert root.find("child").text == "text"

    def test_parse_xml_string_with_cyrillic(self):
        root = parse_xml_string("<root><name>Товары</name></root>")
        assert find_text(root, "name") == "Товары"

    def test_parse_xml_recover_from_minor_errors(self):
        """recover=True — игнорировать мелкие ошибки."""
        # Незакрытый комментарий (1С иногда такое генерирует)
        xml = "<root><!-- unclosed comment <child>text</child></root>"
        root = parse_xml_string(xml)
        # Должно распарситься благодаря recover=True
        assert root.tag == "root"


# ─── find_text / find_all / find_first ─────────────────────────────────────


class TestFindFunctions:
    """Функции поиска элементов."""

    def test_find_text_existing(self):
        root = parse_xml_string("<root><Name>Товары</Name></root>")
        assert find_text(root, "Name") == "Товары"

    def test_find_text_missing_returns_default(self):
        root = parse_xml_string("<root></root>")
        assert find_text(root, "Name") is None
        assert find_text(root, "Name", default="default") == "default"

    def test_find_text_strips_whitespace(self):
        root = parse_xml_string("<root><Name>  Товары  </Name></root>")
        assert find_text(root, "Name") == "Товары"

    def test_find_text_empty_returns_default(self):
        root = parse_xml_string("<root><Name></Name></root>")
        assert find_text(root, "Name") is None
        assert find_text(root, "Name", default="def") == "def"

    def test_find_text_nested_path(self):
        xml = """
        <root>
          <Properties>
            <Name>Товары</Name>
          </Properties>
        </root>
        """
        root = parse_xml_string(xml)
        assert find_text(root, "Properties/Name") == "Товары"

    def test_find_all_returns_list(self):
        xml = """
        <root>
          <ChildObjects>
            <Form>ФормаСписка</Form>
            <Form>ФормаЭлемента</Form>
          </ChildObjects>
        </root>
        """
        root = parse_xml_string(xml)
        forms = find_all(root, "ChildObjects/Form")
        assert len(forms) == 2

    def test_find_all_empty(self):
        root = parse_xml_string("<root></root>")
        assert find_all(root, "Nonexistent") == []

    def test_find_first_returns_element_or_none(self):
        root = parse_xml_string("<root><Name>X</Name></root>")
        assert find_first(root, "Name") is not None
        assert find_first(root, "Nonexistent") is None


# ─── get_name / get_synonym / get_comment ──────────────────────────────────


class TestGetters:
    """Извлечение типичных полей 1С."""

    def test_get_name(self):
        xml = "<Properties><Name>Товары</Name></Properties>"
        root = parse_xml_string(xml)
        assert get_name(root) == "Товары"

    def test_get_name_missing(self):
        xml = "<Properties></Properties>"
        root = parse_xml_string(xml)
        assert get_name(root) is None

    def test_get_synonym_simple(self):
        """Синоним с v8:item структурой."""
        xml = """
        <Properties>
          <Synonym>
            <v8:item>
              <v8:lang>ru</v8:lang>
              <v8:content>Управление торговлей</v8:content>
            </v8:item>
          </Synonym>
        </Properties>
        """
        root = parse_xml_string(xml)
        assert get_synonym(root) == "Управление торговлей"

    def test_get_synonym_missing(self):
        xml = "<Properties></Properties>"
        root = parse_xml_string(xml)
        assert get_synonym(root) is None

    def test_get_synonym_multiple_items_returns_first(self):
        """Если несколько языков — берём первый."""
        xml = """
        <Properties>
          <Synonym>
            <v8:item>
              <v8:lang>en</v8:lang>
              <v8:content>Trade Management</v8:content>
            </v8:item>
            <v8:item>
              <v8:lang>ru</v8:lang>
              <v8:content>Управление торговлей</v8:content>
            </v8:item>
          </Synonym>
        </Properties>
        """
        root = parse_xml_string(xml)
        # Берём первый, который en
        assert get_synonym(root) == "Trade Management"

    def test_get_comment(self):
        xml = "<Properties><Comment>Справочник товаров</Comment></Properties>"
        root = parse_xml_string(xml)
        assert get_comment(root) == "Справочник товаров"

    def test_get_comment_missing(self):
        xml = "<Properties></Properties>"
        root = parse_xml_string(xml)
        assert get_comment(root) is None


# ─── extract_child_object_names / extract_child_object_refs ────────────────


class TestExtractChildObjects:
    """Извлечение имён дочерних объектов."""

    def test_extract_forms(self):
        xml = """
        <Catalog>
          <ChildObjects>
            <Form>ФормаСписка</Form>
            <Form>ФормаЭлемента</Form>
            <Form>ФормаВыбора</Form>
          </ChildObjects>
        </Catalog>
        """
        root = parse_xml_string(xml)
        forms = extract_child_object_names(root, "Form")
        assert forms == ["ФормаСписка", "ФормаЭлемента", "ФормаВыбора"]

    def test_extract_templates(self):
        xml = """
        <Document>
          <ChildObjects>
            <Template>МакетПечати</Template>
          </ChildObjects>
        </Document>
        """
        root = parse_xml_string(xml)
        templates = extract_child_object_names(root, "Template")
        assert templates == ["МакетПечати"]

    def test_extract_commands_empty(self):
        xml = "<Catalog><ChildObjects></ChildObjects></Catalog>"
        root = parse_xml_string(xml)
        assert extract_child_object_names(root, "Command") == []

    def test_extract_no_child_objects(self):
        xml = "<Catalog></Catalog>"
        root = parse_xml_string(xml)
        assert extract_child_object_names(root, "Form") == []

    def test_extract_child_object_refs_in_configuration(self):
        """В Configuration.xml дочерние объекты — это типы (Catalog, Document, ...)."""
        xml = """
        <Configuration>
          <ChildObjects>
            <Catalog>Товары</Catalog>
            <Document>Продажа</Document>
            <CommonModule>ОбщегоНазначения</CommonModule>
          </ChildObjects>
        </Configuration>
        """
        root = parse_xml_string(xml)
        catalogs = extract_child_object_refs(root, "Catalog")
        assert catalogs == ["Товары"]
        documents = extract_child_object_refs(root, "Document")
        assert documents == ["Продажа"]
        modules = extract_child_object_refs(root, "CommonModule")
        assert modules == ["ОбщегоНазначения"]


# ─── iter_metadata_files ────────────────────────────────────────────────────


class TestIterMetadataFiles:
    """Итератор по XML файлам метаданных."""

    @pytest.mark.smoke
    def test_iter_mini_config(self, mini_config_dir: Path):
        """Мини-конфигурация содержит Configuration + 3 объекта."""
        results = list(iter_metadata_files(mini_config_dir))

        # Должны быть: Configuration, Catalog.Товары, Document.Продажа, CommonModule.ОбщегоНазначения
        types = [r[0] for r in results]
        assert "Configuration" in types
        assert "Catalog" in types
        assert "Document" in types
        assert "CommonModule" in types

    def test_iter_returns_correct_names(self, mini_config_dir: Path):
        results = list(iter_metadata_files(mini_config_dir))
        names_by_type: dict[str, str] = {r[0]: r[1] for r in results if r[0] != "Configuration"}

        assert names_by_type.get("Catalog") == "Товары"
        assert names_by_type.get("Document") == "Продажа"
        assert names_by_type.get("CommonModule") == "ОбщегоНазначения"

    def test_iter_returns_existing_paths(self, mini_config_dir: Path):
        results = list(iter_metadata_files(mini_config_dir))
        for _type, _name, path in results:
            assert path.exists(), f"Path does not exist: {path}"

    def test_iter_empty_dir(self, tmp_path: Path):
        """Пустая директория — нет результатов."""
        results = list(iter_metadata_files(tmp_path))
        assert results == []

    def test_iter_only_configuration(self, tmp_path: Path):
        """Только Configuration.xml — один результат."""
        (tmp_path / "Configuration.xml").write_text(
            '<MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core"><Configuration uuid="x"/></MetaDataObject>',
            encoding="utf-8",
        )
        results = list(iter_metadata_files(tmp_path))
        assert len(results) == 1
        assert results[0][0] == "Configuration"
