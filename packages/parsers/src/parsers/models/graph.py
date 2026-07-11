"""Графы зависимостей и вызовов.

DependencyEdge — ребро графа зависимостей метаданных (A ссылается на B).
CallEdge — ребро графа вызовов BSL-методов.
GraphStats — статистика графа.
"""

from __future__ import annotations

from pydantic import Field

from .common import ModelConfig, ObjectRef


class DependencyEdge(ModelConfig):
    """Ребро графа зависимостей метаданных.

    A зависит от B (A references B в XML).

    Examples:
        Catalog.Товары зависит от Catalog.Контрагенты (владелец).
        Document.Продажа зависит от AccumulationRegister.Продажи (register_records).

    Attributes:
        source: кто ссылается.
        target: на кого ссылаются.
        edge_type: тип ссылки (Attribute | Form | TabularSection | Template | Command).
        detail: какой именно атрибут/форма ссылается (опционально).
    """

    source: ObjectRef
    target: ObjectRef
    edge_type: str = Field(
        description="Тип ссылки: Attribute | Form | TabularSection | Template | Command",
    )
    detail: str | None = Field(
        default=None,
        description="Какой именно атрибут/форма ссылается",
    )


class CallEdge(ModelConfig):
    """Ребро графа вызовов BSL-методов.

    Метод source_method модуля source_module вызывает метод target_method
    (из модуля target_module или того же source_module).

    Attributes:
        source_module: модуль, откуда вызывают.
        source_method: метод, откуда вызывают.
        target_module: модуль, который вызывают (None = тот же).
        target_method: метод, который вызывают.
        line: номер строки вызова.
        is_platform: True если вызывается метод платформы, False если метод конфигурации.
    """

    source_module: ObjectRef
    source_method: str
    target_module: ObjectRef | None = Field(
        default=None,
        description="None = вызов в том же модуле",
    )
    target_method: str
    line: int = Field(ge=1, description="Номер строки вызова")
    is_platform: bool = Field(
        default=False,
        description="True = метод платформы, False = метод конфигурации",
    )


class GraphStats(ModelConfig):
    """Статистика графа.

    Attributes:
        nodes: количество узлов.
        edges: количество рёбер.
        cycles: количество циклов.
        avg_degree: средняя степень узла.
        top_hubs: топ-10 узлов по степени (самых связанных).
    """

    nodes: int = Field(ge=0)
    edges: int = Field(ge=0)
    cycles: int = Field(ge=0)
    avg_degree: float = Field(ge=0.0)
    top_hubs: list[str] = Field(
        default_factory=list,
        description="Топ-10 узлов по степени (самых связанных)",
    )
