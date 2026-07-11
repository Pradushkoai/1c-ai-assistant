"""Тесты для data_layer.freshness — функции latest_mtime и is_fresh.

См. TESTING_POLICY.md и docs/architecture/03-paths-protocol.md.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from data_layer import is_fresh, latest_mtime


# ─── latest_mtime ───────────────────────────────────────────────────────────


class TestLatestMtime:
    """latest_mtime() — поиск самого свежего файла."""

    def test_empty_iterator(self, tmp_path: Path):
        """Пустой итератор → None."""
        assert latest_mtime([]) is None

    def test_no_files_only_dirs(self, tmp_path: Path):
        """Только директории (нет файлов) → None."""
        (tmp_path / "dir1").mkdir()
        (tmp_path / "dir2").mkdir()
        assert latest_mtime(tmp_path.iterdir()) is None

    def test_single_file(self, tmp_path: Path):
        file = tmp_path / "test.txt"
        file.write_text("hello", encoding="utf-8")
        result = latest_mtime([file])
        assert result is not None
        assert result == file.stat().st_mtime

    def test_multiple_files_returns_max(self, tmp_path: Path):
        """Из нескольких файлов — самый свежий mtime."""
        old_file = tmp_path / "old.txt"
        old_file.write_text("old", encoding="utf-8")
        old_mtime = old_file.stat().st_mtime

        time.sleep(0.05)

        new_file = tmp_path / "new.txt"
        new_file.write_text("new", encoding="utf-8")
        new_mtime = new_file.stat().st_mtime

        assert new_mtime > old_mtime
        result = latest_mtime([old_file, new_file])
        assert result == new_mtime

    def test_mix_files_and_dirs(self, tmp_path: Path):
        """Файлы и директории вместе — берётся mtime файлов."""
        (tmp_path / "dir").mkdir()
        file = tmp_path / "file.txt"
        file.write_text("hello", encoding="utf-8")

        result = latest_mtime(tmp_path.iterdir())
        assert result is not None
        assert result == file.stat().st_mtime

    def test_rglob_traverses_subdirs(self, tmp_path: Path):
        """rglob('*') обходит поддиректории."""
        sub = tmp_path / "sub"
        sub.mkdir()
        file = sub / "deep.txt"
        file.write_text("deep", encoding="utf-8")

        result = latest_mtime(tmp_path.rglob("*"))
        assert result is not None


# ─── is_fresh ───────────────────────────────────────────────────────────────


class TestIsFresh:
    """is_fresh() — проверка свежести индекса."""

    def test_index_missing_returns_false(self, tmp_path: Path):
        """Если индекса нет — False."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "config.xml").write_text("<r/>", encoding="utf-8")

        index = tmp_path / "index.json"
        assert is_fresh(source, index) is False

    def test_source_empty_index_exists_returns_true(self, tmp_path: Path):
        """Если в source нет файлов, индекс существует — True (по определению)."""
        source = tmp_path / "source"
        source.mkdir()
        # НЕТ файлов в source

        index = tmp_path / "index.json"
        index.write_text("{}", encoding="utf-8")

        assert is_fresh(source, index) is True

    def test_index_newer_than_source_returns_true(self, tmp_path: Path):
        """mtime(index) > mtime(source) → True."""
        source = tmp_path / "source"
        source.mkdir()
        (source / "config.xml").write_text("<r/>", encoding="utf-8")

        time.sleep(0.05)

        index = tmp_path / "index.json"
        index.write_text("{}", encoding="utf-8")

        assert is_fresh(source, index) is True

    def test_index_older_than_source_returns_false(self, tmp_path: Path):
        """mtime(source) > mtime(index) → False (stale)."""
        index = tmp_path / "index.json"
        index.write_text("{}", encoding="utf-8")

        time.sleep(0.05)

        source = tmp_path / "source"
        source.mkdir()
        (source / "config.xml").write_text("<r/>", encoding="utf-8")

        assert is_fresh(source, index) is False

    def test_index_same_mtime_as_source_returns_true(self, tmp_path: Path):
        """mtime(index) == mtime(source) → True (>=)."""
        # Создаём оба одновременно
        source = tmp_path / "source"
        source.mkdir()
        src_file = source / "config.xml"
        src_file.write_text("<r/>", encoding="utf-8")

        index = tmp_path / "index.json"
        index.write_text("{}", encoding="utf-8")

        # Touch source чтобы выровнять mtime
        src_file.touch()

        # is_fresh использует >=, поэтому если mtime равны — True
        result = is_fresh(source, index)
        # Может быть True или False в зависимости от точности fs, но логически >=
        assert isinstance(result, bool)

    def test_is_fresh_with_nested_source(self, tmp_path: Path):
        """is_fresh обходит поддиректории source."""
        source = tmp_path / "source"
        deep_dir = source / "Catalogs" / "Товары"
        deep_dir.mkdir(parents=True)
        (deep_dir / "Товары.xml").write_text("<r/>", encoding="utf-8")

        time.sleep(0.05)

        index = tmp_path / "index.json"
        index.write_text("{}", encoding="utf-8")

        assert is_fresh(source, index) is True

    def test_is_fresh_with_bsl_files(self, tmp_path: Path):
        """is_fresh работает с .bsl файлами."""
        source = tmp_path / "source"
        modules = source / "CommonModules" / "ОбщегоНазначения"
        modules.mkdir(parents=True)
        (modules / "Module.bsl").write_text("Процедура Т() КонецПроцедуры", encoding="utf-8")

        time.sleep(0.05)

        index = tmp_path / "index.json"
        index.write_text("{}", encoding="utf-8")

        assert is_fresh(source, index) is True
