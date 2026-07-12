"""Embeddings indexer — генерация векторов для BSL-методов.

Sprint 4.2 (TD-S4.2-02): codebase MCP — семантический поиск по коду.

Модель: intfloat/multilingual-e5-large (1024 dim, мультилингвальный)
Запуск: локально через fastembed (бесплатно, не требует API ключа)

Chunking: по export-методам (ADR-0020). Каждый chunk = сигнатура + тело.
Multi-layer metadata: source_layer, source_config, source_version, platform_version.

См. ADR-0020 (Embeddings strategy), ADR-0017 (VectorStoreProtocol).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Модель embeddings (ADR-0020: BGE-M3 был запланирован, но недоступен в fastembed.
# multilingual-e5-large — 1024 dim, мультилингвальный, 100+ языков включая русский.)
EMBEDDINGS_MODEL = "intfloat/multilingual-e5-large"
EMBEDDINGS_DIM = 1024
EMBEDDINGS_MODEL_VERSION = "multilingual-e5-large-v1"

# Singleton модели (загрузка ~5 сек, не повторять)
_model: Any = None


def _get_model() -> Any:
    """Получить singleton TextEmbedding model."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        log.info("Loading embeddings model: %s", EMBEDDINGS_MODEL)
        _model = TextEmbedding(model_name=EMBEDDINGS_MODEL)
        log.info("Model loaded: dim=%d", EMBEDDINGS_DIM)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Сгенерировать embeddings для списка текстов.

    Args:
        texts: список BSL-кода (по одному чанку на элемент).

    Returns:
        Список векторов (каждый 1024 dim).
    """
    if not texts:
        return []

    model = _get_model()
    embeddings = list(model.embed(texts))
    return [e.tolist() for e in embeddings]


def build_embeddings_index(
    config_dir: Path,
    config_name: str,
    config_version: str,
    platform_version: str = "8.3.25",
    source_layer: str = "config",
) -> dict[str, Any]:
    """Построить индекс embeddings для конфигурации или библиотеки.

    Чанкует BSL-код по export-методам, генерирует векторы, добавляет metadata.

    Args:
        config_dir: директория с исходным кодом.
        config_name: имя конфигурации/библиотеки.
        config_version: версия.
        platform_version: версия платформы 1С.
        source_layer: 'config' | 'library' (по ADR-0020).

    Returns:
        Словарь с chunks и embeddings:
        {
            "config_name": "...",
            "source_layer": "config",
            "model": "multilingual-e5-large",
            "model_version": "multilingual-e5-large-v1",
            "dim": 1024,
            "chunks": [{
                "chunk_id": "ut11_4.5.3_CommonModule_Модуль_Метод",
                "source_layer": "config",
                "source_config": "ut11",
                "source_version": "4.5.3",
                "platform_version": "8.3.25",
                "module_kind": "CommonModule",
                "object_ref": "CommonModule.Модуль",
                "method_name": "Метод",
                "is_export": true,
                "is_function": true,
                "parameters": ["А", "Б"],
                "code_text": "Функция Метод(А, Б) Экспорт ...",
                "embedding": [0.1, 0.2, ...]  // 1024 dim
            }],
            "stats": {"total_chunks": N, "total_embeddings": M},
            "generated_at": "..."
        }
    """
    if not config_dir.exists():
        raise FileNotFoundError(f"Directory not found: {config_dir}")

    log.info(
        "Building embeddings index for %s/%s (layer=%s)",
        config_name, config_version, source_layer,
    )

    from parsers.bsl.module import parse_bsl_module
    from parsers.indexers.api_reference_indexer import _guess_module_info

    bsl_files = list(config_dir.rglob("*.bsl"))
    log.info("Found %d .bsl files", len(bsl_files))

    # ─── Проход 1: собираем чанки ────────────────────────────────────────────
    chunks: list[dict[str, Any]] = []

    for bsl_path in bsl_files:
        try:
            code = bsl_path.read_text(encoding="utf-8-sig", errors="replace")
            if not code.strip():
                continue

            module = parse_bsl_module(code)
            module_kind, object_ref = _guess_module_info(bsl_path, config_dir)

            for method in module.methods:
                if not method.is_export:
                    continue

                # Извлекаем код метода
                method_code = _extract_method_code(code, method.name)

                chunk = {
                    "chunk_id": f"{config_name}_{config_version}_{object_ref}_{method.name}",
                    "source_layer": source_layer,
                    "source_config": config_name,
                    "source_version": config_version,
                    "platform_version": platform_version,
                    "module_kind": module_kind,
                    "object_ref": object_ref,
                    "method_name": method.name,
                    "is_export": method.is_export,
                    "is_function": not method.is_procedure,
                    "parameters": [p.name for p in method.parameters],
                    "code_text": method_code,
                    "embedding": None,  # будет заполнен в проходе 2
                }
                chunks.append(chunk)

        except Exception as exc:
            log.debug("Failed to parse %s: %s", bsl_path, exc)

    log.info("Pass 1: %d chunks (export methods)", len(chunks))

    # ─── Проход 2: генерируем embeddings ─────────────────────────────────────
    if chunks:
        texts = [_format_chunk_text(c) for c in chunks]
        log.info("Generating embeddings for %d chunks...", len(texts))

        embeddings = embed_texts(texts)
        for i, emb in enumerate(embeddings):
            chunks[i]["embedding"] = emb

        log.info("Embeddings generated: %d × %d dim", len(embeddings), EMBEDDINGS_DIM)

    return {
        "config_name": config_name,
        "config_version": config_version,
        "source_layer": source_layer,
        "model": EMBEDDINGS_MODEL,
        "model_version": EMBEDDINGS_MODEL_VERSION,
        "dim": EMBEDDINGS_DIM,
        "chunks": chunks,
        "stats": {
            "total_chunks": len(chunks),
            "total_embeddings": sum(1 for c in chunks if c.get("embedding") is not None),
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def save_embeddings_index(emb_index: dict[str, Any], output_path: Path) -> None:
    """Сохранить индекс embeddings в JSON.

    Внимание: файл может быть большим (27k chunks × 1024 dim × ~10 bytes = ~280 MB).
    Для production использовать pgvector (см. VectorStoreProtocol), не JSON.
    JSON — для тестирования и отладки.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(emb_index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    size_mb = output_path.stat().st_size / (1024 * 1024)
    log.info("Embeddings index saved to %s (%.1f MB)", output_path, size_mb)


def load_embeddings_index(index_path: Path) -> dict[str, Any] | None:
    """Загрузить индекс embeddings из JSON."""
    if not index_path.exists():
        return None
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


# ─── Внутренние функции ─────────────────────────────────────────────────────


def _extract_method_code(full_code: str, method_name: str) -> str:
    """Извлечь код метода по имени из полного текста модуля.

    Ищет 'Процедура Имя(' или 'Функция Имя(' и возвращает до 'КонецПроцедуры'/'КонецФункции'.
    """
    import re

    # Паттерн: Процедура/Функция Имя(...) ... КонецПроцедуры/КонецФункции
    pattern = rf"(Процедура|Функция)\s+{re.escape(method_name)}\s*\([^)]*\).*?Конец\1"
    match = re.search(pattern, full_code, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(0).strip()

    # Fallback: возвращаем имя метода
    return method_name


def _format_chunk_text(chunk: dict[str, Any]) -> str:
    """Форматировать текст чанка для embeddings.

    Включает: сигнатуру + тело метода + metadata.
    Это даёт вектору контекст — что это за метод и откуда.
    """
    parts: list[str] = []

    # Сигнатура
    params = ", ".join(chunk.get("parameters", []))
    kind = "Функция" if chunk.get("is_function") else "Процедура"
    parts.append(f"{kind} {chunk['method_name']}({params})")

    # Код метода
    code_text = chunk.get("code_text", "")
    if code_text:
        parts.append(code_text)

    return "\n".join(parts)
