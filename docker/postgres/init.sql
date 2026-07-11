-- docker/postgres/init.sql
-- Инициализация PostgreSQL для 1C AI Assistant.
-- Запускается автоматически при первом старте контейнера.

-- ─── Extensions ────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS pgvector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── BSL modules (для codebase-server hybrid search) ──────────────────────
CREATE TABLE IF NOT EXISTS bsl_modules (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    config_name     TEXT NOT NULL,
    config_version  TEXT NOT NULL,
    object_ref      TEXT NOT NULL,
    module_kind     TEXT NOT NULL,
    source          TEXT NOT NULL,
    source_hash     TEXT NOT NULL,
    tsv             TSVECTOR,
    embedding       VECTOR(384),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(config_name, config_version, object_ref, module_kind)
);

CREATE INDEX IF NOT EXISTS bsl_modules_tsv_idx
    ON bsl_modules USING GIN(tsv);
CREATE INDEX IF NOT EXISTS bsl_modules_embedding_idx
    ON bsl_modules USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
CREATE INDEX IF NOT EXISTS bsl_modules_trgm_idx
    ON bsl_modules USING GIN (source gin_trgm_ops);
CREATE INDEX IF NOT EXISTS bsl_modules_config_idx
    ON bsl_modules (config_name, config_version);

-- ─── Config registry (опционально — дублирует runtime/config-registry.json) ──
-- Используется только если решим хранить registry в postgres.
-- Пока оставлено как комментарий, используется JSON-файл.

-- ─── LangGraph checkpoints ────────────────────────────────────────────────
-- Таблицы checkpoints, writes, migration_blobs создаются
-- AsyncPostgresSaver.setup() автоматически при первом запуске orchestrator.

-- ─── Health check ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS health_check (
    id SERIAL PRIMARY KEY,
    checked_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT NOT NULL
);
INSERT INTO health_check (status) VALUES ('initialized');
