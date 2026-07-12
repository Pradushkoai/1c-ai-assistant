"""parsers.hbk — парсер .hbk файлов синтакс-помощника 1С.

Функции:
    parse_hbk_directory(hbk_dir) → list[PlatformMethod]
    load_methods_to_sqlite(methods, db_path, platform_version) → int
    build_platform_methods_index(hbk_dir, platform_version, db_path) → int

См. ADR-0006 (Data Layer) и ADR-0012 (KB-as-code).
"""

from __future__ import annotations

from .container32 import (
    HbkEntry,
    extract_method_name,
    iter_html_entries,
    parse_availability,
    parse_hbk_file,
    strip_html,
)
from .syntax_helper import (
    build_platform_methods_index,
    load_methods_to_sqlite,
    parse_hbk_directory,
)

__all__ = [
    "parse_hbk_directory",
    "load_methods_to_sqlite",
    "build_platform_methods_index",
    "parse_hbk_file",
    "HbkEntry",
    "iter_html_entries",
    "parse_availability",
    "extract_method_name",
    "strip_html",
]
