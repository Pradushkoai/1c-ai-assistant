"""Тесты для parsers.xml.document — парсер Document.xml."""

from __future__ import annotations

from pathlib import Path

import pytest

from parsers.models import AttributeKind, DocumentMetadata, MetadataType
from parsers.xml import parse_document


# ─── Smoke ─────────────────────────────────────────────────────────────────


class TestParseDocumentSmoke:
    """Базовые тесты."""

    @pytest.mark.smoke
    def test_parse_returns_document_metadata(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        assert isinstance(doc, DocumentMetadata)

    def test_parse_nonexistent_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            parse_document(tmp_path / "nonexistent.xml")


# ─── Основные поля ─────────────────────────────────────────────────────────


class TestDocumentFields:
    """Парсинг основных полей Document.xml."""

    def test_name(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        assert doc.name == "Продажа"

    def test_synonym(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        assert doc.synonym == "Продажа"

    def test_comment(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        assert doc.comment == "Документ продажи"

    def test_metadata_type(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        assert doc.metadata_type == MetadataType.DOCUMENT

    def test_object_ref(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        assert doc.object_ref.type == "Document"
        assert doc.object_ref.name == "Продажа"


# ─── Документ-специфичные поля ─────────────────────────────────────────────


class TestDocumentSpecific:
    """Поля, специфичные для документа."""

    def test_number_length(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        assert doc.number_length == 9

    def test_number_type(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        assert doc.number_type == "String"

    def test_posting(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        assert doc.posting == "Allow"

    def test_realtime_posting(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        # В мини-конфиге RealTimePosting=Allow
        assert doc.realtime_posting == "Allow"


# ─── Register records ──────────────────────────────────────────────────────


class TestDocumentRegisterRecords:
    """Регистры, по которым документ делает движения."""

    def test_has_register_records(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        assert len(doc.register_records) >= 1

    def test_register_records_content(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        # В мини-конфиге: <xr:Item>AccumulationRegister.Продажи</xr:Item>
        assert any("Продажи" in r for r in doc.register_records)


# ─── Атрибуты ──────────────────────────────────────────────────────────────


class TestDocumentAttributes:
    """Парсинг атрибутов документа."""

    def test_has_attributes(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        assert len(doc.attributes) >= 2  # Контрагент + Сумма

    def test_attribute_names(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        names = [a.name for a in doc.attributes]
        assert "Контрагент" in names
        assert "Сумма" in names

    def test_attribute_types(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        attr_by_name = {a.name: a for a in doc.attributes}

        # Контрагент — СправочникСсылка.Контрагенты
        assert "СправочникСсылка" in attr_by_name["Контрагент"].type
        # Сумма — Число
        assert attr_by_name["Сумма"].type == "Число"

    def test_attribute_kind(self, mini_config_dir: Path):
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        for attr in doc.attributes:
            assert attr.kind == AttributeKind.ATTRIBUTE

    def test_attribute_required(self, mini_config_dir: Path):
        """Контрагент имеет FillChecking=Show → required=True."""
        path = mini_config_dir / "Documents" / "Продажа.xml"
        doc = parse_document(path)
        attr_by_name = {a.name: a for a in doc.attributes}
        assert attr_by_name["Контрагент"].required is True


# ─── Edge cases ────────────────────────────────────────────────────────────


class TestDocumentEdgeCases:
    """Граничные случаи."""

    def test_missing_document_element_raises(self, tmp_path: Path):
        xml = '<?xml version="1.0"?><Other xmlns="http://v8.1c.ru/8.3/data/core"/>'
        path = tmp_path / "X.xml"
        path.write_text(xml, encoding="utf-8")
        with pytest.raises(ValueError, match="expected <Document>"):
            parse_document(path)

    def test_no_register_records_returns_empty_list(self, tmp_path: Path):
        """Документ без движений — пустой список."""
        xml = """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core">
  <Document uuid="x">
    <Properties>
      <Name>БезДвижений</Name>
      <NumberLength>9</NumberLength>
      <Posting>Allow</Posting>
    </Properties>
  </Document>
</MetaDataObject>
"""
        path = tmp_path / "X.xml"
        path.write_text(xml, encoding="utf-8")
        doc = parse_document(path)
        assert doc.register_records == []
        assert doc.name == "БезДвижений"
