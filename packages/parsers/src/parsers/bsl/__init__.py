"""parsers.bsl — парсеры BSL-модулей 1С.

Функции:
    parse_bsl_module(source, object_ref, module_kind) → BslModule
    parse_bsl_file(file_path, object_ref, module_kind) → BslModule
    extract_export_methods(module) → list[Method]
    extract_method_signatures(module) → list[dict]

См. ADR-0007 (Pydantic v2 models) и docs/architecture/02-pydantic-models.md.
"""

from __future__ import annotations

from .module import (
    extract_export_methods,
    extract_method_signatures,
    parse_bsl_file,
    parse_bsl_module,
)

__all__ = [
    "parse_bsl_module",
    "parse_bsl_file",
    "extract_export_methods",
    "extract_method_signatures",
]
