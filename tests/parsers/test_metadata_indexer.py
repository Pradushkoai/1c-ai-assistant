"""Тесты для parsers.indexers.metadata_indexer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from parsers.indexers import (
    build_metadata_index,
    get_object_from_index,
    load_metadata_index,
    save_metadata_index,
)


# ─── Smoke ─────────────────────────────────────────────────────────────────


class TestBuildMetadataIndexSmoke:
    """Базовые тесты build_metadata_index."""

    @pytest.mark.smoke
    def test_build_returns_dict(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        assert isinstance(index, dict)

    def test_build_nonexistent_dir_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="Config directory not found"):
            build_metadata_index(tmp_path / "nonexistent", "x", "1.0")

    def test_build_missing_configuration_raises(self, tmp_path: Path):
        """Если Configuration.xml отсутствует — ValueError."""
        with pytest.raises(ValueError, match="Configuration.xml not found"):
            build_metadata_index(tmp_path, "x", "1.0")


# ─── Структура индекса ─────────────────────────────────────────────────────


class TestIndexStructure:
    """Структура возвращаемого индекса."""

    def test_has_required_keys(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        assert "config_meta" in index
        assert "objects" in index
        assert "stats" in index
        assert "generated_at" in index
        assert "config_name" in index
        assert "config_version" in index

    def test_config_name_and_version(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        assert index["config_name"] == "mini"
        assert index["config_version"] == "1.0"

    def test_config_meta_present(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        cm = index["config_meta"]
        assert cm["name"] == "МиниКонфигурация"
        assert cm["version_info"]["version"] == "1.0.0"

    def test_generated_at_is_iso(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        # ISO 8601: 2026-07-11T... (с timezone)
        assert "T" in index["generated_at"]


# ─── Objects ────────────────────────────────────────────────────────────────


class TestIndexObjects:
    """Объекты в индексе."""

    def test_has_catalog(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        assert "Catalog" in index["objects"]
        assert len(index["objects"]["Catalog"]) == 1

    def test_has_document(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        assert "Document" in index["objects"]
        assert len(index["objects"]["Document"]) == 1

    def test_has_common_module(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        assert "CommonModule" in index["objects"]
        assert len(index["objects"]["CommonModule"]) == 1

    def test_catalog_has_correct_name(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        catalog = index["objects"]["Catalog"][0]
        assert catalog["name"] == "Товары"

    def test_document_has_correct_name(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        document = index["objects"]["Document"][0]
        assert document["name"] == "Продажа"

    def test_common_module_has_correct_name(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        cm = index["objects"]["CommonModule"][0]
        assert cm["name"] == "ОбщегоНазначения"

    def test_catalog_has_attributes(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        catalog = index["objects"]["Catalog"][0]
        assert len(catalog["attributes"]) >= 2
        names = [a["name"] for a in catalog["attributes"]]
        assert "Артикул" in names
        assert "Цена" in names

    def test_document_has_register_records(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        document = index["objects"]["Document"][0]
        assert len(document["register_records"]) >= 1
        assert any("Продажи" in r for r in document["register_records"])

    def test_common_module_has_server_flag(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        cm = index["objects"]["CommonModule"][0]
        assert cm["server"] is True


# ─── Stats ─────────────────────────────────────────────────────────────────


class TestIndexStats:
    """Статистика в индексе."""

    def test_total_objects(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        # mini_config: 1 Catalog + 1 Document + 1 CommonModule = 3
        assert index["stats"]["total_objects"] == 3

    def test_by_type(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        by_type = index["stats"]["by_type"]
        assert by_type["Catalog"] == 1
        assert by_type["Document"] == 1
        assert by_type["CommonModule"] == 1

    def test_no_parse_errors_for_valid_config(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        assert index["stats"]["parse_errors"] == []


# ─── Persistence ──────────────────────────────────────────────────────────


class TestSaveLoadIndex:
    """Сохранение и загрузка индекса."""

    def test_save_creates_file(self, tmp_path: Path, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        output = tmp_path / "index.json"
        save_metadata_index(index, output)
        assert output.exists()

    def test_save_creates_parent_dir(self, tmp_path: Path, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        output = tmp_path / "nested" / "deep" / "index.json"
        save_metadata_index(index, output)
        assert output.exists()

    def test_load_returns_dict(self, tmp_path: Path, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        output = tmp_path / "index.json"
        save_metadata_index(index, output)

        loaded = load_metadata_index(output)
        assert loaded is not None
        assert loaded["config_name"] == "mini"
        assert loaded["stats"]["total_objects"] == 3

    def test_load_nonexistent_returns_none(self, tmp_path: Path):
        loaded = load_metadata_index(tmp_path / "nonexistent.json")
        assert loaded is None

    def test_round_trip_preserves_data(self, tmp_path: Path, mini_config_dir: Path):
        """Save → load → сравнение."""
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        output = tmp_path / "index.json"
        save_metadata_index(index, output)

        loaded = load_metadata_index(output)
        assert loaded is not None
        # Сравниваем по существенным полям (generated_at отличается при reload)
        assert loaded["config_name"] == index["config_name"]
        assert loaded["stats"]["total_objects"] == index["stats"]["total_objects"]
        assert loaded["stats"]["by_type"] == index["stats"]["by_type"]

    def test_save_is_valid_json(self, tmp_path: Path, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        output = tmp_path / "index.json"
        save_metadata_index(index, output)

        # Проверяем, что файл — валидный JSON
        data = json.loads(output.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "objects" in data

    def test_save_preserves_cyrillic(self, tmp_path: Path, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        output = tmp_path / "index.json"
        save_metadata_index(index, output)

        # ensure_ascii=False — кириллица должна быть видна напрямую
        raw = output.read_text(encoding="utf-8")
        assert "Товары" in raw
        assert "Продажа" in raw
        assert "ОбщегоНазначения" in raw


# ─── get_object_from_index ─────────────────────────────────────────────────


class TestGetObjectFromIndex:
    """Поиск объекта в индексе по ссылке."""

    def test_find_catalog(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        obj = get_object_from_index(index, "Catalog.Товары")
        assert obj is not None
        assert obj["name"] == "Товары"

    def test_find_document(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        obj = get_object_from_index(index, "Document.Продажа")
        assert obj is not None
        assert obj["name"] == "Продажа"

    def test_find_common_module(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        obj = get_object_from_index(index, "CommonModule.ОбщегоНазначения")
        assert obj is not None
        assert obj["name"] == "ОбщегоНазначения"

    def test_find_nonexistent(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        assert get_object_from_index(index, "Catalog.Несуществующий") is None

    def test_find_invalid_ref(self, mini_config_dir: Path):
        index = build_metadata_index(mini_config_dir, "mini", "1.0")
        # Без точки — должно вернуть None
        assert get_object_from_index(index, "InvalidRef") is None


# ─── Универсальный парсер для неизвестных типов ────────────────────────────


class TestGenericParser:
    """Тест универсального парсера для типов без специализированного парсера."""

    def test_generic_object_parsed(self, tmp_path: Path):
        """Информация о регистре сведений парсится через универсальный парсер."""
        # Создаём минимальный InformationRegister.xml
        config_dir = tmp_path / "config"
        ir_dir = config_dir / "InformationRegisters"
        ir_dir.mkdir(parents=True)
        (ir_dir / "КурсыВалют.xml").write_text(
            """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core">
  <InformationRegister uuid="44444444-4444-4444-4444-444444444444">
    <Properties>
      <Name>КурсыВалют</Name>
      <Synonym>
        <v8:item>
          <v8:lang>ru</v8:lang>
          <v8:content>Курсы валют</v8:content>
        </v8:item>
      </Synonym>
      <Comment>Регистр сведений курсов валют</Comment>
    </Properties>
  </InformationRegister>
</MetaDataObject>
""",
            encoding="utf-8",
        )
        # Configuration.xml нужен для build_metadata_index
        (config_dir / "Configuration.xml").write_text(
            """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core">
  <Configuration uuid="x">
    <Properties>
      <Name>Test</Name>
      <Version>1.0</Version>
    </Properties>
  </Configuration>
</MetaDataObject>
""",
            encoding="utf-8",
        )

        index = build_metadata_index(config_dir, "test", "1.0")

        # InformationRegister должен попасть в индекс через универсальный парсер
        assert "InformationRegister" in index["objects"]
        ir = index["objects"]["InformationRegister"][0]
        assert ir["name"] == "КурсыВалют"
        assert ir["synonym"] == "Курсы валют"
        assert ir["comment"] == "Регистр сведений курсов валют"
        assert ir["object_ref"]["type"] == "InformationRegister"
        assert ir["object_ref"]["name"] == "КурсыВалют"

    def test_generic_object_no_synonym(self, tmp_path: Path):
        """Объект без синонима — synonym=None."""
        config_dir = tmp_path / "config"
        enum_dir = config_dir / "Enums"
        enum_dir.mkdir(parents=True)
        (enum_dir / "СтатусыДокумента.xml").write_text(
            """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core">
  <Enum uuid="55555555-5555-5555-5555-555555555555">
    <Properties>
      <Name>СтатусыДокумента</Name>
    </Properties>
  </Enum>
</MetaDataObject>
""",
            encoding="utf-8",
        )
        (config_dir / "Configuration.xml").write_text(
            """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core">
  <Configuration uuid="x">
    <Properties><Name>Test</Name><Version>1.0</Version></Properties>
  </Configuration>
</MetaDataObject>
""",
            encoding="utf-8",
        )

        index = build_metadata_index(config_dir, "test", "1.0")
        assert "Enum" in index["objects"]
        obj = index["objects"]["Enum"][0]
        assert obj["name"] == "СтатусыДокумента"
        assert obj["synonym"] is None


# ─── Устойчивость к ошибкам ────────────────────────────────────────────────


class TestErrorHandling:
    """Устойчивость к повреждённым XML."""

    def test_invalid_xml_recorded_in_errors(self, tmp_path: Path):
        """Повреждённый XML — не падает, записывается в parse_errors."""
        config_dir = tmp_path / "config"
        bad_dir = config_dir / "Catalogs"  # та же что good_dir
        bad_dir.mkdir(parents=True)
        # Полностью сломанный XML
        (bad_dir / "Плохой.xml").write_text(
            "NOT VALID XML AT ALL <<<<",
            encoding="utf-8",
        )
        (config_dir / "Configuration.xml").write_text(
            """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core">
  <Configuration uuid="x">
    <Properties><Name>Test</Name><Version>1.0</Version></Properties>
  </Configuration>
</MetaDataObject>
""",
            encoding="utf-8",
        )

        # Не должно падать
        index = build_metadata_index(config_dir, "test", "1.0")

        # Должна быть запись об ошибке
        assert len(index["stats"]["parse_errors"]) >= 1
        assert index["stats"]["parse_errors"][0]["name"] == "Плохой"

    def test_one_bad_xml_does_not_block_others(self, tmp_path: Path):
        """Один плохой XML не мешает парсить остальные."""
        config_dir = tmp_path / "config"

        # Хорошая конфигурация
        good_dir = config_dir / "Catalogs"
        good_dir.mkdir(parents=True)
        (good_dir / "Хороший.xml").write_text(
            """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core">
  <Catalog uuid="x">
    <Properties><Name>Хороший</Name><CodeLength>9</CodeLength></Properties>
  </Catalog>
</MetaDataObject>
""",
            encoding="utf-8",
        )

        # Плохая конфигурация (в той же директории Catalogs/, рядом с хорошим)
        (good_dir / "Плохой.xml").write_text("INVALID XML", encoding="utf-8")

        (config_dir / "Configuration.xml").write_text(
            """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/data/core">
  <Configuration uuid="x">
    <Properties><Name>Test</Name><Version>1.0</Version></Properties>
  </Configuration>
</MetaDataObject>
""",
            encoding="utf-8",
        )

        index = build_metadata_index(config_dir, "test", "1.0")

        # Хороший объект должен быть в индексе
        assert "Catalog" in index["objects"]
        assert any(c["name"] == "Хороший" for c in index["objects"]["Catalog"])

        # Плохой должен быть в ошибках
        assert any(e["name"] == "Плохой" for e in index["stats"]["parse_errors"])
