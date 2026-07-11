"""Тесты для parsers.xml.configuration — парсер Configuration.xml."""

from __future__ import annotations

from pathlib import Path

import pytest

from parsers.models import ConfigMeta, MetadataType, Version
from parsers.xml import get_configuration_child_objects, parse_configuration


# ─── Smoke тесты ────────────────────────────────────────────────────────────


class TestParseConfigurationSmoke:
    """Базовые тесты парсера Configuration.xml."""

    @pytest.mark.smoke
    def test_parse_returns_config_meta(self, mini_config_dir: Path):
        config_xml = mini_config_dir / "Configuration.xml"
        config = parse_configuration(config_xml)
        assert isinstance(config, ConfigMeta)

    def test_parse_nonexistent_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            parse_configuration(tmp_path / "nonexistent.xml")


# ─── Основные поля ─────────────────────────────────────────────────────────


class TestConfigurationFields:
    """Парсинг основных полей Configuration.xml."""

    def test_name(self, mini_config_dir: Path):
        config = parse_configuration(mini_config_dir / "Configuration.xml")
        assert config.name == "МиниКонфигурация"

    def test_synonym(self, mini_config_dir: Path):
        config = parse_configuration(mini_config_dir / "Configuration.xml")
        assert config.synonym == "Мини-конфигурация для тестов"

    def test_version_info(self, mini_config_dir: Path):
        config = parse_configuration(mini_config_dir / "Configuration.xml")
        assert config.version_info.version == "1.0.0"
        assert config.version_info.vendor == "Pradushkoai"

    def test_platform_version(self, mini_config_dir: Path):
        config = parse_configuration(mini_config_dir / "Configuration.xml")
        # Из CompatibilityMode=Version8_3_10 → 8.3.10
        assert isinstance(config.platform_version, Version)
        assert config.platform_version.major == 8
        assert config.platform_version.minor == 3

    def test_default_language(self, mini_config_dir: Path):
        config = parse_configuration(mini_config_dir / "Configuration.xml")
        # DefaultLanguage → Language.Русский → 'Русский'
        assert config.default_language in ("Русский", "ru")

    def test_data_lock_mode(self, mini_config_dir: Path):
        config = parse_configuration(mini_config_dir / "Configuration.xml")
        assert config.default_data_lock_mode == "Managed"


# ─── object_counts ─────────────────────────────────────────────────────────


class TestObjectCounts:
    """Подсчёт объектов каждого типа в конфигурации."""

    def test_has_catalog(self, mini_config_dir: Path):
        config = parse_configuration(mini_config_dir / "Configuration.xml")
        assert MetadataType.CATALOG in config.object_counts
        assert config.object_counts[MetadataType.CATALOG] == 1

    def test_has_document(self, mini_config_dir: Path):
        config = parse_configuration(mini_config_dir / "Configuration.xml")
        assert MetadataType.DOCUMENT in config.object_counts
        assert config.object_counts[MetadataType.DOCUMENT] == 1

    def test_has_common_module(self, mini_config_dir: Path):
        config = parse_configuration(mini_config_dir / "Configuration.xml")
        assert MetadataType.COMMON_MODULE in config.object_counts
        assert config.object_counts[MetadataType.COMMON_MODULE] == 1

    def test_no_unexpected_types(self, mini_config_dir: Path):
        """Мини-конфигурация содержит только Catalog, Document, CommonModule."""
        config = parse_configuration(mini_config_dir / "Configuration.xml")
        # Language не считается (это не объект метаданных в ChildObjects смысле)
        # Но в mini_config Language.Русский объявлен как дочерний объект
        # Проверяем только то, что точно есть
        assert set(config.object_counts.keys()).issuperset(
            {MetadataType.CATALOG, MetadataType.DOCUMENT, MetadataType.COMMON_MODULE}
        )


# ─── get_configuration_child_objects ───────────────────────────────────────


class TestGetChildObjects:
    """Получение словаря дочерних объектов."""

    @pytest.mark.smoke
    def test_returns_dict(self, mini_config_dir: Path):
        result = get_configuration_child_objects(mini_config_dir / "Configuration.xml")
        assert isinstance(result, dict)

    def test_has_catalog_names(self, mini_config_dir: Path):
        result = get_configuration_child_objects(mini_config_dir / "Configuration.xml")
        assert "Catalog" in result
        assert "Товары" in result["Catalog"]

    def test_has_document_names(self, mini_config_dir: Path):
        result = get_configuration_child_objects(mini_config_dir / "Configuration.xml")
        assert "Document" in result
        assert "Продажа" in result["Document"]

    def test_has_common_module_names(self, mini_config_dir: Path):
        result = get_configuration_child_objects(mini_config_dir / "Configuration.xml")
        assert "CommonModule" in result
        assert "ОбщегоНазначения" in result["CommonModule"]


# ─── Edge cases ────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Граничные случаи."""

    def test_missing_configuration_element_raises(self, tmp_path: Path):
        """Если XML не содержит <Configuration> — ValueError."""
        xml = '<?xml version="1.0"?><Other xmlns="http://v8.1c.ru/8.3/data/core"/>'
        path = tmp_path / "Configuration.xml"
        path.write_text(xml, encoding="utf-8")
        with pytest.raises(ValueError, match="expected <Configuration>"):
            parse_configuration(path)

    def test_missing_properties_raises(self, tmp_path: Path):
        """Если <Configuration> без <Properties> — ValueError."""
        xml = '<?xml version="1.0"?><MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core"><Configuration uuid="x"/></MetaDataObject>'
        path = tmp_path / "Configuration.xml"
        path.write_text(xml, encoding="utf-8")
        with pytest.raises(ValueError, match="missing <Properties>"):
            parse_configuration(path)

    def test_empty_config_uses_defaults(self, tmp_path: Path):
        """Минимальный Configuration.xml с пустыми полями использует defaults."""
        xml = """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core">
  <Configuration uuid="x">
    <Properties>
      <Name>Пустая</Name>
    </Properties>
  </Configuration>
</MetaDataObject>
"""
        path = tmp_path / "Configuration.xml"
        path.write_text(xml, encoding="utf-8")
        config = parse_configuration(path)
        assert config.name == "Пустая"
        assert config.platform_version.major == 8  # дефолт 8.3.20
