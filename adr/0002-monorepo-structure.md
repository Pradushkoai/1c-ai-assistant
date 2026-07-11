# ADR-0002: Монорепа с uv workspace, 5 пакетов

**Статус:** Accepted
**Дата:** 2026-07-11

## Контекст

Проект состоит из нескольких логически независимых частей: парсеры (lib), data layer (FS), MCP-серверы (5 штук), orchestrator (LangGraph), agent (CLI/entry points). Нужно решить: один пакет, multirepo, или монорепа с workspace.

## Рассмотренные варианты

1. **Multirepo** — pros: независимое версионирование; cons: solo-dev не потянет синхронизацию 7+ репозиториев
2. **Один большой пакет** — pros: просто; cons: смешивает ответственности, любой change прогоняет все тесты
3. **Монорепа с uv workspace** — pros: единый git history, независимое версионирование пакетов, atomic commits

## Решение

**Монорепа с uv workspace, 5 пакетов:**
- `parsers` — чистая lib (от неё зависят все)
- `data_layer` — PathManager + ConfigRegistry
- `mcp_servers` — 5 доменных серверов + Facade
- `orchestrator` — LangGraph pipeline
- `agent` — CLI + entry points

Зависимости идут только вниз: `agent → orchestrator → mcp_servers → data_layer → parsers`.

## Последствия

### Положительные
- atomic commits, затрагивающие несколько пакетов
- `uv.lock` фиксирует целостный граф зависимостей
- общие dev-зависимости в корне (без дублирования)
- bisect работоспособен через границы пакетов

### Отрицательные
- один `uv.lock` на всех — bump зависимости в одном пакете влияет на всех
- CI прогоняет все тесты на каждое изменение (митигация: `pytest -m smoke` для быстрых)

## Связанные документы
- 01-monorepo-structure.md
- scripts/check_package_boundaries.py (CI-проверка границ)
