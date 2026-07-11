"""Freshness check — сравнение mtime(source) vs mtime(index).

Вынесено из PathManager в отдельный модуль для тестируемости.
PathManager делегирует сюда (см. ADR-0008).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def latest_mtime(paths: Iterable[Path]) -> float | None:
    """Вернуть самый свежий mtime среди файлов.

    Args:
        paths: итератор по путям (файлы и директории).

    Returns:
        mtime (Unix timestamp) самого свежего файла, или None если файлов нет.
    """
    mtimes = [p.stat().st_mtime for p in paths if p.is_file()]
    return max(mtimes) if mtimes else None


def is_fresh(source_dir: Path, index_path: Path) -> bool:
    """Проверить свежесть индекса относительно исходников.

    Индекс свежий, если:
    - index_path существует, И
    - mtime(index) >= latest_mtime(source_dir/*) (включая поддиректории), ИЛИ
    - в source_dir нет файлов (пустой — индекс "свежий" по определению).

    Args:
        source_dir: директория с исходниками (например, data/configs/ut11/4.5.3/).
        index_path: путь к индексу (например, derived/configs/ut11/4.5.3/unified-metadata-index.json).

    Returns:
        True если индекс свежий, False если устарел или отсутствует.
    """
    if not index_path.exists():
        return False
    source_mtime = latest_mtime(source_dir.rglob("*"))
    if source_mtime is None:
        return True  # нет исходников — индекс "свежий" по определению
    return index_path.stat().st_mtime >= source_mtime
