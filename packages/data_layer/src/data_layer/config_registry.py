"""ConfigRegistry — реестр загруженных конфигураций 1С.

Хранится в runtime/config-registry.json.
Каждая запись: ConfigRegistryEntry (из parsers.models).

См. ADR-0008 (PathManager) и ADR-0006 (Data Layer).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from parsers.models import ConfigRegistryEntry

log = logging.getLogger(__name__)


class ConfigRegistry:
    """Реестр конфигураций: add/list/get/remove/update_freshness.

    Args:
        registry_path: путь к JSON-файлу реестра
            (обычно runtime/config-registry.json).

    Examples:
        >>> from data_layer import ConfigRegistry
        >>> registry = ConfigRegistry(Path("runtime/config-registry.json"))
        >>> registry.add(ConfigRegistryEntry(
        ...     name="ut11",
        ...     version="4.5.3",
        ...     added_at=datetime.now(UTC),
        ...     source_path="/data/configs/ut11/4.5.3",
        ...     index_path="/derived/configs/ut11/4.5.3",
        ... ))
        >>> entry = registry.get("ut11", "4.5.3")
        >>> entry.name
        'ut11'
    """

    def __init__(self, registry_path: Path) -> None:
        self._path = registry_path
        self._entries: dict[str, ConfigRegistryEntry] = {}
        self._load()

    def _load(self) -> None:
        """Загрузить реестр из JSON файла (если существует)."""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load config registry %s: %s", self._path, exc)
            return
        for entry_data in data.get("entries", []):
            try:
                # model_validate_json применяет JSON-семантику (datetime из строки OK),
                # что работает с strict=True моделями. model_validate(dict) в strict
                # mode отказывается конвертировать строку в datetime.
                entry = ConfigRegistryEntry.model_validate_json(json.dumps(entry_data, ensure_ascii=False))
                key = f"{entry.name}:{entry.version}"
                self._entries[key] = entry
            except Exception as exc:
                log.warning("Failed to load registry entry %s: %s", entry_data, exc)

    def _save(self) -> None:
        """Сохранить реестр в JSON файл."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "entries": [e.model_dump(mode="json") for e in self._entries.values()],
            "version": "1.0",
        }
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add(self, entry: ConfigRegistryEntry) -> None:
        """Добавить или обновить запись о конфигурации.

        Если запись с таким name:version уже существует — она заменяется.
        """
        key = f"{entry.name}:{entry.version}"
        self._entries[key] = entry
        self._save()

    def remove(self, name: str, version: str) -> bool:
        """Удалить запись о конфигурации.

        Returns:
            True если запись существовала и удалена, False если не существовала.
        """
        key = f"{name}:{version}"
        if key in self._entries:
            del self._entries[key]
            self._save()
            return True
        return False

    def get(self, name: str, version: str) -> ConfigRegistryEntry | None:
        """Получить запись о конфигурации по name:version.

        Returns:
            ConfigRegistryEntry или None если не найдена.
        """
        return self._entries.get(f"{name}:{version}")

    def iter_entries(self) -> Iterator[ConfigRegistryEntry]:
        """Итератор по всем записям реестра."""
        return iter(self._entries.values())

    def as_list(self) -> list[ConfigRegistryEntry]:
        """Список всех записей реестра (для удобства сериализации)."""
        return list(self._entries.values())

    # Alias для обратной совместимости с контрактом ADR-0008
    # (в архитектуре метод назывался list, но это конфликтует с mypy)
    list = iter_entries

    def update_freshness(self, name: str, version: str, is_fresh: bool) -> bool:
        """Обновить статус свежести индексов конфигурации.

        Args:
            name: имя конфигурации.
            version: версия конфигурации.
            is_fresh: True если индексы свежие.

        Returns:
            True если запись найдена и обновлена, False если не найдена.
        """
        entry = self.get(name, version)
        if entry is None:
            return False
        # frozen model → создаём новую с обновлённым полем
        updated = entry.model_copy(
            update={
                "is_fresh": is_fresh,
                "freshness_checked_at": datetime.now(UTC),
            }
        )
        self._entries[f"{name}:{version}"] = updated
        self._save()
        return True

    def __len__(self) -> int:
        """Количество записей в реестре."""
        return len(self._entries)

    def __contains__(self, key: str | tuple[str, str]) -> bool:
        """Проверка наличия записи.

        Args:
            key: либо строка "name:version", либо кортеж (name, version).
        """
        if isinstance(key, tuple):
            key = f"{key[0]}:{key[1]}"
        return key in self._entries
