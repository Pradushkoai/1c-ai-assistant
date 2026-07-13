"""Парсер бинарного формата .hbk файлов 1С (синтакс-помощник).

Формат .hbk — это ZIP-архив с 16-байтным заголовком 1С. Распаковывается
через стандартный zlib. Внутри ZIP — HTML-страницы с V8SH-маркерами.

См. docs/architecture/12-real-data-validation.md, ADR-0006.
"""

from __future__ import annotations

import logging
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class HbkEntry:
    """Один файл внутри .hbk архива."""

    name: str
    data: bytes


def parse_hbk_file(hbk_path: Path) -> list[HbkEntry]:
    """Распаковать .hbk файл — извлечь все встроенные файлы."""
    try:
        data = hbk_path.read_bytes()
    except Exception as exc:
        log.warning("Cannot read %s: %s", hbk_path, exc)
        return []

    if len(data) < 16:
        return []

    entries: list[HbkEntry] = []
    pos = 0
    while pos < len(data):
        pk_pos = data.find(b"PK\x03\x04", pos)
        if pk_pos == -1 or pk_pos + 30 > len(data):
            break

        header_data = data[pk_pos : pk_pos + 30]
        try:
            (_sig, _ver, flags, method, _mtime, _mdate, _crc, comp_size, _uncomp_size, name_len, extra_len) = (
                struct.unpack("<IHHHHHIIIHH", header_data)
            )
        except struct.error:
            pos = pk_pos + 4
            continue

        name_start = pk_pos + 30
        name_end = name_start + name_len
        if name_end > len(data):
            pos = pk_pos + 4
            continue

        try:
            name = data[name_start:name_end].decode("utf-8", errors="replace")
        except Exception:
            pos = pk_pos + 4
            continue

        data_start = name_end + extra_len
        if data_start > len(data):
            pos = pk_pos + 4
            continue

        content = _extract_entry_data(data, data_start, comp_size, method, flags)
        if content is not None:
            entries.append(HbkEntry(name=name, data=content))

        pos = data_start + comp_size if comp_size > 0 and not (flags & 0x08) else pk_pos + 4

    return entries


def _extract_entry_data(
    data: bytes,
    data_start: int,
    comp_size: int,
    method: int,
    flags: int,
) -> bytes | None:
    """Распаковать данные одной ZIP-записи."""
    if comp_size == 0 or (flags & 0x08):
        if method != 8:
            return None
        try:
            decompressor = zlib.decompressobj(-15)
            result = decompressor.decompress(data[data_start:])
            return result
        except zlib.error:
            return None

    raw = data[data_start : data_start + comp_size]
    if method == 0:
        return raw
    if method == 8:
        try:
            return zlib.decompress(raw, -15)
        except zlib.error:
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return None
    return None


def iter_html_entries(entries: list[HbkEntry]) -> list[tuple[str, str]]:
    """Отфильтровать только HTML-записи и вернуть как (name, text)."""
    result: list[tuple[str, str]] = []
    for entry in entries:
        if not entry.name.lower().endswith((".html", ".htm")):
            if not entry.name:
                continue
            try:
                head = entry.data[:200].decode("utf-8", errors="ignore").lower()
                if "<html" not in head and "<!doctype" not in head:
                    continue
            except Exception:
                continue

        try:
            text = entry.data.decode("utf-8", errors="replace")
            result.append((entry.name, text))
        except Exception:
            continue

    return result


_PAGETITLE_RE = re.compile(r'<h1[^>]*class="V8SH_pagetitle"[^>]*>(.+?)</h1>', re.DOTALL)
_AVAILABILITY_RE = re.compile(r'<p[^>]*class="V8SH_chapter">Доступность:\s*</p>\s*<p>([^<]+)</p>', re.DOTALL)
_AVAILABILITY_TEXT_RE = re.compile(r"Доступность:\s*</p>\s*<p>([^<]+)</p>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    """Удалить HTML-теги и декодировать сущности."""
    import html as html_module

    text = html_module.unescape(text)
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


CONTEXT_MAP = {
    "тонкий клиент": "thin_client",
    "веб-клиент": "web_client",
    "веб клиент": "web_client",
    "мобильный клиент": "mobile_client",
    "сервер": "server",
    "толстый клиент": "thick_client",
    "внешнее соединение": "external_connection",
    "мобильное приложение (клиент)": "mobile_application",
    "мобильное приложение (сервер)": "mobile_client_application",
    "мобильный автономный сервер": "mobile_client_application",
}


def parse_availability(raw: str) -> dict[str, bool]:
    """Распарсить строку доступности в булевые флаги."""
    result = {
        "server": False,
        "thin_client": False,
        "web_client": False,
        "mobile_client": False,
        "thick_client": False,
        "external_connection": False,
        "mobile_application": False,
        "mobile_client_application": False,
    }
    if not raw:
        return result
    raw_lower = raw.lower()
    for ru, en in CONTEXT_MAP.items():
        if ru in raw_lower:
            result[en] = True
    return result


def extract_method_name(title: str) -> tuple[str | None, str | None, str | None]:
    """Извлечь (name_ru, name_en, category) из заголовка страницы."""
    if not title:
        return None, None, None

    name_ru: str | None = None
    name_en: str | None = None
    category: str | None = None

    if "(" in title and ")" in title:
        ru_part = title[: title.rfind("(")].strip()
        en_part = title[title.rfind("(") + 1 : title.rfind(")")].strip()
        if "." in ru_part:
            category = ru_part.rsplit(".", 1)[0]
            name_ru = ru_part.rsplit(".", 1)[1]
        else:
            name_ru = ru_part
        name_en = en_part.rsplit(".", 1)[1] if "." in en_part else en_part
    else:
        if "." in title:
            category = title.rsplit(".", 1)[0]
            name_ru = title.rsplit(".", 1)[1]
        else:
            name_ru = title

    return name_ru, name_en, category
