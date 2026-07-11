# ADR-0017: VectorStoreProtocol — pgvector по умолчанию, Qdrant как опция

**Статус:** Accepted
**Дата:** 2026-07-11
**Связан:** Уточняет ADR-0015

## Контекст

При обсуждении ADR-0015 (3-container deployment с pgvector) пользователь задал критичный вопрос:

> «Не пошли ли мы здесь по пути ухудшения конечного результата решения задачи?»

Анализ показал:
- Качество search = embedding_model (80%) × vector_db (20%)
- На 100k векторов (наш масштаб) разница recall между pgvector и Qdrant = 1-2%
- Но Qdrant объективно лучше в: filtered search, product quantization, native cosine optimizations
- Без абстракции — переключение с pgvector на Qdrant = переписывание `codebase/server.py`

Принципиальное решение: **не верить на слово, а сделать измеримое переключение**.

## Решение

**`VectorStoreProtocol` — контракт с 2 реализациями:**

1. **`PgVectorStore`** (по умолчанию) — использует pgvector в существующем postgres контейнере
2. **`QdrantVectorStore`** (опционально) — использует отдельный Qdrant контейнер

Переключение через env var: `VECTOR_STORE=pgvector|qdrant` (по умолчанию `pgvector`).

### Контракт

```python
# packages/mcp_servers/src/mcp_servers/codebase/vector_store.py
from typing import Protocol, runtime_checkable
from parsers.models import BslModule


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """Контракт векторного хранилища для codebase-server."""

    async def upsert(self, modules: list[BslModule]) -> int:
        """Добавить/обновить модули. Возвращает количество записанных."""
        ...

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[dict]:
        """Поиск ближайших соседей.

        filters: {'module_kind': 'ObjectModule', 'object_type': 'Document'}
        Возвращает: [{module_id, score, object_ref}]
        """
        ...

    async def delete(self, config_name: str, config_version: str) -> int:
        """Удалить все векторы конфигурации. Возвращает количество удалённых."""
        ...

    async def count(self, config_name: str, config_version: str) -> int:
        """Количество векторов для конфигурации."""
        ...

    async def health(self) -> bool:
        """Health check."""
        ...
```

### Реализация по умолчанию: PgVectorStore

```python
# packages/mcp_servers/src/mcp_servers/codebase/vector_stores/pgvector_store.py
class PgVectorStore:
    """Реализация через pgvector (extension postgres).

    Использует существующий postgres контейнер (см. ADR-0015).
    Таблица bsl_modules с колонкой embedding VECTOR(384).
    """

    def __init__(self, dsn: str, embedding_dim: int = 384) -> None:
        self.dsn = dsn
        self.embedding_dim = embedding_dim
        # инициализация psycopg pool

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[dict]:
        # SELECT module_id, 1 - (embedding <=> %s) as score
        # FROM bsl_modules
        # WHERE config_name = %s AND module_kind = %s  -- filters
        # ORDER BY embedding <=> %s
        # LIMIT %s
        ...

    # ... остальные методы
```

### Опциональная реализация: QdrantVectorStore

```python
# packages/mcp_servers/src/mcp_servers/codebase/vector_stores/qdrant_store.py
class QdrantVectorStore:
    """Реализация через Qdrant.

    Требует отдельный контейнер (добавляется в docker-compose при включении).
    Collection: 'bsl_modules' с payload index для filters.
    """

    def __init__(self, url: str, api_key: str | None = None) -> None:
        from qdrant_client import AsyncQdrantClient
        self.client = AsyncQdrantClient(url=url, api_key=api_key)

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[dict]:
        # self.client.search(
        #     collection_name="bsl_modules",
        #     query_vector=query_embedding,
        #     query_filter=Filter(must=[...]),
        #     limit=top_k,
        # )
        ...

    # ... остальные методы
```

### Фабрика

```python
# packages/mcp_servers/src/mcp_servers/codebase/vector_store_factory.py
import os
from .vector_store import VectorStoreProtocol


def make_vector_store() -> VectorStoreProtocol:
    """Создать VectorStore по env var VECTOR_STORE.

    По умолчанию: pgvector.
    Опционально: qdrant (требует VECTOR_STORE=qdrant и QDRANT_URL).
    """
    backend = os.environ.get("VECTOR_STORE", "pgvector").lower()

    if backend == "qdrant":
        from .vector_stores.qdrant_store import QdrantVectorStore
        return QdrantVectorStore(
            url=os.environ["QDRANT_URL"],
            api_key=os.environ.get("QDRANT_API_KEY"),
        )

    if backend == "pgvector":
        from .vector_stores.pgvector_store import PgVectorStore
        return PgVectorStore(
            dsn=os.environ["DATABASE_URL"],
            embedding_dim=int(os.environ.get("EMBEDDING_DIM", "384")),
        )

    raise ValueError(f"Unknown VECTOR_STORE: {backend}")
```

### Использование в codebase-server

```python
# packages/mcp_servers/src/mcp_servers/codebase/server.py
class CodebaseServer:
    def __init__(self) -> None:
        self.vector_store = make_vector_store()  # из фабрики
        # BM25 через postgres tsvector — остаётся в обоих случаях

    async def semantic_search(self, query: str, ...) -> dict:
        # 1. BM25 через postgres (всегда postgres, не зависит от vector store)
        bm25_results = await self._bm25_search(query, ...)

        # 2. Vector через VectorStoreProtocol
        query_embedding = await self._embed(query)
        vector_results = await self.vector_store.search(
            query_embedding=query_embedding,
            top_k=20,
            filters={"config_name": config_name, "config_version": config_version},
        )

        # 3. RRF reranker (не зависит от vector store)
        return self._rrf_fuse(bm25_results, vector_results)[:top_k]
```

## Деплой — 2 варианта

### Вариант A: pgvector (по умолчанию, 3 контейнера)

```yaml
# docker-compose.yml
services:
  1c-ai-app:
    environment:
      - VECTOR_STORE=pgvector          # по умолчанию
      - DATABASE_URL=postgresql://...
  1c-ai-bsl-ls:
    # ...
  postgres:
    image: pgvector/pgvector:pg16
    # ...
```

### Вариант B: Qdrant (4 контейнера)

```yaml
# docker-compose.qdrant.yml (override)
services:
  1c-ai-app:
    environment:
      - VECTOR_STORE=qdrant
      - QDRANT_URL=http://qdrant:6333
  qdrant:
    image: qdrant/qdrant:v1.12.0
    volumes:
      - qdrant_data:/qdrant/storage
    ports:
      - "6333:6333"

volumes:
  qdrant_data:
```

Запуск: `docker compose -f docker-compose.yml -f docker-compose.qdrant.yml up`

## Бенчмарк-тест (обязательный в спринте 4)

```python
# tests/codebase/test_vector_store_benchmark.py
"""
Цель: объективно сравнить PgVectorStore vs QdrantVectorStore
на реальных 1С-данных.

Запуск: pytest tests/codebase/test_vector_store_benchmark.py -v --benchmark-only
Решение: если PgVectorStore даёт recall@10 < 95% — переключаемся на Qdrant по умолчанию.
"""
import pytest
from mcp_servers.codebase.vector_stores.pgvector_store import PgVectorStore
from mcp_servers.codebase.vector_stores.qdrant_store import QdrantVectorStore


@pytest.fixture
def test_queries() -> list[dict]:
    """100 тестовых запросов с известными релевантными модулями.

    Источник: размеченные вручную запросы + правильные ответы.
    Пример: {'query': 'ОбработкаПроведения', 'relevant': ['Document.Реализация.ObjectModule']}
    """
    return [
        {'query': 'ОбработкаПроведения', 'relevant': ['Document.Реализация.ObjectModule']},
        {'query': 'движения по регистру при проведении', 'relevant': [...]},
        # ... 100 запросов
    ]


@pytest.mark.benchmark
async def test_pgvector_recall(test_queries):
    store = PgVectorStore(dsn="postgresql://...")
    recall = await _measure_recall(store, test_queries, k=10)
    print(f"PgVectorStore recall@10: {recall:.2%}")
    assert recall > 0.90  # минимум


@pytest.mark.benchmark
async def test_qdrant_recall(test_queries):
    store = QdrantVectorStore(url="http://localhost:6333")
    recall = await _measure_recall(store, test_queries, k=10)
    print(f"QdrantVectorStore recall@10: {recall:.2%}")
    assert recall > 0.90


async def _measure_recall(store, queries, k=10) -> float:
    """Средний recall@k по всем запросам."""
    hits = 0
    total = 0
    for q in queries:
        embedding = await _embed(q['query'])
        results = await store.search(query_embedding=embedding, top_k=k)
        found = {r['object_ref'] for r in results}
        if any(rel in found for rel in q['relevant']):
            hits += 1
        total += 1
    return hits / total
```

**Критерий переключения на Qdrant по умолчанию:**
- PgVectorStore recall@10 < 95% на наших данных
- ИЛИ QdrantVectorStore recall@10 > PgVectorStore recall@10 + 3%

## Что НЕ зависит от выбора VectorStore

- **Embedding model** — BGE-M3 (multilingual) или OpenAI text-embedding-3-large в любом случае
- **BM25** — postgres tsvector + GIN (всегда postgres, не зависит от vector store)
- **RRF reranker** — объединение BM25 + vector (одинаковая логика)
- **MCP контракт `codebase.semantic_search`** — не меняется
- **TOOL_GROUPS** — GATHERER имеет `codebase.semantic_search`, не меняется
- **Pipeline contracts** — `GatheredCode.similar_modules` не меняется

## Последствия

### Положительные
- Объективное измерение, не вера на слово
- Возможность переключения без переписывания кода (1 env var)
- Начинаем с pgvector (3 контейнера) — меньше инфры
- Если измеримо увидим проблемы — переключаем на Qdrant (4 контейнера)
- Контракт `VectorStoreProtocol` — тестируемый, mock'аемый

### Отрицательные
- 2 реализации вместо 1 (но обе тонкие, ~150 строк каждая)
- Бенчмарк-тест требует размеченных запросов (100 штук, ручная работа в спринте 4)
- Зависимость `qdrant-client` в `[project.optional-dependencies]` (не в основных deps)

## Path migration

```
Спринт 1-3: только PgVectorStore, VECTOR_STORE=pgvector (3 контейнера)
Спринт 4:   + QdrantVectorStore + бенчмарк-тест
            По результатам бенчмарка — решение о дефолте
            Если Qdrant лучше на >3% recall — переключаем дефолт
            (4 контейнера становится стандартом)
Production:  по факту использования
```

## Связанные документы
- ADR-0015 (3-container deployment — pgvector по умолчанию)
- ADR-0010 (MCP tool contracts — codebase.semantic_search)
- 05-mcp-tool-contracts.md (раздел 4: codebase-server)
- 09-error-taxonomy.md (ToolError для vector store ошибок)
