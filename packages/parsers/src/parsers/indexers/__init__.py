"""parsers.indexers — построение индексов из данных 1С.

Индексеры читают исходники из data/ (через parsers.xml или parsers.bsl),
обрабатывают и пишут результат в derived/ (JSON, SQLite).

Функции:
    build_metadata_index(config_dir, name, version) → dict
        Сканирует все XML конфигурации, возвращает unified индекс.

    save_metadata_index(index, path) → None
        Сохраняет индекс в JSON.

    load_metadata_index(path) → dict | None
        Загружает ранее сохранённый индекс.

    get_object_from_index(index, object_ref) → dict | None
        Поиск объекта в индексе по ссылке ('Catalog.Товары').

См. ADR-0006 (Data Layer) и ADR-0008 (PathManager).
"""

from __future__ import annotations

from .metadata_indexer import (
    build_metadata_index,
    get_object_from_index,
    load_metadata_index,
    save_metadata_index,
)

__all__ = [
    "build_metadata_index",
    "save_metadata_index",
    "load_metadata_index",
    "get_object_from_index",
]
