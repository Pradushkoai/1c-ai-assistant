"""Модели BSL-модулей 1С.

BslModule — один .bsl файл. Соответствует ObjectModule.bsl, ManagerModule.bsl,
Form/Module.bsl, CommonModule.bsl, CommandModule.bsl.
"""

from __future__ import annotations

from pydantic import Field

from .common import ModelConfig, ObjectRef


class Region(ModelConfig):
    """Область BSL-модуля (#Область ... #КонецОбласти).

    Области могут быть вложенными (parent поле).
    См. стандарты 1С: ПрограммныйИнтерфейс → СлужебныйПрограммныйИнтерфейс →
    СлужебныеПроцедурыИФункции → ОбработчикиСобытийФормы.
    """

    name: str = Field(description="Имя области, например 'ПрограммныйИнтерфейс'")
    start_line: int = Field(ge=1, description="Номер строки начала (1-based)")
    end_line: int = Field(ge=1, description="Номер строки конца (1-based)")
    parent: str | None = Field(
        default=None,
        description="Имя родительской области (для вложенных областей)",
    )
    methods: list[str] = Field(
        default_factory=list,
        description="Имена методов внутри области",
    )


class MethodParameter(ModelConfig):
    """Параметр метода BSL.

    BSL поддерживает:
    - передачу по значению (Знач) или по ссылке
    - значения по умолчанию (Параметр = 0)
    """

    name: str = Field(description="Имя параметра")
    by_value: bool = Field(
        default=False,
        description="True если передан по значению (с модификатором 'Знач')",
    )
    default_value: str | None = Field(
        default=None,
        description="Строковое представление значения по умолчанию",
    )
    has_default: bool = Field(
        default=False,
        description="True если параметр имеет значение по умолчанию",
    )


class Method(ModelConfig):
    """Метод BSL-модуля (процедура или функция).

    Методы бывают:
    - экспортные (Экспорт) — доступны из других модулей
    - асинхронные (Асинх) — только в клиентском контексте (BSL-ASYNC-001)
    - процедуры или функции
    """

    name: str = Field(description="Имя метода")
    is_export: bool = Field(default=False, description="True если метод экспортный")
    is_async: bool = Field(
        default=False,
        description="True если асинхронный (только клиентский контекст)",
    )
    is_procedure: bool = Field(
        description="True = процедура, False = функция",
    )
    parameters: list[MethodParameter] = Field(
        default_factory=list,
        description="Параметры метода в порядке объявления",
    )
    return_type_hint: str | None = Field(
        default=None,
        description="Подсказка типа возвращаемого значения (из комментариев или AST)",
    )
    start_line: int = Field(ge=1, description="Номер строки начала (1-based)")
    end_line: int = Field(ge=1, description="Номер строки конца (1-based)")
    region: str | None = Field(
        default=None,
        description="Имя области, в которой находится метод",
    )
    docstring: str | None = Field(
        default=None,
        description="Комментарий-документация перед методом",
    )
    cyclomatic_complexity: int | None = Field(
        default=None,
        ge=0,
        description="Цикломатическая сложность (если посчитана)",
    )


class BslModule(ModelConfig):
    """BSL-модуль целиком.

    Один .bsl файл = один BslModule. Соответствует:
    - ObjectModule.bsl — модуль объекта (Catalog, Document, ...)
    - ManagerModule.bsl — модуль менеджера
    - Form/Module.bsl — модуль формы
    - CommonModule.bsl — общий модуль
    - CommandModule.bsl — модуль команды

    Attributes:
        object_ref: ссылка на объект метаданных (Catalog.Товары, ...).
        module_kind: тип модуля (ObjectModule | ManagerModule | FormModule | ...).
        source: полный исходный код .bsl.
        methods: список методов модуля.
        regions: список областей модуля.
        line_count: количество строк в source.
        encoding: кодировка исходного файла (обычно 'utf-8').
        imports: список импортируемых модулей (из '#Использовать' или анализа).
        call_targets: имена вызываемых методов (для графа вызовов).
        parse_warnings: предупреждения парсера (например, regex fallback использован).
    """

    object_ref: ObjectRef = Field(
        description="Catalog.Товары, Document.Продажа, CommonModule.ОбщегоНазначения, ...",
    )
    module_kind: str = Field(
        description="ObjectModule | ManagerModule | FormModule | CommonModule | CommandModule",
    )
    source: str = Field(description="Полный исходный код .bsl")
    methods: list[Method] = Field(default_factory=list)
    regions: list[Region] = Field(default_factory=list)
    line_count: int = Field(ge=0)
    encoding: str = "utf-8"
    imports: list[str] = Field(
        default_factory=list,
        description="Используемые модули (из '#Использовать' или анализа)",
    )
    call_targets: list[str] = Field(
        default_factory=list,
        description="Имена вызываемых методов (для графа вызовов)",
    )
    parse_warnings: list[str] = Field(
        default_factory=list,
        description="Предупреждения парсера (regex fallback и т.д.)",
    )
