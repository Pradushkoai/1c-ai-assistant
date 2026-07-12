"""Dependency graph builder — граф зависимостей между объектами метаданных.

Sprint 4.1 (TD-S4.1-04): последняя задача Этапа 1.

В отличие от call_graph (граф вызовов BSL-методов), этот модуль строит
граф зависимостей МЕТАДАННЫХ: какие объекты ссылаются на какие.

Источники зависимостей:
1. Реквизиты ссылочных типов (CatalogRef.X, DocumentRef.X, EnumRef.X)
2. Табличные части со ссылочными типами
3. Регистраторы регистров (Document.X → Register.Y)
4. Подсистемы (объекты внутри подсистемы)

Planner использует для декомпозиции: понимает какие объекты связаны.

Алгоритм перенесён из старого репо 1c-ai-dev-env (MIT, мой), адаптирован
под наши Pydantic v2 frozen модели (DependencyEdge).

См. ADR-0006, CONCEPTUAL.md §1.2 (Planner → metadata.get_dependency_graph).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from parsers.models import DependencyEdge, ObjectRef

log = logging.getLogger(__name__)

# Regex: ссылочные типы 1С (CatalogRef.Имя, DocumentRef.Имя, ...)
_REF_PATTERN = re.compile(
    r"(CatalogRef|DocumentRef|EnumRef|ChartOfAccountsRef|"
    r"ChartOfCharacteristicTypesRef|ChartOfCalculationTypesRef|"
    r"ExchangePlanRef|BusinessProcessRef|TaskRef)\.(\w+)"
)

# Маппинг: CatalogRef → Catalog, DocumentRef → Document
_REF_TO_TYPE: dict[str, str] = {
    "CatalogRef": "Catalog",
    "DocumentRef": "Document",
    "EnumRef": "Enum",
    "ChartOfAccountsRef": "ChartOfAccounts",
    "ChartOfCharacteristicTypesRef": "ChartOfCharacteristicTypes",
    "ChartOfCalculationTypesRef": "ChartOfCalculationTypes",
    "ExchangePlanRef": "ExchangePlan",
    "BusinessProcessRef": "BusinessProcess",
    "TaskRef": "Task",
}

# Маппинг русских названий ссылочных типов → английские (для ObjectRef)
_RU_REF_TO_TYPE: dict[str, str] = {
    "СправочникСсылка": "Catalog",
    "ДокументСсылка": "Document",
    "ПеречислениеСсылка": "Enum",
    "ПланСчетовСсылка": "ChartOfAccounts",
    "ПланВидовХарактеристикСсылка": "ChartOfCharacteristicTypes",
    "ПланВидовРасчетаСсылка": "ChartOfCalculationTypes",
    "ПланОбменаСсылка": "ExchangePlan",
    "БизнесПроцессСсылка": "BusinessProcess",
    "ЗадачаСсылка": "Task",
}

# Regex: ссылочные типы 1С (CatalogRef.Имя, DocumentRef.Имя, ...)
_REF_PATTERN = re.compile(
    r"(CatalogRef|DocumentRef|EnumRef|ChartOfAccountsRef|"
    r"ChartOfCharacteristicTypesRef|ChartOfCalculationTypesRef|"
    r"ExchangePlanRef|BusinessProcessRef|TaskRef)\.(\w+)"
)

# Regex: русские ссылочные типы (СправочникСсылка.Имя, ДокументСсылка.Имя, ...)
_RU_REF_PATTERN = re.compile(
    r"(СправочникСсылка|ДокументСсылка|ПеречислениеСсылка|"
    r"ПланСчетовСсылка|ПланВидовХарактеристикСсылка|"
    r"ПланВидовРасчетаСсылка|ПланОбменаСсылка|"
    r"БизнесПроцессСсылка|ЗадачаСсылка)\.(\w+)"
)


def build_dependency_graph(
    config_dir: Path,
    config_name: str,
    config_version: str,
) -> dict[str, Any]:
    """Построить граф зависимостей метаданных конфигурации.

    Сканирует XML файлы метаданных, извлекает ссылочные типы реквизитов,
    регистраторов регистров, строит граф зависимостей.

    Args:
        config_dir: директория конфигурации (с Configuration.xml).
        config_name: имя конфигурации.
        config_version: версия.

    Returns:
        Словарь с графом зависимостей:
        {
            "config_name": "...",
            "config_version": "...",
            "edges": [DependencyEdge.model_dump(), ...],
            "stats": {"total_edges": N, "nodes": M},
            "generated_at": "...",
        }
    """
    if not config_dir.exists():
        raise FileNotFoundError(f"Config directory not found: {config_dir}")

    log.info("Building dependency graph for %s/%s", config_name, config_version)

    edges: list[DependencyEdge] = []
    nodes: set[str] = set()

    # Импортируем здесь чтобы не тащить зависимость при --help
    from parsers.xml import iter_metadata_files
    from parsers.xml._xml_utils import find_child, parse_xml

    for metadata_type, object_name, xml_path in iter_metadata_files(config_dir):
        if metadata_type == "Configuration":
            continue

        source_ref_str = f"{metadata_type}.{object_name}"
        nodes.add(source_ref_str)

        try:
            root = parse_xml(xml_path)

            # Находим элемент типа (Catalog, Document, ...)
            obj_elem = find_child(root, metadata_type)
            if obj_elem is None:
                continue

            source_ref = _parse_ref_str(source_ref_str)
            if source_ref is None:
                continue

            # 1. Реквизиты ссылочных типов — используем extract_attributes
            from parsers.xml._xml_utils import extract_attributes
            attributes, tabular_sections = extract_attributes(obj_elem)
            for attr in attributes:
                refs = _extract_refs(attr.type)
                for ref_type, ref_name in refs:
                    target_str = f"{ref_type}.{ref_name}"
                    if target_str != source_ref_str:
                        nodes.add(target_str)
                        detail = f"реквизит {attr.name}"
                        if attr.tabular_section:
                            detail = f"ТЧ {attr.tabular_section}.{attr.name}"
                        edges.append(DependencyEdge(
                            source=source_ref,
                            target=ObjectRef(type=ref_type, name=ref_name),
                            edge_type="uses_attribute",
                            detail=detail,
                        ))

            # 2. Регистраторы регистров
            if metadata_type in ("AccumulationRegister", "InformationRegister",
                                 "AccountingRegister", "CalculationRegister"):
                properties = find_child(obj_elem, "Properties")
                if properties is not None:
                    _scan_recorder(properties, source_ref_str, source_ref, edges, nodes)

        except Exception as exc:
            log.debug("Failed to parse %s: %s", xml_path, exc)

    log.info("Dependency graph: %d edges, %d nodes", len(edges), len(nodes))

    return {
        "config_name": config_name,
        "config_version": config_version,
        "edges": [e.model_dump(mode="json") for e in edges],
        "stats": {
            "total_edges": len(edges),
            "nodes": len(nodes),
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def save_dependency_graph(dep_graph: dict[str, Any], output_path: Path) -> None:
    """Сохранить граф зависимостей в JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dep_graph, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Dependency graph saved to %s (%d KB)", output_path, output_path.stat().st_size // 1024)


def load_dependency_graph(index_path: Path) -> dict[str, Any] | None:
    """Загрузить граф зависимостей из JSON."""
    if not index_path.exists():
        return None
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def _scan_recorder(
    properties: Any,
    source_ref_str: str,
    source_ref: ObjectRef,
    edges: list[DependencyEdge],
    nodes: set[str],
) -> None:
    """Сканировать регистратора регистра."""
    from parsers.xml._xml_utils import find_child as _find_child

    recorder_elem = _find_child(properties, "Recorder")
    if recorder_elem is None:
        return

    # Recorder может быть: Document.Имя или пусто
    recorder_text = ""
    for child in recorder_elem:
        from parsers.xml._xml_utils import _local_name
        tag = _local_name(child)
        if tag == "Document" and child.text:
            recorder_text = f"Document.{child.text}"
            break

    if not recorder_text and recorder_elem.text:
        recorder_text = recorder_elem.text.strip()

    if recorder_text and "." in recorder_text:
        parts = recorder_text.split(".", 1)
        if len(parts) == 2:
            target = ObjectRef(type=parts[0], name=parts[1])
            nodes.add(str(target))
            edges.append(DependencyEdge(
                source=source_ref,
                target=target,
                edge_type="registered_by",
                detail="регистратор",
            ))


def _extract_refs(type_str: str) -> list[tuple[str, str]]:
    """Извлечь ссылочные типы из строки типа.

    Поддерживает 2 формата:
    - Английский: 'CatalogRef.Контрагенты' → [('Catalog', 'Контрагенты')]
    - Русский: 'СправочникСсылка.Контрагенты' → [('Catalog', 'Контрагенты')]
    """
    if not type_str:
        return []

    refs: list[tuple[str, str]] = []

    # Английский формат (cfg:CatalogRef.X или CatalogRef.X)
    for match in _REF_PATTERN.finditer(type_str):
        ref_prefix = match.group(1)
        ref_name = match.group(2)
        ref_type = _REF_TO_TYPE.get(ref_prefix, ref_prefix.replace("Ref", ""))
        refs.append((ref_type, ref_name))

    # Русский формат (СправочникСсылка.X)
    for match in _RU_REF_PATTERN.finditer(type_str):
        ref_prefix = match.group(1)
        ref_name = match.group(2)
        ref_type = _RU_REF_TO_TYPE.get(ref_prefix, ref_prefix)
        refs.append((ref_type, ref_name))

    return refs


def _parse_ref_str(ref_str: str) -> ObjectRef | None:
    """Распарсить строку 'Catalog.Товары' → ObjectRef."""
    if "." not in ref_str:
        return None
    try:
        return ObjectRef.from_string(ref_str)
    except ValueError:
        return None


# Convenience-функции для querying графа

def get_dependencies(
    dep_graph: dict[str, Any],
    object_ref: str,
) -> list[dict[str, Any]]:
    """На что ссылается объект? (исходящие зависимости).

    Args:
        dep_graph: граф из load_dependency_graph.
        object_ref: строка вида 'Catalog.Товары'.

    Returns:
        Список рёбер [{source, target, edge_type, detail}, ...].
    """
    return [
        e for e in dep_graph.get("edges", [])
        if isinstance(e.get("source"), dict)
        and f"{e['source'].get('type')}.{e['source'].get('name')}" == object_ref
    ]


def get_dependents(
    dep_graph: dict[str, Any],
    object_ref: str,
) -> list[dict[str, Any]]:
    """Что зависит от объекта? (входящие зависимости).

    Args:
        dep_graph: граф из load_dependency_graph.
        object_ref: строка вида 'Catalog.Контрагенты'.

    Returns:
        Список рёбер [{source, target, edge_type, detail}, ...].
    """
    return [
        e for e in dep_graph.get("edges", [])
        if isinstance(e.get("target"), dict)
        and f"{e['target'].get('type')}.{e['target'].get('name')}" == object_ref
    ]
