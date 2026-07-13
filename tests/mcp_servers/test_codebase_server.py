"""Тесты для mcp_servers.codebase — CodebaseServer (4 tools).

Sprint 4.2 (TD-S4.2-02 ч.2): codebase MCP server.
Тестирует на InMemoryVectorStore (без postgres).
Мокает embed_texts чтобы не загружать модель.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_servers.codebase import CodebaseServer, InMemoryVectorStore


def _mock_embed_texts(texts: list[str]) -> list[list[float]]:
    """Мок для embed_texts — возвращает детерминированные векторы."""
    results: list[list[float]] = []
    for t in texts:
        # Простой hash-based вектор (детерминированный)
        vec = [float(len(t) % 10) / 10.0] * 1024
        results.append(vec)
    return results


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def vector_store() -> InMemoryVectorStore:
    """InMemoryVectorStore с тестовыми чанками."""
    store = InMemoryVectorStore()

    # Добавляем тестовые чанки (имитация embeddings)
    chunks = [
        {
            "chunk_id": "test_CommonModule_Модуль_Метод1",
            "source_layer": "config",
            "source_config": "test",
            "source_version": "1.0",
            "platform_version": "8.3.25",
            "module_kind": "CommonModule",
            "object_ref": "CommonModule.Модуль",
            "method_name": "Метод1",
            "is_export": True,
            "is_function": True,
            "parameters": ["А"],
            "code_text": "Функция Метод1(А) Экспорт Возврат А КонецФункции",
            "embedding": [0.1, 0.2, 0.3] + [0.0] * 1021,
        },
        {
            "chunk_id": "test_CommonModule_Модуль_Метод2",
            "source_layer": "config",
            "source_config": "test",
            "source_version": "1.0",
            "platform_version": "8.3.25",
            "module_kind": "CommonModule",
            "object_ref": "CommonModule.Модуль",
            "method_name": "Метод2",
            "is_export": True,
            "is_function": False,
            "parameters": ["Б"],
            "code_text": "Процедура Метод2(Б) Экспорт Сообщить(Б) КонецПроцедуры",
            "embedding": [0.2, 0.3, 0.4] + [0.0] * 1021,
        },
        {
            "chunk_id": "test_CommonModule_Другой_Метод3",
            "source_layer": "library",
            "source_config": "БСП",
            "source_version": "3.1",
            "platform_version": "8.3.25",
            "module_kind": "CommonModule",
            "object_ref": "CommonModule.Другой",
            "method_name": "Метод3",
            "is_export": True,
            "is_function": True,
            "parameters": [],
            "code_text": "Функция Метод3() Экспорт Возврат 42 КонецФункции",
            "embedding": [0.9, 0.1, 0.0] + [0.0] * 1021,
        },
    ]

    asyncio.run(store.upsert_chunks(chunks))
    return store


@pytest.fixture
def server(vector_store: InMemoryVectorStore) -> CodebaseServer:
    """CodebaseServer с InMemoryVectorStore."""
    return CodebaseServer(vector_store=vector_store)


# ─── Tests: semantic_search ────────────────────────────────────────────────


class TestSemanticSearch:
    @pytest.mark.asyncio
    async def test_returns_output(self, server: CodebaseServer):
        with patch("parsers.indexers.embeddings_indexer.embed_texts", side_effect=_mock_embed_texts):
            result = await server.semantic_search(
                query="Метод1",
                config_name="test",
                config_version="1.0",
            )
        assert result.query == "Метод1"
        assert isinstance(result.results, list)

    @pytest.mark.asyncio
    async def test_finds_method(self, server: CodebaseServer):
        """Поиск по имени метода находит его."""
        with patch("parsers.indexers.embeddings_indexer.embed_texts", side_effect=_mock_embed_texts):
            result = await server.semantic_search(
                query="Метод1",
                config_name="test",
                config_version="1.0",
            )
        assert len(result.results) > 0
        # Должен найти Метод1 (BM25 match)
        methods = [r.get("method", "") for r in result.results]
        assert "Метод1" in methods

    @pytest.mark.asyncio
    async def test_filters_by_config(self, server: CodebaseServer):
        """Фильтр по config — не находит чанки из БСП."""
        with patch("parsers.indexers.embeddings_indexer.embed_texts", side_effect=_mock_embed_texts):
            result = await server.semantic_search(
                query="Метод",
                config_name="test",
                config_version="1.0",
            )
        # Все результаты должны быть из test/1.0
        for r in result.results:
            assert "БСП" not in r.get("module", "")

    @pytest.mark.asyncio
    async def test_empty_query(self, server: CodebaseServer):
        """Пустой запрос — пустые результаты или все."""
        with patch("parsers.indexers.embeddings_indexer.embed_texts", side_effect=_mock_embed_texts):
            result = await server.semantic_search(
                query="",
                config_name="test",
                config_version="1.0",
            )
        assert isinstance(result.results, list)


# ─── Tests: get_module ─────────────────────────────────────────────────────


class TestGetModule:
    @pytest.mark.asyncio
    async def test_not_found_raises(self, server: CodebaseServer):
        """Несуществующий модуль — ValueError."""
        with pytest.raises(ValueError, match="Module not found"):
            await server.get_module(
                object_ref="CommonModule.Несуществующий",
                module_kind="CommonModule",
                config_name="test",
                config_version="1.0",
            )


# ─── Tests: get_similar ────────────────────────────────────────────────────


class TestGetSimilar:
    @pytest.mark.asyncio
    async def test_returns_output(self, server: CodebaseServer):
        result = await server.get_similar(
            object_ref="CommonModule.Модуль",
            config_name="test",
            config_version="1.0",
        )
        assert result.object_ref == "CommonModule.Модуль"
        assert isinstance(result.similar, list)

    @pytest.mark.asyncio
    async def test_excludes_self(self, server: CodebaseServer):
        """Результат не включает сам объект."""
        result = await server.get_similar(
            object_ref="CommonModule.Модуль",
            config_name="test",
            config_version="1.0",
        )
        for s in result.similar:
            assert s.get("module") != "CommonModule.Модуль"

    @pytest.mark.asyncio
    async def test_not_found(self, server: CodebaseServer):
        """Несуществующий объект — пустой список."""
        result = await server.get_similar(
            object_ref="CommonModule.Несуществующий",
            config_name="test",
            config_version="1.0",
        )
        assert result.similar == []


# ─── Tests: call_graph ─────────────────────────────────────────────────────


class TestCallGraph:
    @pytest.mark.asyncio
    async def test_not_found_raises(self, server: CodebaseServer):
        """Нет call-graph.json — ValueError."""
        with pytest.raises(ValueError, match="Call graph not found"):
            await server.call_graph(
                config_name="nonexistent",
                config_version="0.0",
            )
