"""tests/integration/ — integration tests with real containers (TD-S6-04).

Запускаются только если доступны контейнеры (env vars):
- ``TEST_POSTGRES_DSN`` — реальный Postgres для persistence test.
- ``BSL_LS_HTTP_URL`` — BSL LS HTTP server для lint tests.
- ``TEST_GIT_REPO`` — путь к git-репозиторию для git roundtrip tests.

CI: ``.github/workflows/integration.yml`` поднимает контейнеры через docker compose
и запускает ``pytest tests/integration/ -m integration``.

Локально:
    TEST_POSTGRES_DSN=postgresql://agent:agent@localhost:5432/agent \\
    BSL_LS_HTTP_URL=http://localhost:8080 \\
    TEST_GIT_REPO=/tmp/test-repo \\
    uv run pytest tests/integration/ -m integration -v

См. TESTING_POLICY.md раздел 10.2, D-2026-07-13-13.
"""
