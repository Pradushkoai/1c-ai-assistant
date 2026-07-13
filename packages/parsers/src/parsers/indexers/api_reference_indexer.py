"""api-reference indexer — извлечение export-методов из BSL модулей.

Sprint 4.1 (TD-S4.1-03): Coder получает список доступных функций конфигурации.

Сканирует все .bsl файлы конфигурации, извлекает export-методы,
сохраняет в api-reference.json. Gatherer передаёт Coder'у список доступных
методов, чтобы не дублировать существующие.

См. ADR-0006 (Data Layer) и CONCEPTUAL.md §1.2 (Gatherer → codebase tools).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from parsers.bsl.module import parse_bsl_module

log = logging.getLogger(__name__)


def build_api_reference(
    config_dir: Path,
    config_name: str,
    config_version: str,
) -> dict[str, Any]:
    """Построить api-reference.json из BSL модулей конфигурации.

    Сканирует все .bsl файлы в config_dir, извлекает export-методы,
    группирует по модулям.

    Args:
        config_dir: директория конфигурации (с Configuration.xml).
        config_name: имя конфигурации.
        config_version: версия.

    Returns:
        Словарь с api-reference:
        {
            "config_name": "...",
            "config_version": "...",
            "modules": [
                {
                    "module_kind": "CommonModule" | "ObjectModule" | ...,
                    "object_ref": "CommonModule.ИмяМодуля" | "Catalog.Товары.ObjectModule" | ...,
                    "file_path": "CommonModules/.../Ext/Module.bsl",
                    "export_methods": [
                        {"name": "ИмяМетода", "parameters": ["Параметр1", "Параметр2"], "is_function": true},
                        ...
                    ]
                },
                ...
            ],
            "stats": {
                "total_modules": N,
                "total_export_methods": M,
            },
            "generated_at": "2026-...",
        }
    """
    if not config_dir.exists():
        raise FileNotFoundError(f"Config directory not found: {config_dir}")

    log.info("Building api-reference for %s/%s from %s", config_name, config_version, config_dir)

    bsl_files = list(config_dir.rglob("*.bsl"))
    log.info("Found %d .bsl files", len(bsl_files))

    modules: list[dict[str, Any]] = []
    total_export_methods = 0

    for bsl_path in bsl_files:
        try:
            code = bsl_path.read_text(encoding="utf-8", errors="replace")
            if not code.strip():
                continue

            module = parse_bsl_module(code)

            export_methods = [
                {
                    "name": m.name,
                    "parameters": [p.name for p in m.parameters],
                    "is_function": not m.is_procedure,
                }
                for m in module.methods
                if m.is_export
            ]

            if not export_methods:
                continue

            # Определяем тип модуля и object_ref из пути
            module_kind, object_ref = _guess_module_info(bsl_path, config_dir)

            modules.append(
                {
                    "module_kind": module_kind,
                    "object_ref": object_ref,
                    "file_path": str(bsl_path.relative_to(config_dir)),
                    "export_methods": export_methods,
                }
            )
            total_export_methods += len(export_methods)

        except Exception as exc:
            log.warning("Failed to parse %s: %s", bsl_path, exc)

    result = {
        "config_name": config_name,
        "config_version": config_version,
        "modules": modules,
        "stats": {
            "total_modules": len(modules),
            "total_export_methods": total_export_methods,
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }

    log.info(
        "Api-reference built: %d modules, %d export methods",
        len(modules),
        total_export_methods,
    )

    return result


def save_api_reference(
    api_ref: dict[str, Any],
    output_path: Path,
) -> None:
    """Сохранить api-reference в JSON файл.

    Args:
        api_ref: словарь из build_api_reference.
        output_path: путь для сохранения.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(api_ref, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Api-reference saved to %s (%d KB)", output_path, output_path.stat().st_size // 1024)


def load_api_reference(index_path: Path) -> dict[str, Any] | None:
    """Загрузить ранее сохранённый api-reference.

    Args:
        index_path: путь к api-reference.json.

    Returns:
        Словарь или None если файл не существует.
    """
    if not index_path.exists():
        return None
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def get_methods_for_object(
    api_ref: dict[str, Any],
    object_ref: str,
) -> list[dict[str, Any]]:
    """Найти все export-методы для объекта.

    Args:
        api_ref: словарь из load_api_reference.
        object_ref: строка вида 'CommonModule.ИмяМодуля' или 'Catalog.Товары'.

    Returns:
        Список методов [{name, parameters, is_function}, ...].
    """
    results: list[dict[str, Any]] = []
    for module in api_ref.get("modules", []):
        if module.get("object_ref", "").startswith(object_ref):
            results.extend(module.get("export_methods", []))
    return results


def _guess_module_info(
    bsl_path: Path,
    config_dir: Path,
) -> tuple[str, str]:
    """Определить тип модуля и object_ref из пути файла.

    Примеры:
        CommonModules/Имя/Ext/Module.bsl → ("CommonModule", "CommonModule.Имя")
        Catalogs/Товары/Ext/ObjectModule.bsl → ("ObjectModule", "Catalog.Товары")
        Documents/Продажа/Forms/ФормаДокумента/Ext/Form/Module.bsl
          → ("FormModule", "Document.Продажа.ФормаДокумента")

    Returns:
        Кортеж (module_kind, object_ref).
    """
    try:
        rel = bsl_path.relative_to(config_dir)
    except ValueError:
        return ("Unknown", bsl_path.stem)

    parts = rel.parts

    # CommonModules/Имя/Ext/Module.bsl
    if len(parts) >= 3 and parts[0] == "CommonModules":
        module_name = parts[1]
        return ("CommonModule", f"CommonModule.{module_name}")

    # Catalogs/Товары/Ext/ObjectModule.bsl
    if len(parts) >= 4 and parts[2] == "Ext":
        type_dir = parts[0]  # Catalogs, Documents, etc.
        object_name = parts[1]
        file_name = parts[-1]  # ObjectModule.bsl, ManagerModule.bsl, etc.

        type_map = {
            "Catalogs": "Catalog",
            "Documents": "Document",
            "DataProcessors": "DataProcessor",
            "Reports": "Report",
            "InformationRegisters": "InformationRegister",
            "AccumulationRegisters": "AccumulationRegister",
            "ChartsOfCharacteristicTypes": "ChartOfCharacteristicTypes",
            "BusinessProcesses": "BusinessProcess",
            "Tasks": "Task",
            "ExchangePlans": "ExchangePlan",
        }

        obj_type = type_map.get(type_dir, type_dir[:-1] if type_dir.endswith("s") else type_dir)
        module_kind = file_name.replace(".bsl", "")

        return (module_kind, f"{obj_type}.{object_name}")

    # Forms: Catalogs/Товары/Forms/ФормаДокумента/Ext/Form/Module.bsl
    if "Forms" in parts:
        forms_idx = parts.index("Forms")
        if forms_idx >= 2:
            type_dir = parts[0]
            object_name = parts[1]
            form_name = parts[forms_idx + 1] if forms_idx + 1 < len(parts) else "Unknown"

            type_map = {
                "Catalogs": "Catalog",
                "Documents": "Document",
                "DataProcessors": "DataProcessor",
                "Reports": "Report",
            }
            obj_type = type_map.get(type_dir, "Unknown")
            return ("FormModule", f"{obj_type}.{object_name}.{form_name}")

    # CommonForms/Имя/Ext/Form/Module.bsl
    if len(parts) >= 2 and parts[0] == "CommonForms":
        return ("FormModule", f"CommonForm.{parts[1]}")

    return ("Unknown", str(rel))
