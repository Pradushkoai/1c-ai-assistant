"""Тесты для parsers.xml.form — парсер Form.xml → FormMetadata.

Sprint 4.1 (TD-S4.1-01): Form/Subsystem/Role парсеры для metadata MCP.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from parsers.xml import parse_form
from parsers.xml.form import _extract_v8_content, _guess_parent_from_path


# ─── Fixtures ────────────────────────────────────────────────────────────────


FORM_WRAPPER_XML = """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
  <Form uuid="test-uuid">
    <Properties>
      <Name>ФормаСписка</Name>
      <Synonym>
        <v8:item>
          <v8:lang>ru</v8:lang>
          <v8:content>Форма списка</v8:content>
        </v8:item>
      </Synonym>
      <Comment/>
      <FormType>Managed</FormType>
    </Properties>
  </Form>
</MetaDataObject>
"""

FORM_EXT_XML = """<?xml version="1.0"?>
<Form xmlns="http://v8.1c.ru/8.3/xcf/logform" xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <Title>
    <v8:item>
      <v8:lang>ru</v8:lang>
      <v8:content>Список товаров</v8:content>
    </v8:item>
  </Title>
  <AutoTitle>false</AutoTitle>
  <Events>
    <Event name="OnCreateAtServer">ПриСозданииНаСервере</Event>
    <Event name="OnOpen">ПриОткрытии</Event>
  </Events>
  <Attributes>
    <Attribute name="Список" id="1">
      <Type>v8:ValueListType</Type>
    </Attribute>
  </Attributes>
  <ChildItems>
    <InputField name="Наименование" id="2">
      <DataPath>Список.Наименование</DataPath>
      <Title>
        <v8:item>
          <v8:lang>ru</v8:lang>
          <v8:content>Наименование</v8:content>
        </v8:item>
      </Title>
      <Visible>true</Visible>
    </InputField>
    <UsualGroup name="ГруппаКнопок" id="3">
      <Title>
        <v8:item>
          <v8:lang>ru</v8:lang>
          <v8:content>Кнопки</v8:content>
        </v8:item>
      </Title>
      <ChildItems>
        <Button name="Выбрать" id="4">
          <Type>UsualButton</Type>
          <Title>
            <v8:item>
              <v8:lang>ru</v8:lang>
              <v8:content>Выбрать</v8:content>
            </v8:item>
          </Title>
        </Button>
      </ChildItems>
    </UsualGroup>
  </ChildItems>
</Form>
"""


@pytest.fixture
def form_dir(tmp_path: Path) -> Path:
    """Создать тестовую структуру формы в реальном формате 1С."""
    # Catalogs/Товары/Forms/ФормаСписка.xml (wrapper)
    forms_dir = tmp_path / "Catalogs" / "Товары" / "Forms"
    forms_dir.mkdir(parents=True)
    wrapper_path = forms_dir / "ФормаСписка.xml"
    wrapper_path.write_text(FORM_WRAPPER_XML, encoding="utf-8")

    # Catalogs/Товары/Forms/ФормаСписка/Ext/Form.xml (structure)
    ext_dir = forms_dir / "ФормаСписка" / "Ext"
    ext_dir.mkdir(parents=True)
    (ext_dir / "Form.xml").write_text(FORM_EXT_XML, encoding="utf-8")

    return wrapper_path


# ─── Tests: parse_form ──────────────────────────────────────────────────────


class TestParseForm:
    def test_form_name(self, form_dir: Path):
        form = parse_form(form_dir)
        assert form.form_name == "ФормаСписка"

    def test_title_from_ext(self, form_dir: Path):
        """Title берётся из Ext/Form.xml, не из wrapper synonym."""
        form = parse_form(form_dir)
        assert form.title == "Список товаров"

    def test_object_ref(self, form_dir: Path):
        form = parse_form(form_dir)
        assert form.object_ref.type == "Catalog"
        assert form.object_ref.name == "Товары"

    def test_handlers(self, form_dir: Path):
        form = parse_form(form_dir)
        assert "OnCreateAtServer" in form.handlers
        assert form.handlers["OnCreateAtServer"] == "ПриСозданииНаСервере"
        assert "OnOpen" in form.handlers
        assert form.handlers["OnOpen"] == "ПриОткрытии"

    def test_attributes(self, form_dir: Path):
        form = parse_form(form_dir)
        assert len(form.attributes) == 1
        assert form.attributes[0].name == "Список"

    def test_elements(self, form_dir: Path):
        form = parse_form(form_dir)
        assert len(form.elements) == 2
        # InputField
        inp = form.elements[0]
        assert inp.name == "Наименование"
        assert inp.type == "InputField"
        assert inp.data_path == "Список.Наименование"
        assert inp.title == "Наименование"
        assert inp.visible is True
        # UsualGroup
        group = form.elements[1]
        assert group.name == "ГруппаКнопок"
        assert group.type == "UsualGroup"
        assert len(group.children) == 1
        # Button внутри группы
        btn = group.children[0]
        assert btn.name == "Выбрать"
        assert btn.type == "Button"
        assert btn.title == "Выбрать"

    def test_wrapper_only_no_ext(self, tmp_path: Path):
        """Если Ext/Form.xml не существует — только wrapper данные."""
        forms_dir = tmp_path / "Documents" / "Продажа" / "Forms"
        forms_dir.mkdir(parents=True)
        wrapper = forms_dir / "ФормаДокумента.xml"
        wrapper.write_text(FORM_WRAPPER_XML.replace("ФормаСписка", "ФормаДокумента"), encoding="utf-8")

        form = parse_form(wrapper)
        assert form.form_name == "ФормаДокумента"
        assert form.title == "Форма списка"  # synonym из wrapper
        assert form.handlers == {}
        assert form.elements == []
        assert form.object_ref.type == "Document"
        assert form.object_ref.name == "Продажа"


# ─── Tests: _guess_parent_from_path ──────────────────────────────────────────


class TestGuessParentFromPath:
    def test_catalog(self):
        path = Path("/data/Catalogs/Товары/Forms/ФормаСписка.xml")
        parent_type, parent_name = _guess_parent_from_path(path)
        assert parent_type == "Catalog"
        assert parent_name == "Товары"

    def test_document(self):
        path = Path("/data/Documents/Продажа/Forms/ФормаДокумента.xml")
        parent_type, parent_name = _guess_parent_from_path(path)
        assert parent_type == "Document"
        assert parent_name == "Продажа"

    def test_common_form(self):
        path = Path("/data/CommonForms/МояФорма.xml")
        parent_type, parent_name = _guess_parent_from_path(path)
        assert parent_type == "CommonForm"
        assert parent_name == "МояФорма"

    def test_data_processor(self):
        path = Path("/data/DataProcessors/Обработка1/Forms/Форма.xml")
        parent_type, parent_name = _guess_parent_from_path(path)
        assert parent_type == "DataProcessor"
        assert parent_name == "Обработка1"


# ─── Tests: _extract_v8_content ──────────────────────────────────────────────


class TestExtractV8Content:
    def test_simple_text(self, tmp_path: Path):
        from parsers.xml._xml_utils import parse_xml_string

        root = parse_xml_string("<Title>Hello</Title>")
        assert _extract_v8_content(root) == "Hello"

    def test_v8_item_content(self, tmp_path: Path):
        from parsers.xml._xml_utils import parse_xml_string

        root = parse_xml_string(
            "<Title><v8:item><v8:lang>ru</v8:lang><v8:content>Привет</v8:content></v8:item></Title>"
        )
        assert _extract_v8_content(root) == "Привет"

    def test_empty(self, tmp_path: Path):
        from parsers.xml._xml_utils import parse_xml_string

        root = parse_xml_string("<Title></Title>")
        assert _extract_v8_content(root) is None
