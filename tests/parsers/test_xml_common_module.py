"""Тесты для parsers.xml.common_module — парсер CommonModule.xml."""

from __future__ import annotations

from pathlib import Path

import pytest

from parsers.models import CommonModuleMetadata, MetadataType
from parsers.xml import parse_common_module


# ─── Smoke ─────────────────────────────────────────────────────────────────


class TestParseCommonModuleSmoke:
    """Базовые тесты."""

    @pytest.mark.smoke
    def test_parse_returns_common_module_metadata(self, mini_config_dir: Path):
        path = mini_config_dir / "CommonModules" / "ОбщегоНазначения" / "ОбщегоНазначения.xml"
        cm = parse_common_module(path)
        assert isinstance(cm, CommonModuleMetadata)

    def test_parse_nonexistent_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            parse_common_module(tmp_path / "nonexistent.xml")


# ─── Основные поля ─────────────────────────────────────────────────────────


class TestCommonModuleFields:
    """Парсинг основных полей CommonModule.xml."""

    def test_name(self, mini_config_dir: Path):
        path = mini_config_dir / "CommonModules" / "ОбщегоНазначения" / "ОбщегоНазначения.xml"
        cm = parse_common_module(path)
        assert cm.name == "ОбщегоНазначения"

    def test_synonym(self, mini_config_dir: Path):
        path = mini_config_dir / "CommonModules" / "ОбщегоНазначения" / "ОбщегоНазначения.xml"
        cm = parse_common_module(path)
        assert cm.synonym == "Общего назначения"

    def test_comment(self, mini_config_dir: Path):
        path = mini_config_dir / "CommonModules" / "ОбщегоНазначения" / "ОбщегоНазначения.xml"
        cm = parse_common_module(path)
        assert cm.comment == "Общие функции"

    def test_metadata_type(self, mini_config_dir: Path):
        path = mini_config_dir / "CommonModules" / "ОбщегоНазначения" / "ОбщегоНазначения.xml"
        cm = parse_common_module(path)
        assert cm.metadata_type == MetadataType.COMMON_MODULE

    def test_object_ref(self, mini_config_dir: Path):
        path = mini_config_dir / "CommonModules" / "ОбщегоНазначения" / "ОбщегоНазначения.xml"
        cm = parse_common_module(path)
        assert cm.object_ref.type == "CommonModule"
        assert cm.object_ref.name == "ОбщегоНазначения"


# ─── Флаги контекста ───────────────────────────────────────────────────────


class TestCommonModuleContextFlags:
    """Флаги контекста выполнения общего модуля."""

    def test_server(self, mini_config_dir: Path):
        """В мини-конфиге ОбщегоНазначения.server=True."""
        path = mini_config_dir / "CommonModules" / "ОбщегоНазначения" / "ОбщегоНазначения.xml"
        cm = parse_common_module(path)
        assert cm.server is True

    def test_global(self, mini_config_dir: Path):
        path = mini_config_dir / "CommonModules" / "ОбщегоНазначения" / "ОбщегоНазначения.xml"
        cm = parse_common_module(path)
        # В мини-конфиге Global=false
        assert cm.global_ is False

    def test_client(self, mini_config_dir: Path):
        path = mini_config_dir / "CommonModules" / "ОбщегоНазначения" / "ОбщегоНазначения.xml"
        cm = parse_common_module(path)
        assert cm.client is False

    def test_external_connection(self, mini_config_dir: Path):
        path = mini_config_dir / "CommonModules" / "ОбщегоНазначения" / "ОбщегоНазначения.xml"
        cm = parse_common_module(path)
        # В мини-конфиге ExternalConnection=true
        assert cm.external_connection is True

    def test_privileged(self, mini_config_dir: Path):
        path = mini_config_dir / "CommonModules" / "ОбщегоНазначения" / "ОбщегоНазначения.xml"
        cm = parse_common_module(path)
        assert cm.privileged is False


# ─── Edge cases ────────────────────────────────────────────────────────────


class TestCommonModuleEdgeCases:
    """Граничные случаи."""

    def test_missing_common_module_element_raises(self, tmp_path: Path):
        xml = '<?xml version="1.0"?><Other xmlns="http://v8.1c.ru/8.3/data/core"/>'
        path = tmp_path / "X.xml"
        path.write_text(xml, encoding="utf-8")
        with pytest.raises(ValueError, match="expected <CommonModule>"):
            parse_common_module(path)

    def test_minimal_common_module(self, tmp_path: Path):
        """Минимальный CommonModule.xml с одним полем Name."""
        xml = """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core">
  <CommonModule uuid="x">
    <Properties>
      <Name>Минимальный</Name>
    </Properties>
  </CommonModule>
</MetaDataObject>
"""
        path = tmp_path / "X.xml"
        path.write_text(xml, encoding="utf-8")
        cm = parse_common_module(path)
        assert cm.name == "Минимальный"
        # По умолчанию: server=True (для совместимости)
        assert cm.server is True
        assert cm.global_ is False
        assert cm.client is False

    def test_client_common_module(self, tmp_path: Path):
        """Клиентский общий модуль."""
        xml = """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core">
  <CommonModule uuid="x">
    <Properties>
      <Name>КлиентскийМодуль</Name>
      <Server>false</Server>
      <Client>true</Client>
      <ClientManagedApplication>true</ClientManagedApplication>
    </Properties>
  </CommonModule>
</MetaDataObject>
"""
        path = tmp_path / "X.xml"
        path.write_text(xml, encoding="utf-8")
        cm = parse_common_module(path)
        assert cm.server is False
        assert cm.client is True
        assert cm.client_managed_application is True
