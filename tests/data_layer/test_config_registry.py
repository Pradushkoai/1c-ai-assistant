"""Тесты для data_layer.config_registry — ConfigRegistry.

См. TESTING_POLICY.md и docs/architecture/03-paths-protocol.md.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from data_layer import ConfigRegistry
from parsers.models import ConfigRegistryEntry


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_entry() -> ConfigRegistryEntry:
    """Типовая запись реестра для тестов."""
    return ConfigRegistryEntry(
        name="ut11",
        version="4.5.3",
        title="Управление торговлей 11",
        added_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
        source_zip="/data/archives/ut11-4.5.3.zip",
        source_path="/data/configs/ut11/4.5.3",
        index_path="/derived/configs/ut11/4.5.3",
        freshness_checked_at=None,
        is_fresh=None,
    )


@pytest.fixture
def empty_registry(tmp_path: Path) -> ConfigRegistry:
    """Пустой ConfigRegistry во временной директории."""
    return ConfigRegistry(tmp_path / "registry.json")


# ─── Smoke тесты ─────────────────────────────────────────────────────────────


class TestConfigRegistryCreation:
    """Создание ConfigRegistry."""

    @pytest.mark.smoke
    def test_create_empty_registry(self, tmp_path: Path):
        registry = ConfigRegistry(tmp_path / "registry.json")
        assert len(registry) == 0

    def test_create_with_nonexistent_path(self, tmp_path: Path):
        """Если файл реестра не существует — реестр пустой, без ошибок."""
        registry = ConfigRegistry(tmp_path / "nonexistent.json")
        assert len(registry) == 0


# ─── add() / get() ──────────────────────────────────────────────────────────


class TestAddGet:
    """add() и get() — основные операции."""

    @pytest.mark.smoke
    def test_add_and_get(self, empty_registry: ConfigRegistry, sample_entry: ConfigRegistryEntry):
        empty_registry.add(sample_entry)
        assert empty_registry.get("ut11", "4.5.3") == sample_entry

    def test_get_nonexistent(self, empty_registry: ConfigRegistry):
        assert empty_registry.get("nonexistent", "1.0") is None

    def test_add_overwrites_existing(self, empty_registry: ConfigRegistry, sample_entry: ConfigRegistryEntry):
        """Повторный add с тем же name:version перезаписывает."""
        empty_registry.add(sample_entry)

        updated_entry = sample_entry.model_copy(update={"title": "Updated title"})
        empty_registry.add(updated_entry)

        result = empty_registry.get("ut11", "4.5.3")
        assert result is not None
        assert result.title == "Updated title"

    def test_add_multiple(self, empty_registry: ConfigRegistry):
        for i in range(5):
            entry = ConfigRegistryEntry(
                name=f"config{i}",
                version=f"1.{i}",
                added_at=datetime.now(UTC),
                source_path=f"/data/config{i}/1.{i}",
                index_path=f"/derived/config{i}/1.{i}",
            )
            empty_registry.add(entry)
        assert len(empty_registry) == 5

    def test_add_with_cyrillic_name(self, empty_registry: ConfigRegistry):
        entry = ConfigRegistryEntry(
            name="УправлениеТорговлей",
            version="4.5.3",
            added_at=datetime.now(UTC),
            source_path="/data/ut/4.5.3",
            index_path="/derived/ut/4.5.3",
        )
        empty_registry.add(entry)
        assert empty_registry.get("УправлениеТорговлей", "4.5.3") is not None


# ─── remove() ───────────────────────────────────────────────────────────────


class TestRemove:
    """remove() — удаление записей."""

    def test_remove_existing(self, empty_registry: ConfigRegistry, sample_entry: ConfigRegistryEntry):
        empty_registry.add(sample_entry)
        assert empty_registry.remove("ut11", "4.5.3") is True
        assert empty_registry.get("ut11", "4.5.3") is None
        assert len(empty_registry) == 0

    def test_remove_nonexistent(self, empty_registry: ConfigRegistry):
        """Удаление несуществующей записи возвращает False."""
        assert empty_registry.remove("nonexistent", "1.0") is False

    def test_remove_does_not_affect_others(self, empty_registry: ConfigRegistry, sample_entry: ConfigRegistryEntry):
        empty_registry.add(sample_entry)
        other = ConfigRegistryEntry(
            name="erp",
            version="2.5",
            added_at=datetime.now(UTC),
            source_path="/data/erp/2.5",
            index_path="/derived/erp/2.5",
        )
        empty_registry.add(other)

        empty_registry.remove("ut11", "4.5.3")
        assert empty_registry.get("erp", "2.5") is not None
        assert len(empty_registry) == 1


# ─── list() ─────────────────────────────────────────────────────────────────


class TestList:
    """iter_entries() и as_list() — итерация по записям."""

    def test_list_empty(self, empty_registry: ConfigRegistry):
        assert list(empty_registry.iter_entries()) == []

    def test_iter_entries_returns_all(self, empty_registry: ConfigRegistry):
        for i in range(3):
            entry = ConfigRegistryEntry(
                name=f"config{i}",
                version="1.0",
                added_at=datetime.now(UTC),
                source_path=f"/data/config{i}/1.0",
                index_path=f"/derived/config{i}/1.0",
            )
            empty_registry.add(entry)

        entries = list(empty_registry.iter_entries())
        assert len(entries) == 3

    def test_as_list(self, empty_registry: ConfigRegistry, sample_entry: ConfigRegistryEntry):
        empty_registry.add(sample_entry)
        entries = empty_registry.as_list()
        assert isinstance(entries, list)
        assert len(entries) == 1
        assert entries[0] == sample_entry

    def test_list_alias_works(self, empty_registry: ConfigRegistry, sample_entry: ConfigRegistryEntry):
        """`list` alias работает для обратной совместимости с контрактом ADR-0008."""
        empty_registry.add(sample_entry)
        entries = list(empty_registry.list())
        assert len(entries) == 1


# ─── Persistence ────────────────────────────────────────────────────────────


class TestPersistence:
    """Сохранение и загрузка реестра из JSON."""

    def test_persistence_round_trip(self, tmp_path: Path, sample_entry: ConfigRegistryEntry):
        """add → reload → get работает."""
        registry_path = tmp_path / "registry.json"

        registry1 = ConfigRegistry(registry_path)
        registry1.add(sample_entry)

        # Новый экземпляр читает тот же файл
        registry2 = ConfigRegistry(registry_path)
        result = registry2.get("ut11", "4.5.3")
        assert result is not None
        assert result.name == "ut11"
        assert result.version == "4.5.3"

    def test_persistence_after_remove(self, tmp_path: Path, sample_entry: ConfigRegistryEntry):
        registry_path = tmp_path / "registry.json"

        registry1 = ConfigRegistry(registry_path)
        registry1.add(sample_entry)
        registry1.remove("ut11", "4.5.3")

        registry2 = ConfigRegistry(registry_path)
        assert registry2.get("ut11", "4.5.3") is None
        assert len(registry2) == 0

    def test_persistence_creates_parent_dir(self, tmp_path: Path, sample_entry: ConfigRegistryEntry):
        """Если родительская директория не существует — она создаётся."""
        registry_path = tmp_path / "nested" / "deep" / "registry.json"
        registry = ConfigRegistry(registry_path)
        registry.add(sample_entry)
        assert registry_path.exists()

    def test_persistence_json_format(self, tmp_path: Path, sample_entry: ConfigRegistryEntry):
        """Файл реестра — валидный JSON с правильной структурой."""
        registry_path = tmp_path / "registry.json"
        registry = ConfigRegistry(registry_path)
        registry.add(sample_entry)

        data = json.loads(registry_path.read_text(encoding="utf-8"))
        assert "entries" in data
        assert len(data["entries"]) == 1
        assert data["entries"][0]["name"] == "ut11"

    def test_persistence_unicode(self, tmp_path: Path):
        """Кириллические имена сохраняются корректно."""
        registry_path = tmp_path / "registry.json"
        entry = ConfigRegistryEntry(
            name="УправлениеТорговлей",
            version="4.5.3",
            added_at=datetime(2026, 7, 11, tzinfo=UTC),
            source_path="/data/ut/4.5.3",
            index_path="/derived/ut/4.5.3",
        )
        registry = ConfigRegistry(registry_path)
        registry.add(entry)

        # Читаем JSON, проверяем что не ASCII-escaped
        raw = registry_path.read_text(encoding="utf-8")
        assert "УправлениеТорговлей" in raw  # ensure_ascii=False

        # Перезагружаем
        registry2 = ConfigRegistry(registry_path)
        assert registry2.get("УправлениеТорговлей", "4.5.3") is not None


# ─── update_freshness() ────────────────────────────────────────────────────


class TestUpdateFreshness:
    """update_freshness() — обновление статуса свежести."""

    def test_update_freshness_true(self, empty_registry: ConfigRegistry, sample_entry: ConfigRegistryEntry):
        empty_registry.add(sample_entry)

        assert empty_registry.update_freshness("ut11", "4.5.3", is_fresh=True) is True

        updated = empty_registry.get("ut11", "4.5.3")
        assert updated is not None
        assert updated.is_fresh is True
        assert updated.freshness_checked_at is not None

    def test_update_freshness_false(self, empty_registry: ConfigRegistry, sample_entry: ConfigRegistryEntry):
        empty_registry.add(sample_entry)
        empty_registry.update_freshness("ut11", "4.5.3", is_fresh=False)

        updated = empty_registry.get("ut11", "4.5.3")
        assert updated is not None
        assert updated.is_fresh is False

    def test_update_freshness_nonexistent(self, empty_registry: ConfigRegistry):
        """update_freshness для несуществующей записи возвращает False."""
        assert empty_registry.update_freshness("nonexistent", "1.0", is_fresh=True) is False

    def test_update_freshness_persists(self, tmp_path: Path, sample_entry: ConfigRegistryEntry):
        """update_freshness сохраняется в JSON."""
        registry_path = tmp_path / "registry.json"
        registry1 = ConfigRegistry(registry_path)
        registry1.add(sample_entry)
        registry1.update_freshness("ut11", "4.5.3", is_fresh=True)

        registry2 = ConfigRegistry(registry_path)
        result = registry2.get("ut11", "4.5.3")
        assert result is not None
        assert result.is_fresh is True

    def test_update_freshness_does_not_mutate_original(
        self, empty_registry: ConfigRegistry, sample_entry: ConfigRegistryEntry
    ):
        """Исходная entry не мутируется (frozen model)."""
        empty_registry.add(sample_entry)
        empty_registry.update_freshness("ut11", "4.5.3", is_fresh=True)

        # Оригинал не изменился
        assert sample_entry.is_fresh is None
        assert sample_entry.freshness_checked_at is None


# ─── __contains__ / __len__ ────────────────────────────────────────────────


class TestDunders:
    """__contains__ и __len__."""

    def test_contains_string_key(self, empty_registry: ConfigRegistry, sample_entry: ConfigRegistryEntry):
        empty_registry.add(sample_entry)
        assert "ut11:4.5.3" in empty_registry
        assert "nonexistent:1.0" not in empty_registry

    def test_contains_tuple_key(self, empty_registry: ConfigRegistry, sample_entry: ConfigRegistryEntry):
        empty_registry.add(sample_entry)
        assert ("ut11", "4.5.3") in empty_registry

    def test_len(self, empty_registry: ConfigRegistry):
        assert len(empty_registry) == 0
        for i in range(3):
            entry = ConfigRegistryEntry(
                name=f"config{i}",
                version="1.0",
                added_at=datetime.now(UTC),
                source_path=f"/data/config{i}/1.0",
                index_path=f"/derived/config{i}/1.0",
            )
            empty_registry.add(entry)
        assert len(empty_registry) == 3


# ─── Corrupted file recovery ────────────────────────────────────────────────


class TestCorruptedFile:
    """Восстановление при повреждённом файле реестра."""

    def test_corrupted_json_does_not_crash(self, tmp_path: Path):
        """Если JSON повреждён — реестр пустой, без исключения."""
        registry_path = tmp_path / "registry.json"
        registry_path.write_text("NOT VALID JSON", encoding="utf-8")

        registry = ConfigRegistry(registry_path)
        assert len(registry) == 0

    def test_corrupted_entry_does_not_crash(self, tmp_path: Path):
        """Если одна запись повреждена — остальные загружаются."""
        registry_path = tmp_path / "registry.json"
        data = {
            "entries": [
                {
                    "name": "valid",
                    "version": "1.0",
                    "added_at": "2026-07-11T12:00:00Z",
                    "source_path": "/data/valid/1.0",
                    "index_path": "/derived/valid/1.0",
                },
                {
                    "name": "invalid",
                    # missing required fields
                },
            ]
        }
        registry_path.write_text(json.dumps(data), encoding="utf-8")

        registry = ConfigRegistry(registry_path)
        # Валидная запись загружена, невалидная пропущена
        assert registry.get("valid", "1.0") is not None
        assert registry.get("invalid", None) is None  # type: ignore[arg-type]
