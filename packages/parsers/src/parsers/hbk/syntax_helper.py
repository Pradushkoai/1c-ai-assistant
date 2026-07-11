"""Парсер .hbk файлов синтакс-помощника 1С.

.hbk — бинарный формат (Container32), содержит структурированную справку
по методам платформы 1С.

Минимальная реализация для Sprint 3:
- Чтение .hbk файлов из директории
- Извлечение имён методов и их сигнатур через текстовый поиск
- Загрузка в SQLite platform-methods.db

Полная реализация (с ContextAvailability, version_since, и т.д.) — в Sprint 4.

См. ADR-0006 (Data Layer) и ADR-0012 (KB-as-code).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

from parsers.models import ContextAvailability, PlatformMethod

log = logging.getLogger(__name__)

# Regex для поиска имён методов в текстовом содержимом .hbk
# Ищем паттерны: ИмяМетода(параметры) — имя + скобки
_METHOD_CALL_RE = re.compile(
    r"\b([A-Za-zА-Яа-я_][A-Za-zА-Яа-я0-9_]*)\s*\(([^)]*)\)",
    re.MULTILINE,
)

# Сигнатуры методов (упрощённый поиск)
_SIGNATURE_RE = re.compile(
    r"([A-Za-zА-Яа-я_][A-Za-zА-Яа-я0-9_]*)\s*\(([^)]*)\)",
    re.MULTILINE,
)


def parse_hbk_directory(hbk_dir: Path) -> list[PlatformMethod]:
    """Распарсить все .hbk файлы в директории.

    Args:
        hbk_dir: директория с .hbk файлами (обычно shcntx_ru/).

    Returns:
        Список PlatformMethod.
    """
    methods: list[PlatformMethod] = []
    seen_names: set[str] = set()

    hbk_files = list(hbk_dir.rglob("*.hbk"))
    if not hbk_files:
        log.warning("No .hbk files found in %s", hbk_dir)
        return methods

    log.info("Parsing %d .hbk files from %s", len(hbk_files), hbk_dir)

    for hbk_file in hbk_files:
        try:
            file_methods = _parse_hbk_file(hbk_file)
            for method in file_methods:
                if method.name not in seen_names:
                    methods.append(method)
                    seen_names.add(method.name)
        except Exception as exc:
            log.warning("Failed to parse %s: %s", hbk_file, exc)

    log.info("Parsed %d unique platform methods", len(methods))
    return methods


def _parse_hbk_file(hbk_path: Path) -> list[PlatformMethod]:
    """Распарсить один .hbk файл.

    .hbk — бинарный формат, но содержит текстовые фрагменты.
    Извлекаем текст и ищем имена методов.

    Args:
        hbk_path: путь к .hbk файлу.

    Returns:
        Список PlatformMethod из этого файла.
    """
    methods: list[PlatformMethod] = []

    try:
        raw = hbk_path.read_bytes()
    except Exception as exc:
        log.warning("Cannot read %s: %s", hbk_path, exc)
        return methods

    # Извлекаем текст из бинарных данных (UTF-16LE или UTF-8 фрагменты)
    text = _extract_text(raw)
    if not text:
        return methods

    # Ищем имена методов через паттерн Имя(параметры)
    for match in _METHOD_CALL_RE.finditer(text):
        name = match.group(1)
        params = match.group(2).strip()

        if not name or len(name) < 3:
            continue

        # Пропускаем ключевые слова и слишком короткие имена
        skip_words = {
            "Процедура",
            "Функция",
            "Procedure",
            "Function",
            "Возврат",
            "Return",
            "Если",
            "Тогда",
            "Иначе",
            "ИначеЕсли",
            "КонецЕсли",
            "Для",
            "Каждого",
            "Из",
            "Цикл",
            "КонецЦикла",
            "Пока",
            "Новый",
            "Попытка",
            "Исключение",
            "КонецПопытки",
            "КонецПроцедуры",
            "КонецФункции",
            "Истина",
            "Ложь",
            "Неопределено",
            "NULL",
            "Экспорт",
            "Знач",
            "И",
            "ИЛИ",
            "НЕ",
        }
        if name in skip_words:
            continue

        # Сигнатура
        signature = f"{name}({params})" if params else f"{name}()"

        # Определяем is_procedure по контексту
        context_before = text[max(0, match.start() - 30) : match.start()]
        is_procedure = "Процедура" in context_before or "Procedure" in context_before

        method = PlatformMethod(
            name=name,
            signature=signature,
            description=f"Метод платформы 1С: {name}",
            is_procedure=is_procedure,
            availability=_guess_availability(name),
        )
        methods.append(method)

    return methods


def _extract_text(raw: bytes) -> str:
    """Извлечь текст из бинарных данных .hbk.

    .hbk содержит текст в UTF-16LE и/или UTF-8.
    Пытаемся UTF-8 сначала (более вероятно для текстовых fixture'ов),
    затем UTF-16LE (реальные .hbk файлы).
    """
    # Попытка UTF-8 (приоритет — текстовые файлы и fixture'ы)
    try:
        text_utf8 = raw.decode("utf-8", errors="strict")
        if len(text_utf8) > 10:
            return text_utf8
    except UnicodeDecodeError:
        pass

    # UTF-8 с errors=ignore (для смешанных бинарно-текстовых файлов)
    try:
        text_utf8_loose = raw.decode("utf-8", errors="ignore")
        if len(text_utf8_loose) > 50:
            return text_utf8_loose
    except Exception:
        pass

    # Попытка UTF-16LE (реальные .hbk файлы)
    try:
        text_utf16 = raw.decode("utf-16-le", errors="ignore")
        if len(text_utf16) > 50:
            return text_utf16
    except Exception:
        pass

    # Fallback: latin-1 (не потеряем данные, но могут быть артефакты)
    return raw.decode("latin-1", errors="ignore")


def _find_signature_near(text: str, pos: int, method_name: str) -> str | None:
    """Найти сигнатуру метода рядом с позицией.

    Args:
        text: полный текст.
        pos: позиция найденного имени метода.
        method_name: имя метода.

    Returns:
        Сигнатура (например, "ЗаписьЖурналаРегистрации(ИмяСобытия, Уровень, ...)") или None.
    """
    # Ищем в окне ±200 символов
    start = max(0, pos - 50)
    end = min(len(text), pos + 200)
    window = text[start:end]

    # Ищем pattern: method_name(parameters)
    pattern = re.escape(method_name) + r"\s*\(([^)]*)\)"
    match = re.search(pattern, window)
    if match:
        params = match.group(1).strip()
        return f"{method_name}({params})"

    return None


def _guess_availability(method_name: str) -> ContextAvailability:
    """Угадать доступность метода по имени (эвристика).

    Args:
        method_name: имя метода.

    Returns:
        ContextAvailability с предположениями.
    """
    # Методы, доступные только на сервере
    server_only = {
        "ЗаписьЖурналаРегистрации",
        "УровеньЖурналаРегистрации",
        "Метаданные",
        "ПараметрыСеанса",
        "Константы",
        "ФоновыеЗадания",
        "РегламентныеЗадания",
        "НайтиПоСсылкам",
        "Заблокировать",
        "Разблокировать",
        "Выполнить",
        "ВыполнитьПакет",
    }

    # Методы, доступные только на клиенте
    client_only = {
        "Асинх",
        "Ждать",
        "ПоказатьВопрос",
        "ПоказатьПредупреждение",
        "ОткрытьФорму",
        "Закрыть",
        "Оповестить",
        "ПоказатьЗначение",
        "ОткрытьЗначение",
    }

    if method_name in server_only:
        return ContextAvailability(
            server=True,
            thin_client=False,
            web_client=False,
            mobile_client=False,
            external_connection=True,
        )

    if method_name in client_only:
        return ContextAvailability(
            server=False,
            thin_client=True,
            web_client=True,
            mobile_client=True,
            external_connection=False,
        )

    # По умолчанию — доступно везде
    return ContextAvailability()


def load_methods_to_sqlite(
    methods: list[PlatformMethod],
    db_path: Path,
    platform_version: str,
) -> int:
    """Загрузить методы платформы в SQLite.

    Args:
        methods: список PlatformMethod.
        db_path: путь к .db файлу.
        platform_version: версия платформы.

    Returns:
        Количество загруженных методов.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS platform_methods (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                signature TEXT,
                description TEXT,
                is_procedure INTEGER DEFAULT 0,
                category TEXT,
                server INTEGER DEFAULT 1,
                thin_client INTEGER DEFAULT 1,
                web_client INTEGER DEFAULT 1,
                mobile_client INTEGER DEFAULT 0,
                external_connection INTEGER DEFAULT 1,
                source_file TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_methods_name
                ON platform_methods(name);

            CREATE TABLE IF NOT EXISTS platform_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )

        # Очищаем старые данные
        conn.execute("DELETE FROM platform_methods")

        # Вставляем методы
        for method in methods:
            avail = method.availability
            conn.execute(
                """INSERT INTO platform_methods
                   (name, signature, description, is_procedure, category,
                    server, thin_client, web_client, mobile_client, external_connection)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    method.name,
                    method.signature,
                    method.description,
                    1 if method.is_procedure else 0,
                    method.category,
                    1 if avail.server else 0,
                    1 if avail.thin_client else 0,
                    1 if avail.web_client else 0,
                    1 if avail.mobile_client else 0,
                    1 if avail.external_connection else 0,
                ),
            )

        # Метаданные
        from datetime import UTC, datetime

        conn.executemany(
            "INSERT OR REPLACE INTO platform_meta (key, value) VALUES (?, ?)",
            [
                ("platform_version", platform_version),
                ("loaded_at", datetime.now(UTC).isoformat()),
                ("methods_count", str(len(methods))),
            ],
        )
        conn.commit()

    log.info("Loaded %d methods to %s", len(methods), db_path)
    return len(methods)


def build_platform_methods_index(
    hbk_dir: Path,
    platform_version: str,
    db_path: Path,
) -> int:
    """Полный цикл: распарсить .hbk → загрузить в SQLite.

    Args:
        hbk_dir: директория с .hbk файлами.
        platform_version: версия платформы (например, '8.3.20').
        db_path: путь к .db файлу.

    Returns:
        Количество загруженных методов.
    """
    methods = parse_hbk_directory(hbk_dir)
    return load_methods_to_sqlite(methods, db_path, platform_version)
