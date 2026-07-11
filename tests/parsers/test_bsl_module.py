"""Тесты для parsers.bsl — парсер BSL-модулей."""

from __future__ import annotations

from pathlib import Path

import pytest

from parsers.bsl import (
    extract_export_methods,
    extract_method_signatures,
    parse_bsl_file,
    parse_bsl_module,
)
from parsers.models import BslModule, Method, ObjectRef, Region


# ─── parse_bsl_module — базовые ─────────────────────────────────────────────


class TestParseBslModuleSmoke:
    @pytest.mark.smoke
    def test_parse_empty_source(self):
        module = parse_bsl_module("", "CommonModule.Пустой")
        assert module.line_count == 0
        assert module.methods == []
        assert module.regions == []

    def test_parse_returns_bsl_module(self):
        module = parse_bsl_module(
            "Процедура Тест() КонецПроцедуры",
            "CommonModule.Тест",
        )
        assert isinstance(module, BslModule)

    def test_object_ref_from_string(self):
        module = parse_bsl_module("// empty", "Catalog.Товары")
        assert module.object_ref.type == "Catalog"
        assert module.object_ref.name == "Товары"

    def test_object_ref_from_object(self):
        ref = ObjectRef.from_string("Document.Продажа")
        module = parse_bsl_module("// empty", ref)
        assert module.object_ref.name == "Продажа"

    def test_object_ref_none_defaults(self):
        module = parse_bsl_module("// empty")
        assert module.object_ref.type == "CommonModule"
        assert module.object_ref.name == "Unknown"

    def test_module_kind(self):
        module = parse_bsl_module("// empty", module_kind="ObjectModule")
        assert module.module_kind == "ObjectModule"

    def test_line_count(self):
        source = "Строка1\nСтрока2\nСтрока3"
        module = parse_bsl_module(source)
        assert module.line_count == 3


# ─── Методы — извлечение ───────────────────────────────────────────────────


class TestMethodExtraction:
    @pytest.mark.smoke
    def test_single_procedure(self):
        source = 'Процедура МояПроцедура()\n\tСообщить("Hello");\nКонецПроцедуры'
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert len(module.methods) == 1
        assert module.methods[0].name == "МояПроцедура"
        assert module.methods[0].is_procedure is True
        assert module.methods[0].is_export is False

    def test_single_function(self):
        source = "Функция МояФункция()\n\tВозврат 42;\nКонецФункции"
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert len(module.methods) == 1
        assert module.methods[0].name == "МояФункция"
        assert module.methods[0].is_procedure is False

    def test_export_method(self):
        source = "Функция ОткрытаяФункция() Экспорт\n\tВозврат 1;\nКонецФункции"
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert module.methods[0].is_export is True

    def test_non_export_method(self):
        source = "Процедура ВнутренняяПроцедура()\nКонецПроцедуры"
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert module.methods[0].is_export is False

    def test_async_function(self):
        source = "Асинх Функция МояАсинх() Экспорт\n\tВозврат 1;\nКонецФункции"
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert module.methods[0].is_async is True
        assert module.methods[0].is_export is True

    def test_multiple_methods(self, simple_module_bsl: str):
        module = parse_bsl_module(simple_module_bsl, "CommonModule.Тест")
        assert len(module.methods) == 2
        names = [m.name for m in module.methods]
        assert "ТестоваяПроцедура" in names
        assert "ТестоваяФункция" in names

    def test_method_line_numbers(self):
        source = "Строка1\nСтрока2\nПроцедура Тест()\nКонецПроцедуры"
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert module.methods[0].start_line == 3
        assert module.methods[0].end_line >= 3

    def test_method_with_cyrillic_name(self):
        source = "Процедура ОбработкаПроведения(Отказ, ДанныеДляЗаписи)\nКонецПроцедуры"
        module = parse_bsl_module(source, "Document.Продажа", "ObjectModule")
        assert module.methods[0].name == "ОбработкаПроведения"


# ─── Параметры методов ──────────────────────────────────────────────────────


class TestMethodParameters:
    def test_no_parameters(self):
        source = "Процедура БезПараметров()\nКонецПроцедуры"
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert module.methods[0].parameters == []

    def test_simple_parameter(self):
        source = "Процедура СПараметром(Парам1)\nКонецПроцедуры"
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert len(module.methods[0].parameters) == 1
        assert module.methods[0].parameters[0].name == "Парам1"
        assert module.methods[0].parameters[0].by_value is False

    def test_by_value_parameter(self):
        source = "Процедура Знич(Знач Парам1)\nКонецПроцедуры"
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert module.methods[0].parameters[0].by_value is True

    def test_default_value(self):
        source = "Процедура СДефолтом(Парам1 = 0)\nКонецПроцедуры"
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert module.methods[0].parameters[0].has_default is True
        assert module.methods[0].parameters[0].default_value == "0"

    def test_multiple_parameters(self):
        source = 'Процедура Много(Парам1, Знач Парам2, Парам3 = "")\nКонецПроцедуры'
        module = parse_bsl_module(source, "CommonModule.Тест")
        params = module.methods[0].parameters
        assert len(params) == 3
        assert params[0].name == "Парам1"
        assert params[1].by_value is True
        assert params[2].has_default is True

    def test_parameter_with_nested_parens(self):
        """Параметр с значением по умолчанию, содержащим скобки."""
        source = "Процедура Сложный(Парам = Новый Массив(1, 2))\nКонецПроцедуры"
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert len(module.methods[0].parameters) == 1
        assert module.methods[0].parameters[0].has_default is True


# ─── Области ────────────────────────────────────────────────────────────────


class TestRegions:
    @pytest.mark.smoke
    def test_no_regions(self):
        source = "Процедура Тест()\nКонецПроцедуры"
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert module.regions == []

    def test_single_region(self):
        source = "#Область ПрограммныйИнтерфейс\nПроцедура Тест() Экспорт\nКонецПроцедуры\n#КонецОбласти\n"
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert len(module.regions) == 1
        assert module.regions[0].name == "ПрограммныйИнтерфейс"

    def test_multiple_regions(self, with_regions_bsl: str):
        module = parse_bsl_module(with_regions_bsl, "CommonModule.Тест")
        assert len(module.regions) == 4
        names = [r.name for r in module.regions]
        assert "ПрограммныйИнтерфейс" in names
        assert "ОбработчикиСобытийФормы" in names

    def test_nested_regions(self):
        source = (
            "#Область Внешняя\n#Область Внутренняя\nПроцедура Тест()\nКонецПроцедуры\n#КонецОбласти\n#КонецОбласти\n"
        )
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert len(module.regions) == 2
        inner = next(r for r in module.regions if r.name == "Внутренняя")
        assert inner.parent == "Внешняя"

    def test_region_line_numbers(self):
        source = "#Область ПрограммныйИнтерфейс\nПроцедура Тест()\nКонецПроцедуры\n#КонецОбласти\n"
        module = parse_bsl_module(source, "CommonModule.Тест")
        region = module.regions[0]
        assert region.start_line == 1
        # end_line включает строку с #КонецОбласти
        assert region.end_line >= 4


# ─── Методы + регионы ──────────────────────────────────────────────────────


class TestMethodsInRegions:
    def test_method_assigned_to_region(self, with_regions_bsl: str):
        module = parse_bsl_module(with_regions_bsl, "CommonModule.Тест")
        for method in module.methods:
            if method.name == "ОткрытаяФункция":
                assert method.region == "ПрограммныйИнтерфейс"
                break

    def test_method_without_region(self):
        source = "Процедура БезОбласти()\nКонецПроцедуры"
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert module.methods[0].region is None


# ─── parse_bsl_file ────────────────────────────────────────────────────────


class TestParseBslFile:
    @pytest.mark.smoke
    def test_parse_file(self, bsl_samples_dir: Path):
        path = bsl_samples_dir / "simple_module.bsl"
        module = parse_bsl_file(path, "CommonModule.Тест")
        assert isinstance(module, BslModule)
        assert len(module.methods) == 2

    def test_parse_file_nonexistent(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            parse_bsl_file(tmp_path / "nonexistent.bsl")

    def test_parse_with_regions_file(self, bsl_samples_dir: Path):
        path = bsl_samples_dir / "with_regions.bsl"
        module = parse_bsl_file(path, "CommonModule.Тест")
        assert len(module.regions) == 4
        # 5 методов: ОткрытаяФункция, СерверныйВызов, ВнутренняяФункция,
        # ПолучитьДанные, ПриСозданииНаСервере
        assert len(module.methods) == 5

    def test_infer_ref_from_path(self, bsl_samples_dir: Path):
        """Если object_ref не указан — выводится из пути."""
        path = bsl_samples_dir / "simple_module.bsl"
        module = parse_bsl_file(path)
        # Путь не содержит Catalogs/Documents — fallback на CommonModule.Unknown
        assert module.object_ref.type == "CommonModule"

    def test_infer_kind_from_path(self, tmp_path: Path):
        """Вывод module_kind из имени файла."""
        # Создаём структуру Catalogs/Товары/Ext/ObjectModule.bsl
        path = tmp_path / "Catalogs" / "Товары" / "Ext" / "ObjectModule.bsl"
        path.parent.mkdir(parents=True)
        path.write_text("Процедура Тест() КонецПроцедуры", encoding="utf-8")

        module = parse_bsl_file(path)
        assert module.object_ref.type == "Catalog"
        assert module.object_ref.name == "Товары"
        assert module.module_kind == "ObjectModule"


# ─── extract_export_methods ────────────────────────────────────────────────


class TestExtractExportMethods:
    def test_only_export(self):
        source = "Процедура Внутренняя()\nКонецПроцедуры\nФункция Открытая() Экспорт\n\tВозврат 1;\nКонецФункции\n"
        module = parse_bsl_module(source, "CommonModule.Тест")
        exports = extract_export_methods(module)
        assert len(exports) == 1
        assert exports[0].name == "Открытая"

    def test_no_exports(self):
        source = "Процедура Внутренняя()\nКонецПроцедуры\n"
        module = parse_bsl_module(source, "CommonModule.Тест")
        assert extract_export_methods(module) == []


# ─── extract_method_signatures ─────────────────────────────────────────────


class TestExtractMethodSignatures:
    def test_signatures(self):
        source = (
            "Функция Сложить(А, Знач Б = 0) Экспорт\n\tВозврат А + Б;\nКонецФункции\n"
            "Процедура Внутр()\nКонецПроцедуры\n"
        )
        module = parse_bsl_module(source, "CommonModule.Тест")
        sigs = extract_method_signatures(module)
        assert len(sigs) == 1  # только экспортная
        assert sigs[0]["name"] == "Сложить"
        assert sigs[0]["is_procedure"] is False
        assert len(sigs[0]["parameters"]) == 2
        assert sigs[0]["parameters"][0]["name"] == "А"
        assert sigs[0]["parameters"][1]["by_value"] is True
        assert sigs[0]["parameters"][1]["has_default"] is True


# ─── Round-trip ────────────────────────────────────────────────────────────


class TestRoundTrip:
    def test_bsl_module_round_trip(self):
        source = "Процедура Тест() Экспорт\nКонецПроцедуры"
        module = parse_bsl_module(source, "CommonModule.Тест")
        dumped = module.model_dump_json()
        restored = BslModule.model_validate_json(dumped)
        assert restored.object_ref.name == "Тест"
        assert len(restored.methods) == 1
        assert restored.methods[0].name == "Тест"
        assert restored.methods[0].is_export is True

    def test_json_schema_export(self):
        schema = BslModule.model_json_schema()
        assert "properties" in schema
        assert "methods" in schema["properties"]
