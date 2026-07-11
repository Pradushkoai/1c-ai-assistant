"""Конфигурация 1С как целое.

ConfigMeta — корневые метаданные конфигурации (Configuration.xml).
ConfigRegistryEntry — запись в реестре загруженных конфигов.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .common import ModelConfig, Version
from .metadata import MetadataType


class VersionInfo(ModelConfig):
    """Версия конфигурации.

    Attributes:
        version: версия, например '11.4.5.3'.
        edition: редакция, например 'Управление торговлей'.
        vendor: разработчик, например '1С-Солид'.
        description: описание версии.
    """

    version: str = Field(description="Версия: '11.4.5.3'")
    edition: str | None = Field(default=None, description="Редакция: 'Управление торговлей'")
    vendor: str | None = Field(default=None, description="Разработчик")
    description: str | None = Field(default=None, description="Описание версии")


class ConfigMeta(ModelConfig):
    """Метаданные конфигурации целиком (Configuration.xml).

    Корневой объект метаданных 1С. Содержит:
    - имя, синоним, версию
    - версию платформы, для которой собрана
    - количество объектов каждого типа

    Attributes:
        name: имя конфигурации ('УправлениеТорговлей').
        synonym: синоним ('Управление торговлей').
        version_info: информация о версии.
        platform_version: версия платформы, для которой собрана.
        default_data_lock_mode: режим блокировки данных (Managed | Auto).
        default_language: язык по умолчанию ('ru').
        data_separators: разделители данных.
        object_counts: количество объектов каждого типа.
    """

    name: str = Field(description="Имя конфигурации: 'УправлениеТорговлей'")
    synonym: str | None = Field(default=None, description="Синоним")
    version_info: VersionInfo
    platform_version: Version = Field(
        description="Версия платформы, для которой собрана конфигурация",
    )
    default_data_lock_mode: str = Field(
        default="Managed",
        description="Режим блокировки данных: Managed | Auto",
    )
    default_language: str = Field(default="ru", description="Язык по умолчанию")
    data_separators: list[str] = Field(
        default_factory=list,
        description="Разделители данных",
    )
    object_counts: dict[MetadataType, int] = Field(
        default_factory=dict,
        description="Количество объектов каждого типа в конфигурации",
    )


class ConfigRegistryEntry(ModelConfig):
    """Запись в runtime/config-registry.json — реестр загруженных конфигов.

    ConfigRegistry (data_layer) управляет этим списком.

    Attributes:
        name: имя конфигурации (пользовательское).
        version: версия (пользовательская).
        title: отображаемое имя.
        added_at: когда добавлена в реестр.
        source_zip: путь к исходному ZIP (если был).
        source_path: путь к распакованной конфигурации.
        index_path: путь к сгенерированным индексам.
        freshness_checked_at: когда последний раз проверялась свежесть.
        is_fresh: True если индексы свежие (mtime source <= mtime index).
    """

    name: str
    version: str
    title: str | None = None
    added_at: datetime
    source_zip: str | None = None
    source_path: str
    index_path: str
    freshness_checked_at: datetime | None = None
    is_fresh: bool | None = None
