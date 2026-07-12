"""Тесты для parsers.bsl.call_graph — построение графа вызовов.

Sprint 4.1 (TD-S4.1-02).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from parsers.bsl import build_call_graph, load_call_graph, save_call_graph


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Создать тестовую конфигурацию с BSL модулями для call graph."""
    # Модуль 1: имеет export метод, вызывает локальный метод
    mod1_dir = tmp_path / "CommonModules" / "Модуль1" / "Ext"
    mod1_dir.mkdir(parents=True)
    (mod1_dir / "Module.bsl").write_text(
        "Функция ВнешняяФункция() Экспорт\n"
        "\tРезультат = ВнутренняяФункция();\n"
        "\tВозврат Результат;\n"
        "КонецФункции\n"
        "\n"
        "Функция ВнутренняяФункция() Экспорт\n"
        "\tВозврат 42;\n"
        "КонецФункции\n",
        encoding="utf-8",
    )

    # Модуль 2: вызывает метод Модуля1
    mod2_dir = tmp_path / "CommonModules" / "Модуль2" / "Ext"
    mod2_dir.mkdir(parents=True)
    (mod2_dir / "Module.bsl").write_text(
        "Процедура ТестоваяПроцедура() Экспорт\n"
        "\\тРезультат = Модуль1.ВнешняяФункция();\n"
        "КонецПроцедуры\n",
        encoding="utf-8",
    )

    return tmp_path


# ─── Tests: build_call_graph ────────────────────────────────────────────────


class TestBuildCallGraph:
    def test_returns_dict(self, config_dir: Path):
        result = build_call_graph(config_dir, "test", "1.0")
        assert isinstance(result, dict)

    def test_stats(self, config_dir: Path):
        result = build_call_graph(config_dir, "test", "1.0")
        assert result["stats"]["modules"] >= 2
        assert result["stats"]["export_methods"] >= 2
        assert result["stats"]["total_edges"] >= 1

    def test_config_name(self, config_dir: Path):
        result = build_call_graph(config_dir, "test", "1.0")
        assert result["config_name"] == "test"

    def test_generated_at(self, config_dir: Path):
        result = build_call_graph(config_dir, "test", "1.0")
        assert "generated_at" in result

    def test_edges_present(self, config_dir: Path):
        result = build_call_graph(config_dir, "test", "1.0")
        assert len(result["edges"]) > 0

    def test_edge_structure(self, config_dir: Path):
        result = build_call_graph(config_dir, "test", "1.0")
        edge = result["edges"][0]
        assert "source_module" in edge
        assert "source_method" in edge
        assert "target_method" in edge
        assert "line" in edge

    def test_cross_module_call(self, config_dir: Path):
        """Модуль2 вызывает Модуль1.ВнешняяФункция()."""
        result = build_call_graph(config_dir, "test", "1.0")
        cross_edges = [e for e in result["edges"] if e.get("target_module") is not None]
        assert len(cross_edges) >= 1
        # Проверяем что Модуль2 вызывает Модуль1
        found = False
        for e in cross_edges:
            if (e["source_module"]["name"] == "Модуль2" and
                e["target_module"]["name"] == "Модуль1" and
                e["target_method"] == "ВнешняяФункция"):
                found = True
                break
        assert found, "Expected cross-module call Модуль2 → Модуль1.ВнешняяФункция"

    def test_local_call(self, config_dir: Path):
        """Модуль1.ВнешняяФункция вызывает локальный ВнутренняяФункция."""
        result = build_call_graph(config_dir, "test", "1.0")
        local_edges = [e for e in result["edges"] if e.get("target_module") is None]
        assert len(local_edges) >= 1
        found = any(
            e["source_method"] == "ВнешняяФункция" and e["target_method"] == "ВнутренняяФункция"
            for e in local_edges
        )
        assert found, "Expected local call ВнешняяФункция → ВнутренняяФункция"

    def test_empty_dir(self, tmp_path: Path):
        result = build_call_graph(tmp_path, "test", "1.0")
        assert result["stats"]["total_edges"] == 0

    def test_nonexistent_dir(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            build_call_graph(tmp_path / "nonexistent", "test", "1.0")


# ─── Tests: save/load ───────────────────────────────────────────────────────


class TestSaveLoad:
    def test_save_creates_file(self, config_dir: Path, tmp_path: Path):
        result = build_call_graph(config_dir, "test", "1.0")
        out = tmp_path / "call-graph.json"
        save_call_graph(result, out)
        assert out.exists()

    def test_load_returns_dict(self, config_dir: Path, tmp_path: Path):
        result = build_call_graph(config_dir, "test", "1.0")
        out = tmp_path / "call-graph.json"
        save_call_graph(result, out)
        loaded = load_call_graph(out)
        assert loaded is not None
        assert loaded["config_name"] == "test"
        assert loaded["stats"]["total_edges"] == result["stats"]["total_edges"]

    def test_load_nonexistent(self, tmp_path: Path):
        assert load_call_graph(tmp_path / "nonexistent.json") is None
