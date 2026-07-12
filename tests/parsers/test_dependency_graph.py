"""Тесты для parsers.xml.dependency_graph.

Sprint 4.1 (TD-S4.1-04): последняя задача Этапа 1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from parsers.xml import (
    build_dependency_graph,
    get_dependencies,
    get_dependents,
    load_dependency_graph,
    save_dependency_graph,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


CATALOG_XML = """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Catalog uuid="test-uuid">
    <Properties>
      <Name>Заказ</Name>
      <Synonym><v8:item><v8:lang>ru</v8:lang><v8:content>Заказ</v8:content></v8:item></Synonym>
    </Properties>
    <ChildObjects>
      <Attribute uuid="a1">
        <Properties>
          <Name>Контрагент</Name>
          <Type>
            <v8:Type>cfg:CatalogRef.Контрагенты</v8:Type>
          </Type>
        </Properties>
      </Attribute>
      <Attribute uuid="a2">
        <Properties>
          <Name>Сумма</Name>
          <Type>
            <v8:Type>xs:decimal</v8:Type>
          </Type>
        </Properties>
      </Attribute>
      <TabularSection uuid="ts1">
        <Properties>
          <Name>Товары</Name>
        </Properties>
        <ChildObjects>
          <Attribute uuid="a3">
            <Properties>
              <Name>Номенклатура</Name>
              <Type>
                <v8:Type>cfg:CatalogRef.Номенклатура</v8:Type>
              </Type>
            </Properties>
          </Attribute>
        </ChildObjects>
      </TabularSection>
    </ChildObjects>
  </Catalog>
</MetaDataObject>
"""

REGISTER_XML = """<?xml version="1.0"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <AccumulationRegister uuid="r1">
    <Properties>
      <Name>Продажи</Name>
      <Synonym><v8:item><v8:lang>ru</v8:lang><v8:content>Продажи</v8:content></v8:item></Synonym>
      <Recorder>
        <Document>Реализация</Document>
      </Recorder>
    </Properties>
  </AccumulationRegister>
</MetaDataObject>
"""


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Создать тестовую конфигурацию с зависимостями."""
    # Catalogs/Заказ.xml — имеет атрибуты CatalogRef.Контрагенты и CatalogRef.Номенклатура
    cat_dir = tmp_path / "Catalogs"
    cat_dir.mkdir()
    (cat_dir / "Заказ.xml").write_text(CATALOG_XML, encoding="utf-8")

    # AccumulationRegisters/Продажи.xml — регистратор Document.Реализация
    reg_dir = tmp_path / "AccumulationRegisters"
    reg_dir.mkdir()
    (reg_dir / "Продажи.xml").write_text(REGISTER_XML, encoding="utf-8")

    # Configuration.xml (обязательно для iter_metadata_files)
    (tmp_path / "Configuration.xml").write_text(
        '<?xml version="1.0"?>\n<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">'
        '<Configuration uuid="x"><Properties><Name>Test</Name><Version>1.0</Version></Properties>'
        '</Configuration></MetaDataObject>',
        encoding="utf-8",
    )

    return tmp_path


# ─── Tests: build_dependency_graph ──────────────────────────────────────────


class TestBuildDependencyGraph:
    def test_returns_dict(self, config_dir: Path):
        result = build_dependency_graph(config_dir, "test", "1.0")
        assert isinstance(result, dict)

    def test_stats(self, config_dir: Path):
        result = build_dependency_graph(config_dir, "test", "1.0")
        assert result["stats"]["total_edges"] >= 2  # Контрагент + Номенклатура
        assert result["stats"]["nodes"] >= 3  # Заказ + Контрагенты + Номенклатура

    def test_config_name(self, config_dir: Path):
        result = build_dependency_graph(config_dir, "test", "1.0")
        assert result["config_name"] == "test"

    def test_generated_at(self, config_dir: Path):
        result = build_dependency_graph(config_dir, "test", "1.0")
        assert "generated_at" in result

    def test_attribute_dependency(self, config_dir: Path):
        """Catalog.Заказ зависит от Catalog.Контрагенты через реквизит."""
        result = build_dependency_graph(config_dir, "test", "1.0")
        found = False
        for e in result["edges"]:
            src = f"{e['source']['type']}.{e['source']['name']}"
            tgt = f"{e['target']['type']}.{e['target']['name']}"
            if src == "Catalog.Заказ" and tgt == "Catalog.Контрагенты":
                assert e["edge_type"] == "uses_attribute"
                assert "Контрагент" in e.get("detail", "")
                found = True
                break
        assert found, "Expected dependency Catalog.Заказ → Catalog.Контрагенты"

    def test_tabular_section_dependency(self, config_dir: Path):
        """ТЧ Товары.Номенклатура — зависимость через табличную часть."""
        result = build_dependency_graph(config_dir, "test", "1.0")
        found = False
        for e in result["edges"]:
            tgt = f"{e['target']['type']}.{e['target']['name']}"
            if tgt == "Catalog.Номенклатура":
                assert "ТЧ" in e.get("detail", "")
                found = True
                break
        assert found, "Expected dependency through tabular section → Catalog.Номенклатура"

    def test_non_ref_attribute_not_included(self, config_dir: Path):
        """Атрибут Сумма (xs:decimal) не создаёт ребро."""
        result = build_dependency_graph(config_dir, "test", "1.0")
        for e in result["edges"]:
            detail = e.get("detail", "")
            assert "Сумма" not in detail, "Non-ref attribute should not create edge"

    def test_empty_dir(self, tmp_path: Path):
        (tmp_path / "Configuration.xml").write_text("<x/>", encoding="utf-8")
        result = build_dependency_graph(tmp_path, "test", "1.0")
        assert result["stats"]["total_edges"] == 0

    def test_nonexistent_dir(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            build_dependency_graph(tmp_path / "nonexistent", "test", "1.0")


# ─── Tests: save/load ───────────────────────────────────────────────────────


class TestSaveLoad:
    def test_save_creates_file(self, config_dir: Path, tmp_path: Path):
        result = build_dependency_graph(config_dir, "test", "1.0")
        out = tmp_path / "dep-graph.json"
        save_dependency_graph(result, out)
        assert out.exists()

    def test_load_returns_dict(self, config_dir: Path, tmp_path: Path):
        result = build_dependency_graph(config_dir, "test", "1.0")
        out = tmp_path / "dep-graph.json"
        save_dependency_graph(result, out)
        loaded = load_dependency_graph(out)
        assert loaded is not None
        assert loaded["config_name"] == "test"

    def test_load_nonexistent(self, tmp_path: Path):
        assert load_dependency_graph(tmp_path / "nonexistent.json") is None


# ─── Tests: get_dependencies / get_dependents ───────────────────────────────


class TestQueryGraph:
    def test_get_dependencies(self, config_dir: Path):
        """На что ссылается Catalog.Заказ?"""
        result = build_dependency_graph(config_dir, "test", "1.0")
        deps = get_dependencies(result, "Catalog.Заказ")
        assert len(deps) >= 2  # Контрагенты + Номенклатура
        targets = [f"{d['target']['type']}.{d['target']['name']}" for d in deps]
        assert "Catalog.Контрагенты" in targets
        assert "Catalog.Номенклатура" in targets

    def test_get_dependents(self, config_dir: Path):
        """Что зависит от Catalog.Контрагенты?"""
        result = build_dependency_graph(config_dir, "test", "1.0")
        dependents = get_dependents(result, "Catalog.Контрагенты")
        assert len(dependents) >= 1
        sources = [f"{d['source']['type']}.{d['source']['name']}" for d in dependents]
        assert "Catalog.Заказ" in sources

    def test_get_dependents_empty(self, config_dir: Path):
        """Ничего не зависит от несуществующего объекта."""
        result = build_dependency_graph(config_dir, "test", "1.0")
        dependents = get_dependents(result, "Catalog.Несуществующий")
        assert dependents == []
