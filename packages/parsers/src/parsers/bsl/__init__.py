"""parsers.bsl — парсеры BSL-модулей 1С.

Функции:
    parse_bsl_module(source, object_ref, module_kind) → BslModule
    parse_bsl_file(file_path, object_ref, module_kind) → BslModule
    extract_export_methods(module) → list[Method]
    extract_method_signatures(module) → list[dict]
    build_call_graph(config_dir, name, version) → dict
    save_call_graph / load_call_graph — persistence

См. ADR-0007 (Pydantic v2 models) и docs/architecture/02-pydantic-models.md.
"""

from __future__ import annotations

from .call_graph import (
    build_call_graph,
    load_call_graph,
    save_call_graph,
)
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
    "build_call_graph",
    "save_call_graph",
    "load_call_graph",
]
