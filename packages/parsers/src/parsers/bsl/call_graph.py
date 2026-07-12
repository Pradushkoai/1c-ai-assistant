"""Call graph builder — построение графа вызовов BSL-методов.

Sprint 4.1 (TD-S4.1-02): Coder видит существующие вызовы, не дублирует.

Алгоритм (перенесён из старого репо 1c-ai-dev-env, MIT):
1. Первый проход: собираем имена всех модулей и export-методов
2. Второй проход: для каждого .bsl файла ищем вызовы:
   - Кросс-модульные: Модуль.Метод( — где Модуль в списке известных
   - Локальные: Метод( — если метод в export_methods этого модуля

Использует regex (tree-sitter-bsl опционален, не обязателен для MVP).

См. ADR-0006, CONCEPTUAL.md §1.2 (Gatherer → codebase tools).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from parsers.models import CallEdge, ObjectRef

log = logging.getLogger(__name__)

# Regex: кросс-модульный вызов Модуль.Метод(
_CROSS_MODULE_CALL_RE = re.compile(
    r"\b([А-Яа-яЁё][А-Яа-яЁё\w]*)\s*\.\s*([А-Яа-яЁё][А-Яа-яЁё\w]*)\s*\(",
)

# Regex: определение процедуры/функции
_PROC_DEF_RE = re.compile(r"(Процедура|Функция)\s+([А-Яа-яЁё\w]+)")

# Ключевые слова BSL — не методы
_BSL_KEYWORDS = {
    "Если", "Иначе", "ИначеЕсли", "КонецЕсли",
    "Для", "Пока", "Цикл", "КонецЦикла",
    "Процедура", "КонецПроцедуры",
    "Функция", "КонецФункции",
    "Возврат", "Прервать", "Продолжить",
    "Попытка", "Исключение", "КонецПопытки",
    "Перем", "Новый",
    "И", "ИЛИ", "НЕ", "Тогда",
    "Экспорт", "Знач",
    "Неопределено", "Истина", "Ложь",
}

# Стандартные объекты 1С — не модули конфигурации
_STANDARD_OBJECTS = {
    "ЭтотОбъект", "Объект", "Форма", "Элементы", "ЭтаФорма",
    "Справочники", "Документы", "Регистры", "Константы", "Метаданные",
    "Параметры", "ПараметрыСеанса", "Запрос", "Результат", "РезультатЗапроса",
    "Выборка", "СтрокаТаблицы", "Элемент", "Колонка",
    "Структура", "Массив", "ТаблицаЗначений", "ДеревоЗначений",
    "Справочник", "Документ", "РегистрСведений", "РегистрНакопления",
    "РегистрБухгалтерии", "РегистрРасчета", "ПланСчетов", "ПланВидовХарактеристик",
    "ПланВидовРасчета", "ПланОбмена", "Перечисление", "БизнесПроцесс", "Задача",
    "ДоставляемыеУведомления", "СредстваМультимедиа", "ФоновыеЗадания",
    "ИнформацияОбИнтернетСоединении", "ЖурналРегистрации", "Пользователи",
    "ПользователиИнформационнойБазы", "ДвоичныеДанные", "ХранилищеЗначения",
    "ЧтениеJSON", "ЗаписьJSON", "ЧтениеXML", "ЗаписьXML",
    "HTTPСоединение", "HTTPЗапрос", "HTTPОтвет",
    "КомпоновщикНастроек", "ПроцессорВывода", "ТабличныйДокумент",
    "ТекстовыйДокумент", "ОписаниеОповещения", "ДиалогВыбораФайла",
    "ЗащищенноеСоединениеOpenSSL",
}


def build_call_graph(
    config_dir: Path,
    config_name: str,
    config_version: str,
) -> dict[str, Any]:
    """Построить граф вызовов BSL-методов конфигурации.

    Двухпроходный алгоритм:
    1. Собираем имена модулей и export-методов
    2. Парсим каждый .bsl файл на вызовы

    Args:
        config_dir: директория конфигурации.
        config_name: имя конфигурации.
        config_version: версия.

    Returns:
        Словарь с графом вызовов:
        {
            "config_name": "...",
            "config_version": "...",
            "edges": [CallEdge.model_dump(), ...],
            "stats": {"total_edges": N, "modules": M, "cross_module_calls": K},
            "generated_at": "...",
        }
    """
    if not config_dir.exists():
        raise FileNotFoundError(f"Config directory not found: {config_dir}")

    log.info("Building call graph for %s/%s", config_name, config_version)

    bsl_files = list(config_dir.rglob("*.bsl"))
    log.info("Found %d .bsl files", len(bsl_files))

    # ─── Проход 1: собираем имена модулей и export-методы ────────────────────
    module_names: set[str] = set()
    export_methods: set[str] = set()  # "ИмяМодуля.ИмяМетода"

    for bsl_path in bsl_files:
        mod_name = _get_module_name_from_path(bsl_path, config_dir)
        module_names.add(mod_name)

        try:
            code = bsl_path.read_text(encoding="utf-8-sig", errors="replace")
            from parsers.bsl.module import parse_bsl_module
            module = parse_bsl_module(code)
            for method in module.methods:
                if method.is_export:
                    export_methods.add(f"{mod_name}.{method.name}")
        except Exception as exc:
            log.debug("Failed to parse %s for export methods: %s", bsl_path, exc)

    log.info("Pass 1: %d modules, %d export methods", len(module_names), len(export_methods))

    # ─── Проход 2: извлекаем рёбра вызовов ───────────────────────────────────
    edges: list[CallEdge] = []
    cross_module_count = 0

    for bsl_path in bsl_files:
        mod_name = _get_module_name_from_path(bsl_path, config_dir)
        mod_ref = _guess_module_ref(bsl_path, config_dir)

        try:
            code = bsl_path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            continue

        file_edges = _parse_bsl_file(
            code=code,
            mod_name=mod_name,
            mod_ref=mod_ref,
            config_dir=config_dir,
            bsl_path=bsl_path,
            module_names=module_names,
            export_methods=export_methods,
        )
        edges.extend(file_edges)
        cross_module_count += sum(1 for e in file_edges if e.target_module is not None)

    log.info("Pass 2: %d edges (%d cross-module)", len(edges), cross_module_count)

    return {
        "config_name": config_name,
        "config_version": config_version,
        "edges": [e.model_dump(mode="json") for e in edges],
        "stats": {
            "total_edges": len(edges),
            "modules": len(module_names),
            "export_methods": len(export_methods),
            "cross_module_calls": cross_module_count,
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def save_call_graph(call_graph: dict[str, Any], output_path: Path) -> None:
    """Сохранить граф вызовов в JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(call_graph, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Call graph saved to %s (%d KB)", output_path, output_path.stat().st_size // 1024)


def load_call_graph(index_path: Path) -> dict[str, Any] | None:
    """Загрузить граф вызовов из JSON."""
    if not index_path.exists():
        return None
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


# ─── Внутренние функции ─────────────────────────────────────────────────────


def _get_module_name_from_path(bsl_path: Path, config_dir: Path) -> str:
    """Извлечь имя модуля из пути файла."""
    try:
        rel = bsl_path.relative_to(config_dir)
    except ValueError:
        return bsl_path.stem

    parts = rel.parts

    if len(parts) >= 2:
        if parts[0] == "CommonModules":
            return parts[1]
        if parts[0] == "Ext":
            return bsl_path.stem
        if parts[0] == "CommonForms" and len(parts) >= 3:
            return parts[1]
        if "Ext" in parts:
            ext_idx = parts.index("Ext")
            if ext_idx > 0:
                return parts[ext_idx - 1]

    return bsl_path.stem


def _guess_module_ref(bsl_path: Path, config_dir: Path) -> ObjectRef:
    """Определить ObjectRef модуля из пути."""
    try:
        rel = bsl_path.relative_to(config_dir)
    except ValueError:
        return ObjectRef(type="CommonModule", name=bsl_path.stem)

    parts = rel.parts

    if len(parts) >= 3 and parts[0] == "CommonModules":
        return ObjectRef(type="CommonModule", name=parts[1])

    if len(parts) >= 4 and parts[2] == "Ext":
        type_map = {
            "Catalogs": "Catalog",
            "Documents": "Document",
            "DataProcessors": "DataProcessor",
            "Reports": "Report",
        }
        obj_type = type_map.get(parts[0], "Unknown")
        return ObjectRef(type=obj_type, name=parts[1])

    return ObjectRef(type="CommonModule", name=_get_module_name_from_path(bsl_path, config_dir))


def _parse_bsl_file(
    code: str,
    mod_name: str,
    mod_ref: ObjectRef,
    config_dir: Path,
    bsl_path: Path,
    module_names: set[str],
    export_methods: set[str],
) -> list[CallEdge]:
    """Распарсить один BSL файл на вызовы методов."""
    lines = code.split("\n")
    edges: list[CallEdge] = []

    import contextlib
    with contextlib.suppress(ValueError):
        str(bsl_path.relative_to(config_dir))

    for i, raw_line in enumerate(lines):
        line = _strip_comments(raw_line)
        stripped = line.strip()
        if not stripped:
            continue

        current_proc = _find_current_procedure(lines, i)

        # 1. Кросс-модульные вызовы: Модуль.Метод(
        for m in _CROSS_MODULE_CALL_RE.finditer(line):
            obj_name = m.group(1)
            method_name = m.group(2)

            if obj_name in _STANDARD_OBJECTS or obj_name in _BSL_KEYWORDS:
                continue

            if obj_name in module_names:
                edges.append(CallEdge(
                    source_module=mod_ref,
                    source_method=current_proc,
                    target_module=ObjectRef(type="CommonModule", name=obj_name),
                    target_method=method_name,
                    line=i + 1,
                    is_platform=False,
                ))

        # 2. Локальные вызовы: Метод( — если метод export в этом модуле
        for local_m in re.finditer(r"\b([А-Яа-яЁё][А-Яа-яЁё\w]*)\s*\(", stripped):
            method_name = local_m.group(1)
            if method_name not in _BSL_KEYWORDS and method_name != current_proc and f"{mod_name}.{method_name}" in export_methods:
                    edges.append(CallEdge(
                        source_module=mod_ref,
                        source_method=current_proc,
                        target_module=None,
                        target_method=method_name,
                        line=i + 1,
                        is_platform=False,
                    ))

    return edges


def _find_current_procedure(lines: list[str], line_idx: int) -> str:
    """Найти имя процедуры/функции, в которой находится строка."""
    for i in range(line_idx, -1, -1):
        line = lines[i].strip()
        m = _PROC_DEF_RE.match(line)
        if m:
            return m.group(2)
    return "<модуль>"


def _strip_comments(line: str) -> str:
    """Удалить комментарий // из строки (не внутри строк)."""
    in_string = False
    i = 0
    while i < len(line) - 1:
        if line[i] == '"':
            in_string = not in_string
        elif not in_string and line[i] == "/" and line[i + 1] == "/":
            return line[:i]
        i += 1
    return line
