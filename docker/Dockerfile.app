# docker/Dockerfile.app
# 1C AI Assistant — основной Python-контейнер (multi-stage, TD-S5-04).
# Содержит: orchestrator + 4 MCP in-process + Facade.
# Не содержит Java (BSL LS в отдельном контейнере).
#
# Multi-stage: builder (с build deps) + runtime (только runtime deps).
# См. ADR-0015 (3-container deployment), D-2026-07-13-09.

# ─── Stage 1: builder ───────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Build deps для C-extensions (psycopg, fastembed, tree-sitter).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Копируем только dependency-файлы (better layer caching).
COPY pyproject.toml uv.lock* ./
COPY packages/ ./packages/
COPY paths.env ./

# Синхронизация всех extras (postgres, langsmith, qdrant, api) в /app/.venv.
RUN uv sync --all-extras

# ─── Stage 2: runtime ───────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Runtime deps: git (для git MCP), curl (для healthcheck), ca-certificates.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user для security.
RUN groupadd -r app && useradd -r -g app -d /app -s /bin/bash app

WORKDIR /app

# Копируем .venv из builder.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/pyproject.toml /app/uv.lock* /app/
COPY --from=builder /app/paths.env /app/

# Копируем исходники пакетов (для editable install).
COPY packages/ /app/packages/

# Копируем knowledge-base, adr, docs (read-only ресурсы).
COPY knowledge-base/ /app/knowledge-base/
COPY adr/ /app/adr/
COPY docs/ /app/docs/

# Volume для данных (gitignored в репо, монтируется из host).
VOLUME ["/app/data", "/app/derived", "/app/runtime"]

# Переменные окружения (defaults; переопределяются в docker-compose / .env).
ENV PYTHONUNBUFFERED=1 \
    LOG_FORMAT=json \
    VECTOR_STORE=pgvector \
    PATH="/app/.venv/bin:${PATH}"

# OCI labels (org.opencontainers.image.*).
LABEL org.opencontainers.image.title="1c-ai-app" \
      org.opencontainers.image.description="1C AI Assistant — orchestrator + MCP servers + Facade" \
      org.opencontainers.image.source="https://github.com/Pradushkoai/1c-ai-assistant" \
      org.opencontainers.image.licenses="MIT"

# Переключаемся на non-root user.
USER app

# Healthcheck: HTTP /health endpoint (Stage 5 TD-S7-02). Fallback: 1c-ai health CLI.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || 1c-ai health || exit 1

# Точка входа — CLI. Для production: docker run ... 1c-ai serve (HTTP server).
ENTRYPOINT ["1c-ai"]
CMD ["--help"]
