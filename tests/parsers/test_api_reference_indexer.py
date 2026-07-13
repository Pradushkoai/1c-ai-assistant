"""Тесты для parsers.indexers.api_reference_indexer.

Sprint 4.1 (TD-S4.1-03): api-reference — export-методы конфигурации.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from parsers.indexers import (
    build_api_reference,
    get_methods_for_object,
    load_api_reference,
    save_api_reference,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Создать тестовую конфигурацию с BSL модулями."""
    # CommonModules/Модуль1/Ext/Module.bsl
    mod1_dir = tmp_path / "CommonModules" / "Модуль1" / "Ext"
    mod1_dir.mkdir(parents=True)
    (mod1_dir / "Module.bsl").write_text(
        "Функция МояФункция(А, Б) Экспорт\n\tВозврат А + Б;\nКонецФункции\n"
        'Процедура МояПроцедура() Экспорт\n\tСообщить("Hello");\nКонецПроцедуры\n'
        "Процедура ЛокальнаяПроцедура()\nКонецПроцедуры\n",
        encoding="utf-8",
    )

    # CommonModules/Модуль2/Ext/Module.bsl (без export методов)
    mod2_dir = tmp_path / "CommonModules" / "Модуль2" / "Ext"
    mod2_dir.mkdir(parents=True)
    (mod2_dir / "Module.bsl").write_text(
        "Процедура ЛокальнаяПроцедура()\nКонецПроцедуры\n",
        encoding="utf-8",
    )

    # Catalogs/Товары/Ext/ObjectModule.bsl
    cat_dir = tmp_path / "Catalogs" / "Товары" / "Ext"
    cat_dir.mkdir(parents=True)
    (cat_dir / "ObjectModule.bsl").write_text(
        "Функция ПолучитьЦену() Экспорт\n\tВозврат 100;\nКонецФункции\n",
        encoding="utf-8",
    )

    return tmp_path


# ─── Tests: build_api_reference ─────────────────────────────────────────────


class TestBuildApiReference:
    def test_returns_dict(self, config_dir: Path):
        result = build_api_reference(config_dir, "test", "1.0")
        assert isinstance(result, dict)

    def test_stats(self, config_dir: Path):
        result = build_api_reference(config_dir, "test", "1.0")
        # Модуль1 (2 export) + Товары (1 export). Модуль2 не попал (0 export).
        assert result["stats"]["total_modules"] == 2
        assert result["stats"]["total_export_methods"] == 3

    def test_config_name(self, config_dir: Path):
        result = build_api_reference(config_dir, "test", "1.0")
        assert result["config_name"] == "test"
        assert result["config_version"] == "1.0"

    def test_generated_at(self, config_dir: Path):
        result = build_api_reference(config_dir, "test", "1.0")
        assert "generated_at" in result

    def test_module_info(self, config_dir: Path):
        result = build_api_reference(config_dir, "test", "1.0")
        modules = result["modules"]
        # Модуль1
        mod1 = [m for m in modules if "Модуль1" in m["object_ref"]][0]
        assert mod1["module_kind"] == "CommonModule"
        assert mod1["object_ref"] == "CommonModule.Модуль1"
        assert len(mod1["export_methods"]) == 2

    def test_export_method_fields(self, config_dir: Path):
        result = build_api_reference(config_dir, "test", "1.0")
        mod1 = [m for m in result["modules"] if "Модуль1" in m["object_ref"]][0]
        func = [m for m in mod1["export_methods"] if m["name"] == "МояФункция"][0]
        assert func["is_function"] is True
        assert func["parameters"] == ["А", "Б"]

    def test_catalog_object_module(self, config_dir: Path):
        result = build_api_reference(config_dir, "test", "1.0")
        cat_mod = [m for m in result["modules"] if "Товары" in m["object_ref"]][0]
        assert cat_mod["module_kind"] == "ObjectModule"
        assert cat_mod["object_ref"] == "Catalog.Товары"

    def test_empty_dir(self, tmp_path: Path):
        result = build_api_reference(tmp_path, "test", "1.0")
        assert result["stats"]["total_modules"] == 0
        assert result["stats"]["total_export_methods"] == 0

    def test_nonexistent_dir(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            build_api_reference(tmp_path / "nonexistent", "test", "1.0")


# ─── Tests: save/load ───────────────────────────────────────────────────────


class TestSaveLoad:
    def test_save_creates_file(self, config_dir: Path, tmp_path: Path):
        result = build_api_reference(config_dir, "test", "1.0")
        out = tmp_path / "api-reference.json"
        save_api_reference(result, out)
        assert out.exists()

    def test_load_returns_dict(self, config_dir: Path, tmp_path: Path):
        result = build_api_reference(config_dir, "test", "1.0")
        out = tmp_path / "api-reference.json"
        save_api_reference(result, out)
        loaded = load_api_reference(out)
        assert loaded is not None
        assert loaded["config_name"] == "test"

    def test_load_nonexistent(self, tmp_path: Path):
        assert load_api_reference(tmp_path / "nonexistent.json") is None


# ─── Tests: get_methods_for_object ──────────────────────────────────────────


class TestGetMethodsForObject:
    def test_find_by_module(self, config_dir: Path):
        result = build_api_reference(config_dir, "test", "1.0")
        methods = get_methods_for_object(result, "CommonModule.Модуль1")
        assert len(methods) == 2
        names = [m["name"] for m in methods]
        assert "МояФункция" in names
        assert "МояПроцедура" in names

    def test_find_by_catalog(self, config_dir: Path):
        result = build_api_reference(config_dir, "test", "1.0")
        methods = get_methods_for_object(result, "Catalog.Товары")
        assert len(methods) == 1
        assert methods[0]["name"] == "ПолучитьЦену"

    def test_not_found(self, config_dir: Path):
        result = build_api_reference(config_dir, "test", "1.0")
        methods = get_methods_for_object(result, "CommonModule.Несуществующий")
        assert methods == []
