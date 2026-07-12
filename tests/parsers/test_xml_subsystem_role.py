"""Тесты для parsers.xml.subsystem_role — Subsystem и Role парсеры.

Sprint 4.1 (TD-S4.1-01).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from parsers.xml import parse_role, parse_subsystem


# ─── Fixtures ────────────────────────────────────────────────────────────────


SUBSYSTEM_XML = """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:xr="http://v8.1c.ru/8.3/xcf/readable" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Subsystem uuid="test-uuid">
    <Properties>
      <Name>Продажи</Name>
      <Synonym>
        <v8:item>
          <v8:lang>ru</v8:lang>
          <v8:content>Продажи</v8:content>
        </v8:item>
      </Synonym>
      <Comment>Подсистема продаж</Comment>
      <Content>
        <xr:Item xsi:type="xr:MDObjectRef">Catalog.Товары</xr:Item>
        <xr:Item xsi:type="xr:MDObjectRef">Document.Продажа</xr:Item>
        <xr:Item xsi:type="xr:MDObjectRef">Report.АнализПродаж</xr:Item>
      </Content>
    </Properties>
  </Subsystem>
</MetaDataObject>
"""

ROLE_XML = """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
  <Role uuid="role-uuid">
    <Properties>
      <Name>ПолныеПрава</Name>
      <Synonym>
        <v8:item>
          <v8:lang>ru</v8:lang>
          <v8:content>Полные права</v8:content>
        </v8:item>
      </Synonym>
      <Comment>Административные права</Comment>
    </Properties>
  </Role>
</MetaDataObject>
"""


@pytest.fixture
def subsystem_path(tmp_path: Path) -> Path:
    path = tmp_path / "Продажи.xml"
    path.write_text(SUBSYSTEM_XML, encoding="utf-8")
    return path


@pytest.fixture
def role_path(tmp_path: Path) -> Path:
    path = tmp_path / "ПолныеПрава.xml"
    path.write_text(ROLE_XML, encoding="utf-8")
    return path


# ─── Tests: parse_subsystem ─────────────────────────────────────────────────


class TestParseSubsystem:
    def test_name(self, subsystem_path: Path):
        sub = parse_subsystem(subsystem_path)
        assert sub.name == "Продажи"

    def test_synonym(self, subsystem_path: Path):
        sub = parse_subsystem(subsystem_path)
        assert sub.synonym == "Продажи"

    def test_comment(self, subsystem_path: Path):
        sub = parse_subsystem(subsystem_path)
        assert sub.comment == "Подсистема продаж"

    def test_content_count(self, subsystem_path: Path):
        sub = parse_subsystem(subsystem_path)
        assert len(sub.content) == 3

    def test_content_types(self, subsystem_path: Path):
        sub = parse_subsystem(subsystem_path)
        types = [ref.type for ref in sub.content]
        assert "Catalog" in types
        assert "Document" in types
        assert "Report" in types

    def test_content_names(self, subsystem_path: Path):
        sub = parse_subsystem(subsystem_path)
        names = [ref.name for ref in sub.content]
        assert "Товары" in names
        assert "Продажа" in names
        assert "АнализПродаж" in names

    def test_object_ref(self, subsystem_path: Path):
        sub = parse_subsystem(subsystem_path)
        assert sub.object_ref.type == "Subsystem"
        assert sub.object_ref.name == "Продажи"

    def test_metadata_type(self, subsystem_path: Path):
        sub = parse_subsystem(subsystem_path)
        assert sub.metadata_type == "Subsystem"

    def test_empty_content(self, tmp_path: Path):
        """Subsystem без Content — пустой список."""
        xml = SUBSYSTEM_XML.replace(
            '<Content>\n        <xr:Item xsi:type="xr:MDObjectRef">Catalog.Товары</xr:Item>\n        <xr:Item xsi:type="xr:MDObjectRef">Document.Продажа</xr:Item>\n        <xr:Item xsi:type="xr:MDObjectRef">Report.АнализПродаж</xr:Item>\n      </Content>',
            "",
        )
        path = tmp_path / "Empty.xml"
        path.write_text(xml, encoding="utf-8")
        sub = parse_subsystem(path)
        assert sub.content == []


# ─── Tests: parse_role ──────────────────────────────────────────────────────


class TestParseRole:
    def test_name(self, role_path: Path):
        role = parse_role(role_path)
        assert role.name == "ПолныеПрава"

    def test_synonym(self, role_path: Path):
        role = parse_role(role_path)
        assert role.synonym == "Полные права"

    def test_comment(self, role_path: Path):
        role = parse_role(role_path)
        assert role.comment == "Административные права"

    def test_object_ref(self, role_path: Path):
        role = parse_role(role_path)
        assert role.object_ref.type == "Role"
        assert role.object_ref.name == "ПолныеПрава"

    def test_metadata_type(self, role_path: Path):
        role = parse_role(role_path)
        assert role.metadata_type == "Role"

    def test_minimal_role(self, tmp_path: Path):
        """Role без синонима и комментария."""
        xml = """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
  <Role uuid="x">
    <Properties>
      <Name>МинимальнаяРоль</Name>
    </Properties>
  </Role>
</MetaDataObject>
"""
        path = tmp_path / "Min.xml"
        path.write_text(xml, encoding="utf-8")
        role = parse_role(path)
        assert role.name == "МинимальнаяРоль"
        assert role.synonym is None
        assert role.comment is None
