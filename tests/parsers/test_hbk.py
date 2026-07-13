"""Тесты для parsers.hbk — парсер .hbk файлов.

Sprint 3.2: полная переработка — .hbk это ZIP-архив с 16-байтным заголовком 1С,
а внутри — HTML-страницы с V8SH-маркерами. Fixtures создают настоящие .hbk файлы.
"""

from __future__ import annotations

import sqlite3
import struct
import zlib
from pathlib import Path

import pytest

from parsers.hbk import (
    build_platform_methods_index,
    load_methods_to_sqlite,
    parse_availability,
    parse_hbk_directory,
    parse_hbk_file,
    strip_html,
)
from parsers.models import PlatformMethod


# ─── Helpers: создание синтетических .hbk файлов ─────────────────────────────


def _make_zip_entry(name: str, content: bytes) -> bytes:
    """Создать одну PK\\x03\\x04 запись (local file header + данные, deflate)."""
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    compressed = compressor.compress(content) + compressor.flush()

    name_bytes = name.encode("utf-8")
    header = struct.pack(
        "<IHHHHHIIIHH",
        0x04034B50,
        20,
        0,
        8,
        0,
        0,
        0,
        len(compressed),
        len(content),
        len(name_bytes),
        0,
    )
    return header + name_bytes + compressed


def _make_hbk_file(entries: list[tuple[str, bytes]]) -> bytes:
    """Создать .hbk файл: 16-байтный заголовок 1С + ZIP-записи."""
    header = b"\x65\xdf\x1c\x00" + b"\x00" * 12
    body = b""
    for name, content in entries:
        body += _make_zip_entry(name, content)
    return header + body


def _make_method_html(
    name_ru: str,
    name_en: str = "",
    category: str = "Глобальный контекст",
    availability: str = "Сервер, толстый клиент, внешнее соединение.",
    syntax: str = "",
) -> str:
    """Создать HTML-страницу метода в формате V8SH."""
    title = f"{category}.{name_ru}"
    if name_en:
        title += f" ({name_en})"

    if not syntax:
        syntax = f"{name_ru}(Параметр1, Параметр2)"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head><body>
<h1 class="V8SH_pagetitle">{title}</h1>
<p class="V8SH_title">{title}</p>
<p class="V8SH_chapter">Синтаксис:</p>
<p>{syntax}</p>
<p class="V8SH_chapter">Описание:</p>
<p>Описание метода {name_ru}</p>
<p class="V8SH_chapter">Доступность:</p>
<p>{availability}</p>
</body></html>"""


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_hbk_dir(tmp_path: Path) -> Path:
    """Создать синтетическую директорию с .hbk файлом (ZIP с HTML внутри)."""
    hbk_dir = tmp_path / "shcntx_ru"
    hbk_dir.mkdir()

    html_files = [
        (
            "objects/methods/ЗаписьЖурналаРегистрации.html",
            _make_method_html(
                "ЗаписьЖурналаРегистрации",
                "WriteLogEvent",
                "Глобальный контекст",
                "Сервер, толстый клиент, внешнее соединение.",
                "ЗаписьЖурналаРегистрации(ИмяСобытия, Уровень, Метаданные, ДанныеСобытия, Комментарий)",
            ),
        ),
        (
            "objects/methods/ПоказатьВопрос.html",
            _make_method_html(
                "ПоказатьВопрос",
                "ShowQuery",
                "Глобальный контекст",
                "Тонкий клиент, веб-клиент, мобильный клиент.",
                "Процедура ПоказатьВопрос(ОписаниеОповещения, ТекстВопроса)",
            ),
        ),
        (
            "objects/methods/ОткрытьФорму.html",
            _make_method_html(
                "ОткрытьФорму",
                "OpenForm",
                "Глобальный контекст",
                "Тонкий клиент, веб-клиент, мобильный клиент.",
                "Функция ОткрытьФорму(ИмяФормы, Параметры)",
            ),
        ),
        (
            "objects/methods/Сообщить.html",
            _make_method_html(
                "Сообщить",
                "Message",
                "Глобальный контекст",
                "Тонкий клиент, веб-клиент, мобильный клиент, сервер, толстый клиент, внешнее соединение.",
                "Процедура Сообщить(Текст)",
            ),
        ),
    ]

    entries = [(name, html.encode("utf-8")) for name, html in html_files]
    hbk_data = _make_hbk_file(entries)

    (hbk_dir / "shcntx_ru.hbk").write_bytes(hbk_data)
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

        html = _make_method_html("Тест", "Test", "Глобальный контекст")
        entries = [("test1.html", html.encode("utf-8"))]
        (hbk_dir / "a.hbk").write_bytes(_make_hbk_file(entries))
        (hbk_dir / "b.hbk").write_bytes(_make_hbk_file(entries))

        methods = parse_hbk_directory(hbk_dir)
        names = [m.name for m in methods]
        assert names.count("Тест") == 1


# ─── Availability ────────────────────────────────────────────────────────────


class TestAvailability:
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

    def test_universal_method(self, synthetic_hbk_dir: Path):
        """Сообщить — доступно везде."""
        methods = parse_hbk_directory(synthetic_hbk_dir)
        for m in methods:
            if m.name == "Сообщить":
                assert m.availability.server is True
                assert m.availability.thin_client is True
                assert m.availability.web_client is True
                break

    def test_parse_availability_helper(self):
        """Прямой тест parse_availability."""
        result = parse_availability("Сервер, толстый клиент, внешнее соединение.")
        assert result["server"] is True
        assert result["thick_client"] is True
        assert result["external_connection"] is True
        assert result["thin_client"] is False
        assert result["web_client"] is False

    def test_parse_availability_empty(self):
        result = parse_availability("")
        assert all(v is False for v in result.values())


# ─── load_methods_to_sqlite ─────────────────────────────────────────────────


class TestLoadToSqlite:
    def test_creates_db(self, tmp_path: Path):
        methods = [
            PlatformMethod(
                name="Тест",
                signature="Тест()",
                description="Test method",
                is_procedure=False,
            )
        ]
        db_path = tmp_path / "platform-methods.db"
        count = load_methods_to_sqlite(methods, db_path, "8.3.25")
        assert count == 1
        assert db_path.exists()

    def test_db_has_method(self, tmp_path: Path):
        methods = [
            PlatformMethod(
                name="Сообщить",
                signature="Процедура Сообщить(Текст)",
                description="Выводит сообщение",
                is_procedure=True,
            )
        ]
        db_path = tmp_path / "platform-methods.db"
        load_methods_to_sqlite(methods, db_path, "8.3.25")

        with sqlite3.connect(db_path) as conn:
            cur = conn.execute("SELECT name, signature, is_procedure FROM platform_methods")
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "Сообщить"
            assert row[1] == "Процедура Сообщить(Текст)"
            assert row[2] == 1

    def test_db_method_availability(self, synthetic_hbk_dir: Path, tmp_path: Path):
        """Метод ЗаписьЖурналаРегистрации — server=True, thin_client=False."""
        methods = parse_hbk_directory(synthetic_hbk_dir)
        db_path = tmp_path / "platform-methods.db"
        load_methods_to_sqlite(methods, db_path, "8.3.25")

        with sqlite3.connect(db_path) as conn:
            cur = conn.execute(
                "SELECT server, thin_client FROM platform_methods WHERE name = ?",
                ("ЗаписьЖурналаРегистрации",),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == 1  # server=True
            assert row[1] == 0  # thin_client=False

    def test_db_has_meta(self, tmp_path: Path):
        methods = [PlatformMethod(name="X", signature="X()", description="x", is_procedure=False)]
        db_path = tmp_path / "platform-methods.db"
        load_methods_to_sqlite(methods, db_path, "8.3.25")

        with sqlite3.connect(db_path) as conn:
            cur = conn.execute("SELECT value FROM platform_meta WHERE key = 'platform_version'")
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "8.3.25"


# ─── build_platform_methods_index ──────────────────────────────────────────


class TestBuildIndex:
    def test_full_cycle(self, synthetic_hbk_dir: Path, tmp_path: Path):
        db_path = tmp_path / "platform-methods.db"
        count = build_platform_methods_index(synthetic_hbk_dir, "8.3.20", db_path)
        assert count > 0
        assert db_path.exists()

    def test_rebuild_replaces_data(self, synthetic_hbk_dir: Path, tmp_path: Path):
        """Перестроение индекса заменяет старые данные."""
        db_path = tmp_path / "platform-methods.db"
        build_platform_methods_index(synthetic_hbk_dir, "8.3.20", db_path)
        first_count = build_platform_methods_index(synthetic_hbk_dir, "8.3.20", db_path)

        with sqlite3.connect(db_path) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM platform_methods")
            actual_count = cur.fetchone()[0]
        assert actual_count == first_count


# ─── container32 helpers ────────────────────────────────────────────────────


class TestContainer32Helpers:
    """Прямые тесты helpers из container32.py."""

    def test_parse_hbk_file_returns_entries(self, synthetic_hbk_dir: Path):
        """parse_hbk_file возвращает list[HbkEntry]."""
        hbk_path = synthetic_hbk_dir / "shcntx_ru.hbk"
        entries = parse_hbk_file(hbk_path)
        assert len(entries) > 0
        names = [e.name for e in entries]
        assert any("ЗаписьЖурналаРегистрации" in n for n in names)

    def test_parse_hbk_file_nonexistent(self, tmp_path: Path):
        """parse_hbk_file на несуществующем файле — пустой список."""
        entries = parse_hbk_file(tmp_path / "nonexistent.hbk")
        assert entries == []

    def test_strip_html(self):
        assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"
        assert strip_html("Plain text") == "Plain text"
        assert strip_html("") == ""

    def test_strip_html_entities(self):
        assert strip_html("&lt;b&gt;bold&lt;/b&gt;") == "bold"
