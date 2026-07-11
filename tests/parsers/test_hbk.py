"""Тесты для parsers.hbk — парсер .hbk файлов."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from parsers.hbk import (
    build_platform_methods_index,
    load_methods_to_sqlite,
    parse_hbk_directory,
)
from parsers.models import PlatformMethod


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_hbk_dir(tmp_path: Path) -> Path:
    """Создать синтетическую директорию с .hbk файлами."""
    hbk_dir = tmp_path / "shcntx_ru"
    hbk_dir.mkdir()

    # Создаём минимальный .hbk файл с текстовыми фрагментами
    # (реальные .hbk — бинарные, но содержат UTF-16LE текст)
    content = """
    Функция ЗаписьЖурналаРегистрации(ИмяСобытия, Уровень, Метаданные, ДанныеСобытия, Комментарий)
    Процедура ПоказатьВопрос(ОписаниеОповещения, ТекстВопроса, РежимДиалогаВопрос)
    Функция ОткрытьФорму(ИмяФормы, Параметры)
    Процедура Сообщить(Текст)
    Функция НоваяФункция(Параметр1, Параметр2)
    """
    (hbk_dir / "methods.hbk").write_text(content, encoding="utf-8")
    return hbk_dir


# ─── parse_hbk_directory ───────────────────────────────────────────────────


class TestParseHbkDirectory:
    @pytest.mark.smoke
    def test_returns_list(self, synthetic_hbk_dir: Path):
        methods = parse_hbk_directory(synthetic_hbk_dir)
        assert isinstance(methods, list)

    def test_finds_methods(self, synthetic_hbk_dir: Path):
        methods = parse_hbk_directory(synthetic_hbk_dir)
        names = [m.name for m in methods]
        assert "ЗаписьЖурналаРегистрации" in names
        assert "ПоказатьВопрос" in names
        assert "ОткрытьФорму" in names

    def test_method_has_signature(self, synthetic_hbk_dir: Path):
        methods = parse_hbk_directory(synthetic_hbk_dir)
        for m in methods:
            if m.name == "ЗаписьЖурналаРегистрации":
                assert "ИмяСобытия" in m.signature
                break

    def test_method_is_procedure(self, synthetic_hbk_dir: Path):
        methods = parse_hbk_directory(synthetic_hbk_dir)
        for m in methods:
            if m.name == "ПоказатьВопрос":
                assert m.is_procedure is True
                break
            if m.name == "ЗаписьЖурналаРегистрации":
                assert m.is_procedure is False

    def test_empty_directory(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        methods = parse_hbk_directory(empty_dir)
        assert methods == []

    def test_no_hbk_files(self, tmp_path: Path):
        (tmp_path / "readme.txt").write_text("not a hbk file", encoding="utf-8")
        methods = parse_hbk_directory(tmp_path)
        assert methods == []

    def test_dedup_methods(self, tmp_path: Path):
        """Если метод встречается в нескольких файлах — не дублируется."""
        hbk_dir = tmp_path / "shcntx"
        hbk_dir.mkdir()
        (hbk_dir / "a.hbk").write_text("Функция Тест(А) Возврат А; КонецФункции", encoding="utf-8")
        (hbk_dir / "b.hbk").write_text("Функция Тест(Б) Возврат Б; КонецФункции", encoding="utf-8")
        methods = parse_hbk_directory(hbk_dir)
        names = [m.name for m in methods]
        assert names.count("Тест") == 1


# ─── _guess_availability ────────────────────────────────────────────────────


class TestAvailabilityGuess:
    def test_server_only_method(self, synthetic_hbk_dir: Path):
        methods = parse_hbk_directory(synthetic_hbk_dir)
        for m in methods:
            if m.name == "ЗаписьЖурналаРегистрации":
                assert m.availability.server is True
                assert m.availability.thin_client is False
                break

    def test_client_only_method(self, synthetic_hbk_dir: Path):
        methods = parse_hbk_directory(synthetic_hbk_dir)
        for m in methods:
            if m.name == "ОткрытьФорму":
                assert m.availability.server is False
                assert m.availability.thin_client is True
                break

    def test_generic_method_available_everywhere(self, synthetic_hbk_dir: Path):
        methods = parse_hbk_directory(synthetic_hbk_dir)
        for m in methods:
            if m.name == "НоваяФункция":
                assert m.availability.server is True
                assert m.availability.thin_client is True
                break


# ─── load_methods_to_sqlite ────────────────────────────────────────────────


class TestLoadToSqlite:
    def test_creates_db(self, synthetic_hbk_dir: Path, tmp_path: Path):
        methods = parse_hbk_directory(synthetic_hbk_dir)
        db_path = tmp_path / "platform-methods.db"

        count = load_methods_to_sqlite(methods, db_path, "8.3.20")

        assert db_path.exists()
        assert count == len(methods)

    def test_db_has_methods(self, synthetic_hbk_dir: Path, tmp_path: Path):
        methods = parse_hbk_directory(synthetic_hbk_dir)
        db_path = tmp_path / "platform-methods.db"
        load_methods_to_sqlite(methods, db_path, "8.3.20")

        with sqlite3.connect(db_path) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM platform_methods")
            assert cur.fetchone()[0] == len(methods)

    def test_db_has_meta(self, synthetic_hbk_dir: Path, tmp_path: Path):
        methods = parse_hbk_directory(synthetic_hbk_dir)
        db_path = tmp_path / "platform-methods.db"
        load_methods_to_sqlite(methods, db_path, "8.3.20")

        with sqlite3.connect(db_path) as conn:
            cur = conn.execute("SELECT value FROM platform_meta WHERE key = 'platform_version'")
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "8.3.20"

    def test_db_method_availability(self, synthetic_hbk_dir: Path, tmp_path: Path):
        methods = parse_hbk_directory(synthetic_hbk_dir)
        db_path = tmp_path / "platform-methods.db"
        load_methods_to_sqlite(methods, db_path, "8.3.20")

        with sqlite3.connect(db_path) as conn:
            cur = conn.execute(
                "SELECT server, thin_client FROM platform_methods WHERE name = ?",
                ("ЗаписьЖурналаРегистрации",),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == 1  # server
            assert row[1] == 0  # thin_client


# ─── build_platform_methods_index ──────────────────────────────────────────


class TestBuildIndex:
    def test_full_cycle(self, synthetic_hbk_dir: Path, tmp_path: Path):
        db_path = tmp_path / "platform-methods.db"

        count = build_platform_methods_index(synthetic_hbk_dir, "8.3.20", db_path)

        assert count > 0
        assert db_path.exists()

    def test_rebuild_replaces_data(self, synthetic_hbk_dir: Path, tmp_path: Path):
        db_path = tmp_path / "platform-methods.db"

        build_platform_methods_index(synthetic_hbk_dir, "8.3.20", db_path)
        first_count = build_platform_methods_index(synthetic_hbk_dir, "8.3.20", db_path)

        with sqlite3.connect(db_path) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM platform_methods")
            assert cur.fetchone()[0] == first_count  # не дублировалось
