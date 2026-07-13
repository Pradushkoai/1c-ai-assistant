"""VectorStoreProtocol — контракт векторного хранилища для codebase MCP.

ADR-0017: pgvector по умолчанию, Qdrant как опция.
ADR-0020: multi-layer metadata, гибридный поиск BM25+vector+RRF.

Production: postgres с pgvector.
Tests: mock реализация (InMemoryVectorStore).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

log = logging.getLogger(__name__)


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """Контракт векторного хранилища для codebase-server.

    Реализации:
    - PgVectorStore: postgres + pgvector (production, ADR-0015)
    - InMemoryVectorStore: для тестов (не production)
    """

    async def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """Добавить/обновить чанки с embeddings.

        Args:
            chunks: список чанков с embedding, metadata, code_text.

        Returns:
            Количество записанных чанков.
        """
        ...

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Векторный поиск ближайших чанков.

        Args:
            query_embedding: вектор запроса (1024 dim).
            top_k: максимум результатов.
            filters: {'source_layer': 'config', 'source_config': 'ut11'}.

        Returns:
            Список чанков [{chunk_id, score, code_text, metadata}, ...].
        """
        ...

    async def search_bm25(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """BM25 (полнотекстовый) поиск.

        Args:
            query: текст запроса.
            top_k: максимум результатов.
            filters: фильтры по metadata.

        Returns:
            Список чанков [{chunk_id, score, code_text, metadata}, ...].
        """
        ...

    async def search_hybrid(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        rrf_k: int = 60,
    ) -> list[dict[str, Any]]:
        """Гибридный поиск BM25 + vector + RRF (ADR-0020).

        Args:
            query: текст запроса (для BM25).
            query_embedding: вектор запроса (для vector search).
            top_k: максимум результатов.
            filters: фильтры по metadata.
            rrf_k: параметр RRF (default 60).

        Returns:
            Список чанков [{chunk_id, rrf_score, code_text, metadata}, ...].
        """
        ...

    async def delete_by_source(self, source_config: str, source_version: str | None = None) -> int:
        """Удалить чанки по источнику.

        Args:
            source_config: имя конфигурации/библиотеки.
            source_version: версия (если None — все версии).

        Returns:
            Количество удалённых.
        """
        ...

    async def health_check(self) -> bool:
        """Проверить доступность хранилища."""
        ...


# ─── InMemoryVectorStore (для тестов) ───────────────────────────────────────


class InMemoryVectorStore:
    """In-memory реализация для тестов. НЕ для production."""

    def __init__(self) -> None:
        self._chunks: list[dict[str, Any]] = []

    async def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        for chunk in chunks:
            # Заменяем если chunk_id совпадает
            self._chunks = [c for c in self._chunks if c.get("chunk_id") != chunk.get("chunk_id")]
            self._chunks.append(chunk)
        return len(chunks)

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:

        filtered = self._apply_filters(filters)

        results: list[dict[str, Any]] = []
        for chunk in filtered:
            emb = chunk.get("embedding")
            if emb is None:
                continue
            # Cosine similarity
            score = _cosine_similarity(query_embedding, emb)
            results.append({
                "chunk_id": chunk.get("chunk_id"),
                "score": score,
                "code_text": chunk.get("code_text", ""),
                "metadata": {k: v for k, v in chunk.items() if k != "embedding" and k != "code_text"},
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def search_bm25(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        # Упрощённый BM25: substring match + tf scoring
        filtered = self._apply_filters(filters)
        query_terms = query.lower().split()

        results: list[dict[str, Any]] = []
        for chunk in filtered:
            code = chunk.get("code_text", "").lower()
            score = sum(1.0 for term in query_terms if term in code) / max(len(query_terms), 1)
            if score > 0:
                results.append({
                    "chunk_id": chunk.get("chunk_id"),
                    "score": score,
                    "code_text": chunk.get("code_text", ""),
                    "metadata": {k: v for k, v in chunk.items() if k != "embedding" and k != "code_text"},
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def search_hybrid(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        rrf_k: int = 60,
    ) -> list[dict[str, Any]]:
        # RRF: 1/(k + rank_bm25) + 1/(k + rank_vector)
        bm25_results = await self.search_bm25(query, top_k=top_k * 2, filters=filters)
        vector_results = await self.search(query_embedding, top_k=top_k * 2, filters=filters)

        rrf_scores: dict[str, float] = {}
        chunk_data: dict[str, dict[str, Any]] = {}

        for rank, r in enumerate(bm25_results):
            cid = r["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (rrf_k + rank + 1)
            chunk_data[cid] = r

        for rank, r in enumerate(vector_results):
            cid = r["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (rrf_k + rank + 1)
            if cid not in chunk_data:
                chunk_data[cid] = r

        results: list[dict[str, Any]] = []
        for cid, score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]:
            data = chunk_data[cid]
            results.append({
                "chunk_id": cid,
                "rrf_score": score,
                "code_text": data.get("code_text", ""),
                "metadata": data.get("metadata", {}),
            })

        return results

    async def delete_by_source(self, source_config: str, source_version: str | None = None) -> int:
        before = len(self._chunks)
        self._chunks = [
            c for c in self._chunks
            if not (
                c.get("source_config") == source_config
                and (source_version is None or c.get("source_version") == source_version)
            )
        ]
        return before - len(self._chunks)

    async def health_check(self) -> bool:
        return True

    def _apply_filters(self, filters: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not filters:
            return list(self._chunks)
        return [
            c for c in self._chunks
            if all(c.get(k) == v for k, v in filters.items())
        ]


# ─── PgVectorStore (production, ADR-0015) ───────────────────────────────────


class PgVectorStore:
    """Postgres + pgvector реализация (production).

    Требует:
    - postgres с расширениями: pgvector, pg_trgm
    - таблица code_chunks (см. ADR-0020 схема БД)

    Подключение через DATABASE_URL env var или psycopg2.connect().
    """

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn or _get_dsn()
        self._conn: Any = None

    def _get_conn(self) -> Any:
        if self._conn is None:
            import psycopg2

            self._conn = psycopg2.connect(self._dsn)
            self._conn.autocommit = True
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        """Создать таблицу если не существует (ADR-0020)."""
        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS code_chunks (
                    id BIGSERIAL PRIMARY KEY,
                    chunk_id TEXT UNIQUE NOT NULL,
                    source_layer TEXT NOT NULL,
                    source_config TEXT,
                    source_version TEXT,
                    platform_version TEXT,
                    module_kind TEXT,
                    object_ref TEXT,
                    method_name TEXT,
                    is_export BOOLEAN DEFAULT FALSE,
                    is_function BOOLEAN DEFAULT TRUE,
                    parameters JSONB DEFAULT '[]',
                    code_text TEXT NOT NULL,
                    tsvector TSVECTOR,
                    embedding VECTOR(1024),
                    embeddings_model_version TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_tsvector ON code_chunks USING GIN (tsvector)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON code_chunks USING IVFFLAT (embedding vector_cosine_ops) WITH (lists = 100)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_layer ON code_chunks (source_layer, source_config, source_version)")

    async def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        conn = self._get_conn()
        with conn.cursor() as cur:
            for chunk in chunks:
                import json as _json

                emb = chunk.get("embedding")
                emb_str = f"[{','.join(str(x) for x in emb)}]" if emb else "NULL"

                cur.execute(
                    """INSERT INTO code_chunks
                       (chunk_id, source_layer, source_config, source_version,
                        platform_version, module_kind, object_ref, method_name,
                        is_export, is_function, parameters, code_text, tsvector,
                        embedding, embeddings_model_version)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                               to_tsvector('russian', %s), %s::vector, %s)
                       ON CONFLICT (chunk_id) DO UPDATE SET
                           code_text = EXCLUDED.code_text,
                           tsvector = EXCLUDED.tsvector,
                           embedding = EXCLUDED.embedding,
                           embeddings_model_version = EXCLUDED.embeddings_model_version
                    """,
                    (
                        chunk["chunk_id"],
                        chunk.get("source_layer", "config"),
                        chunk.get("source_config"),
                        chunk.get("source_version"),
                        chunk.get("platform_version"),
                        chunk.get("module_kind"),
                        chunk.get("object_ref"),
                        chunk.get("method_name"),
                        chunk.get("is_export", False),
                        chunk.get("is_function", True),
                        _json.dumps(chunk.get("parameters", [])),
                        chunk.get("code_text", ""),
                        chunk.get("code_text", ""),
                        emb_str if emb != "NULL" else None,
                        chunk.get("embeddings_model_version", ""),
                    ),
                )
        return len(chunks)

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        conn = self._get_conn()
        emb_str = f"[{','.join(str(x) for x in query_embedding)}]"

        where_clause = _build_where_clause(filters)
        query = f"""
            SELECT chunk_id, 1 - (embedding <=> %s::vector) AS score,
                   code_text, source_layer, source_config, source_version,
                   module_kind, object_ref, method_name, is_function, parameters
            FROM code_chunks
            WHERE embedding IS NOT NULL {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """

        with conn.cursor() as cur:
            cur.execute(query, (emb_str, emb_str, top_k))
            rows = cur.fetchall()

        return [_row_to_dict(r, cur.description) for r in rows]

    async def search_bm25(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        conn = self._get_conn()
        where_clause = _build_where_clause(filters)

        query_sql = f"""
            SELECT chunk_id, ts_rank(tsvector, plainto_tsquery('russian', %s)) AS score,
                   code_text, source_layer, source_config, source_version,
                   module_kind, object_ref, method_name, is_function, parameters
            FROM code_chunks
            WHERE tsvector @@ plainto_tsquery('russian', %s) {where_clause}
            ORDER BY score DESC
            LIMIT %s
        """

        with conn.cursor() as cur:
            cur.execute(query_sql, (query, query, top_k))
            rows = cur.fetchall()

        return [_row_to_dict(r, cur.description) for r in rows]

    async def search_hybrid(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        rrf_k: int = 60,
    ) -> list[dict[str, Any]]:
        bm25_results = await self.search_bm25(query, top_k=top_k * 2, filters=filters)
        vector_results = await self.search(query_embedding, top_k=top_k * 2, filters=filters)

        # RRF fusion
        rrf_scores: dict[str, float] = {}
        chunk_data: dict[str, dict[str, Any]] = {}

        for rank, r in enumerate(bm25_results):
            cid = r["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (rrf_k + rank + 1)
            chunk_data[cid] = r

        for rank, r in enumerate(vector_results):
            cid = r["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (rrf_k + rank + 1)
            if cid not in chunk_data:
                chunk_data[cid] = r

        results: list[dict[str, Any]] = []
        for cid, score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]:
            data = chunk_data[cid]
            results.append({
                "chunk_id": cid,
                "rrf_score": score,
                "code_text": data.get("code_text", ""),
                "metadata": {k: v for k, v in data.items() if k not in ("code_text", "score")},
            })

        return results

    async def delete_by_source(self, source_config: str, source_version: str | None = None) -> int:
        conn = self._get_conn()
        with conn.cursor() as cur:
            if source_version:
                cur.execute(
                    "DELETE FROM code_chunks WHERE source_config = %s AND source_version = %s",
                    (source_config, source_version),
                )
            else:
                cur.execute("DELETE FROM code_chunks WHERE source_config = %s", (source_config,))
            return int(cur.rowcount)

    async def health_check(self) -> bool:
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
        except Exception:
            return False


# ─── Factory ────────────────────────────────────────────────────────────────


def make_vector_store(backend: str | None = None) -> VectorStoreProtocol:
    """Создать VectorStore по env var или аргументу.

    Args:
        backend: 'pgvector' | 'memory'. Если None — из env VECTOR_STORE.

    Returns:
        VectorStoreProtocol реализация.
    """
    import os

    backend = backend or os.environ.get("VECTOR_STORE", "pgvector")

    if backend == "pgvector":
        return PgVectorStore()
    if backend == "memory":
        return InMemoryVectorStore()
    raise ValueError(f"Unknown vector store backend: {backend}")


# ─── Helpers ────────────────────────────────────────────────────────────────


def _get_dsn() -> str:
    import os

    return os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/onec_ai",
    )


def _build_where_clause(filters: dict[str, Any] | None) -> str:
    if not filters:
        return ""
    clauses: list[str] = []
    for k, v in filters.items():
        if v is not None:
            clauses.append(f" AND {k} = '{v}'")
    return "".join(clauses)


def _row_to_dict(row: tuple[Any, ...], description: Any) -> dict[str, Any]:
    cols = [desc[0] for desc in description]
    d = dict(zip(cols, row, strict=False))
    # Группируем metadata
    metadata_keys = {"source_layer", "source_config", "source_version",
                     "platform_version", "module_kind", "object_ref",
                     "method_name", "is_function", "parameters"}
    result = {
        "chunk_id": d.get("chunk_id"),
        "score": d.get("score"),
        "code_text": d.get("code_text", ""),
        "metadata": {k: v for k, v in d.items() if k in metadata_keys},
    }
    return result


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity между двумя векторами."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))
