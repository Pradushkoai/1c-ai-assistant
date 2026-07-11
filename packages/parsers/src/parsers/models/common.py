"""Базовые типы, общие для всех моделей проекта.

Все модели наследуются от ModelConfig (frozen + extra=forbid + strict).
См. ADR-0007 (Pydantic v2 frozen models).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ModelConfig(BaseModel):
    """Базовый конфиг для всех моделей проекта.

    Свойства:
    - frozen=True — иммутабельность (см. ADR-0007)
    - extra="forbid" — лишние поля вызывают ошибку (ловит опечатки)
    - strict=True — строгая типизация (int не конвертируется в str)
    - populate_by_name=True — alias → field name
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
        populate_by_name=True,
    )


class ObjectRef(ModelConfig):
    """Ссылка на объект метаданных 1С.

    Формат: 'Catalog.Контрагенты', 'Document.Реализация',
    'CommonModule.ОбщегоНазначения'.

    Examples:
        >>> ref = ObjectRef.from_string("Catalog.Товары")
        >>> ref.type
        'Catalog'
        >>> ref.name
        'Товары'
        >>> str(ref)
        'Catalog.Товары'
    """

    type: str = Field(description="Тип объекта: Catalog, Document, CommonModule, ...")
    name: str = Field(description="Имя объекта на русском")

    @classmethod
    def from_string(cls, ref: str) -> ObjectRef:
        """Парсинг 'Catalog.Контрагенты' → ObjectRef(type='Catalog', name='Контрагенты').

        Raises:
            ValueError: если строка не содержит '.' или пустая.
        """
        if not ref or "." not in ref:
            raise ValueError(f"Invalid ObjectRef: {ref!r}, expected 'Type.Name'")
        type_, name = ref.split(".", 1)
        if not type_ or not name:
            raise ValueError(f"Invalid ObjectRef: {ref!r}, both type and name required")
        return cls(type=type_, name=name)

    def __str__(self) -> str:
        return f"{self.type}.{self.name}"


class Version(ModelConfig):
    """Версия 1С: '8.3.20', '8.3.21.62'.

    Examples:
        >>> v = Version.from_string("8.3.20")
        >>> v.major, v.minor, v.patch
        (8, 3, 20)
        >>> str(v)
        '8.3.20'
        >>> v2 = Version.from_string("8.3.21.62")
        >>> v2.build
        62
        >>> str(v2)
        '8.3.21.62'
    """

    major: int = Field(ge=0)
    minor: int = Field(ge=0)
    patch: int = Field(ge=0)
    build: int | None = Field(default=None, ge=0)

    @classmethod
    def from_string(cls, version: str) -> Version:
        """Парсинг '8.3.20' или '8.3.21.62'.

        Raises:
            ValueError: если меньше 3 компонентов или нечисловые значения.
        """
        if not version:
            raise ValueError("Empty version string")
        parts = version.split(".")
        if len(parts) < 3:
            raise ValueError(f"Invalid version: {version!r}, expected at least 3 components")
        try:
            return cls(
                major=int(parts[0]),
                minor=int(parts[1]),
                patch=int(parts[2]),
                build=int(parts[3]) if len(parts) > 3 else None,
            )
        except ValueError as exc:
            raise ValueError(f"Invalid version components: {version!r}") from exc

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        return f"{s}.{self.build}" if self.build is not None else s


class ExecutionEnvironment(StrEnum):
    """Контекст выполнения BSL-кода.

    Используется в ContextAvailability для указания доступности методов.
    Источник: .hbk файлы синтакс-помощника.
    """

    SERVER = "server"
    THIN_CLIENT = "thin_client"
    WEB_CLIENT = "web_client"
    MOBILE_CLIENT = "mobile_client"
    RICH_CLIENT = "rich_client"
    EXTERNAL_CONNECTION = "external_connection"
    MOBILE_APPLICATION = "mobile_application"
    MOBILE_CLIENT_APPLICATION = "mobile_client_application"
    UNKNOWN = "unknown"


class ContextAvailability(ModelConfig):
    """Доступность метода платформы в контекстах.

    Источник: .hbk файлы синтакс-помощника.
    Используется kb.check_method_availability (см. ADR-0010).

    Defaults соответствуют большинству серверных методов —
    при парсинге .hbk поля уточняются.
    """

    server: bool = True
    thin_client: bool = True
    web_client: bool = True
    mobile_client: bool = False
    rich_client: bool = True
    external_connection: bool = True
    mobile_application: bool = False
    mobile_client_application: bool = False

    def available_in(self, env: ExecutionEnvironment) -> bool:
        """Проверка доступности в конкретном контексте.

        Args:
            env: контекст выполнения (server, thin_client, ...).

        Returns:
            True если метод доступен в данном контексте.

        Examples:
            >>> avail = ContextAvailability(server=True, thin_client=False)
            >>> avail.available_in(ExecutionEnvironment.SERVER)
            True
            >>> avail.available_in(ExecutionEnvironment.THIN_CLIENT)
            False
        """
        return bool(getattr(self, env.value, False))

    def to_dict(self) -> dict[str, bool]:
        """Сериализация в dict (для JSON output)."""
        return {
            "server": self.server,
            "thin_client": self.thin_client,
            "web_client": self.web_client,
            "mobile_client": self.mobile_client,
            "rich_client": self.rich_client,
            "external_connection": self.external_connection,
            "mobile_application": self.mobile_application,
            "mobile_client_application": self.mobile_client_application,
        }
