# docker/Dockerfile.app
# 1C AI Assistant — основной Python-контейнер.
# Содержит: orchestrator + 4 MCP in-process + Facade.
# Не содержит Java (BSL LS в отдельном контейнере).

FROM python:3.12-slim AS base

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Установка uv для dependency management
RUN pip install --no-cache-dir uv

WORKDIR /app

# Копируем workspace
COPY pyproject.toml uv.lock* ./
COPY packages/ ./packages/
COPY paths.env ./

# Синхронизация зависимостей
RUN uv sync --all-extras

# Копируем остальное
COPY knowledge-base/ ./knowledge-base/
COPY adr/ ./adr/
COPY docs/ ./docs/

# Volume для данных
VOLUME ["/app/data", "/app/derived", "/app/runtime"]

# Переменные окружения
ENV PYTHONUNBUFFERED=1 \
    LOG_FORMAT=json \
    VECTOR_STORE=pgvector

# Точка входа — CLI
ENTRYPOINT ["uv", "run", "1c-ai"]
CMD ["--help"]
