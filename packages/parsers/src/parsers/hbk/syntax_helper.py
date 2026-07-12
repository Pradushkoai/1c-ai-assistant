"""Парсер .hbk файлов синтакс-помощника 1С.

Использует container32.py для распаковки ZIP и HTML-парсинг для извлечения методов.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from parsers.models import ContextAvailability, PlatformMethod

from .container32 import (
    _AVAILABILITY_RE,
    _AVAILABILITY_TEXT_RE,
    _PAGETITLE_RE,
    extract_method_name,
    iter_html_entries,
    parse_availability,
    parse_hbk_file,
    strip_html,
)

log = logging.getLogger(__name__)

KEY_HBK_FILES = {
    "shcntx_ru.hbk",
    "shlang_ru.hbk",
}

_V8SH_MARKER_RE = re.compile(r"V8SH_chapter|V8SH_pagetitle")


def parse_hbk_directory(hbk_dir: Path) -> list[PlatformMethod]:
    """Распарсить все .hbk файлы в директории."""
    methods: list[PlatformMethod] = []
    seen_names: set[str] = set()

    hbk_files = list(hbk_dir.rglob("*.hbk"))
    if not hbk_files:
        log.warning("No .hbk files found in %s", hbk_dir)
        return methods

    log.info("Parsing %d .hbk files from %s", len(hbk_files), hbk_dir)

    for hbk_file in hbk_files:
        try:
            is_key = hbk_file.name in KEY_HBK_FILES
            file_methods = _parse_single_hbk(hbk_file, full=is_key)
            for method in file_methods:
                key = method.name
                if key not in seen_names:
                    methods.append(method)
                    seen_names.add(key)
        except Exception as exc:
            log.warning("Failed to parse %s: %s", hbk_file, exc)

    log.info("Parsed %d unique platform methods", len(methods))
    return methods


def _parse_single_hbk(hbk_path: Path, full: bool = True) -> list[PlatformMethod]:
    """Распарсить один .hbk файл."""
    entries = parse_hbk_file(hbk_path)
    if not full and len(entries) > 1000:
        entries = entries[:1000]

    html_entries = iter_html_entries(entries)

    methods: list[PlatformMethod] = []
    for name, html_text in html_entries:
        method = _extract_method_from_html(html_text, source_file=name)
        if method is not None:
            methods.append(method)

    return methods


def _extract_method_from_html(
    html_text: str,
    source_file: str = "",
) -> PlatformMethod | None:
    """Извлечь информацию о методе из HTML-страницы."""
    if not _V8SH_MARKER_RE.search(html_text):
        return None

    m = _PAGETITLE_RE.search(html_text)
    title = strip_html(m.group(1)) if m else ""

    if not title:
        return None

    name_ru, name_en, category = extract_method_name(title)
    if not name_ru:
        return None

    avail_text = ""
    m = _AVAILABILITY_RE.search(html_text)
    if not m:
        m = _AVAILABILITY_TEXT_RE.search(html_text)
    if m:
        avail_text = strip_html(m.group(1))
        if "." in avail_text:
            avail_text = avail_text.split(".")[0] + "."

    avail_flags = parse_availability(avail_text)
    availability = ContextAvailability(
        server=avail_flags["server"],
        thin_client=avail_flags["thin_client"],
        web_client=avail_flags["web_client"],
        mobile_client=avail_flags["mobile_client"],
        rich_client=avail_flags["thick_client"],
        external_connection=avail_flags["external_connection"],
        mobile_application=avail_flags["mobile_application"],
        mobile_client_application=avail_flags["mobile_client_application"],
    )

    signature = name_ru
    syntax_match = re.search(
        r'<p[^>]*class="V8SH_chapter">Синтаксис:</p>(.+?)(?:<p[^>]*class="V8SH_chapter">|<HR>|$)',
        html_text,
        re.DOTALL,
    )
    if syntax_match:
        sig_text = strip_html(syntax_match.group(1))[:200]
        if sig_text:
            signature = sig_text

    description = f"Метод платформы 1С: {name_ru}"
    if name_en:
        description += f" (en: {name_en})"
    if category:
        description += f" | Категория: {category}"

    is_procedure = signature.lower().startswith("процедура") or "процедура " in signature.lower()

    return PlatformMethod(
        name=name_ru,
        signature=signature,
        description=description,
        is_procedure=is_procedure,
        availability=availability,
        category=category or "Uncategorized",
    )


def load_methods_to_sqlite(
    methods: list[PlatformMethod],
    db_path: Path,
    platform_version: str,
) -> int:
    """Загрузить методы платформы в SQLite."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS platform_methods (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                signature TEXT,
                description TEXT,
                is_procedure INTEGER DEFAULT 0,
                category TEXT,
                server INTEGER DEFAULT 1,
                thin_client INTEGER DEFAULT 1,
                web_client INTEGER DEFAULT 1,
                mobile_client INTEGER DEFAULT 0,
                external_connection INTEGER DEFAULT 1,
                source_file TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_methods_name
                ON platform_methods(name);

            CREATE TABLE IF NOT EXISTS platform_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )

        conn.execute("DELETE FROM platform_methods")

        for method in methods:
            avail = method.availability
            conn.execute(
                """INSERT INTO platform_methods
                   (name, signature, description, is_procedure, category,
                    server, thin_client, web_client, mobile_client, external_connection)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    method.name,
                    method.signature,
                    method.description,
                    1 if method.is_procedure else 0,
                    method.category,
                    1 if avail.server else 0,
                    1 if avail.thin_client else 0,
                    1 if avail.web_client else 0,
                    1 if avail.mobile_client else 0,
                    1 if avail.external_connection else 0,
                ),
            )

        conn.executemany(
            "INSERT OR REPLACE INTO platform_meta (key, value) VALUES (?, ?)",
            [
                ("platform_version", platform_version),
                ("loaded_at", datetime.now(UTC).isoformat()),
                ("methods_count", str(len(methods))),
                ("methods_loaded", str(len(methods))),
                ("parser_status", "container32_html_parser"),
            ],
        )
        conn.commit()

    log.info("Loaded %d methods to %s", len(methods), db_path)
    return len(methods)


def build_platform_methods_index(
    hbk_dir: Path,
    platform_version: str,
    db_path: Path,
) -> int:
    """Полный цикл: распарсить .hbk → загрузить в SQLite."""
    methods = parse_hbk_directory(hbk_dir)
    return load_methods_to_sqlite(methods, db_path, platform_version)
