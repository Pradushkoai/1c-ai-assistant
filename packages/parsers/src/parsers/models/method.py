"""Методы и свойства платформы 1С.

Источник: .hbk файлы синтакс-помощника (8141 методов в платформе 8.3.20).
Используется kb.check_method_availability для валидации контекста.
"""

from __future__ import annotations

from pydantic import Field

from .common import ContextAvailability, ModelConfig, Version


class PlatformMethod(ModelConfig):
    """Метод платформы 1С.

    Источник: .hbk файлы синтакс-помощника.
    Используется kb.check_method_availability (см. ADR-0010).

    Attributes:
        name: имя метода, например 'ЗаписьЖурналаРегистрации'.
        signature: полная сигнатура с параметрами.
        description: описание из синтакс-помощника.
        is_procedure: True = процедура, False = функция.
        return_type: тип возвращаемого значения (для функций).
        availability: доступность в контекстах (server, thin_client, ...).
        version_since: версия, в которой метод добавлен.
        version_deprecated: версия, в которой метод устарел.
        deprecated_replacement: чем заменить устаревший метод.
        category: категория (Глобальный контекст, Документы, ...).
        examples: список примеров использования.
    """

    name: str = Field(description="Имя метода, например 'ЗаписьЖурналаРегистрации'")
    signature: str = Field(description="Полная сигнатура с параметрами")
    description: str = Field(description="Описание из синтакс-помощника")
    is_procedure: bool = Field(
        description="True = процедура, False = функция",
    )
    return_type: str | None = Field(
        default=None,
        description="Тип возвращаемого значения (для функций)",
    )
    availability: ContextAvailability = Field(
        default_factory=ContextAvailability,
        description="Доступность в контекстах",
    )
    version_since: Version | None = Field(
        default=None,
        description="Версия, в которой метод добавлен",
    )
    version_deprecated: Version | None = Field(
        default=None,
        description="Версия, в которой метод устарел",
    )
    deprecated_replacement: str | None = Field(
        default=None,
        description="Чем заменить устаревший метод",
    )
    category: str = Field(
        default="Uncategorized",
        description="Категория: Глобальный контекст, Документы, ...",
    )
    examples: list[str] = Field(
        default_factory=list,
        description="Примеры использования",
    )


class PlatformProperty(ModelConfig):
    """Свойство платформы (например, Метаданные, ПараметрыСеанса).

    Источник: .hbk файлы синтакс-помощника.

    Attributes:
        name: имя свойства.
        description: описание.
        type: тип значения.
        availability: доступность в контекстах.
        version_since: версия, в которой свойство добавлено.
        version_deprecated: версия, в которой свойство устарело.
    """

    name: str
    description: str
    type: str
    availability: ContextAvailability = Field(default_factory=ContextAvailability)
    version_since: Version | None = None
    version_deprecated: Version | None = None
