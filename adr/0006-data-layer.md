# ADR-0006: Data Layer — 4 слоя + PathManager

**Статус:** Accepted
**Дата:** 2026-07-11

## Контекст

Проект работает с большим объёмом данных 1С:
- XML-выгрузки конфигураций (10-100 МБ на конфиг)
- BSL-модули (10k+ файлов в типовой УТ 11)
- .hbk файлы синтакс-помощника (8141 методов платформы)
- Сгенерированные индексы (BM25, embeddings, SQLite)
- Состояние сессий и checkpoint'ы

Без чёткой структуры — расхождения между CLI и MCP, гонки freshness check, тесты создают временные директории хаотично.

## Решение

**4 слоя файловой системы:**
1. `data/` (gitignored) — пользовательский ввод: configs/, archives/, hbk/
2. `derived/` (gitignored) — сгенерированные индексы: configs/{name}/{version}/*.json, platform/{version}/platform-methods.db
3. `runtime/` (gitignored) — состояние сессий: config-registry.json, session-state.json
4. `knowledge-base/` (в git) — KB-as-code, ревью через PR

**PathManager** — единый источник правды для всех путей:
- `data_config_dir(name, version) -> Path`
- `unified_metadata_index(name, version) -> Path`
- `validate() -> {path: exists_bool}` — preflight check
- `freshness_check(name, version) -> {index: is_fresh_bool}`

**Конфигурация через `paths.env`** с возможностью переопределения через OS env vars (для CI/Docker).

## Последствия

### Положительные
- Единый контракт для 5 MCP-серверов и orchestrator'а
- Тестируемость: `tmp_paths` fixture подменяет `paths.env` на `tmp_path`
- Freshness check — основа для `1c-ai config build --check-freshness`
- KB в git — ревью через PR, версионирование правил

### Отрицательные
- PathManager — ещё один класс (но тонкий, без бизнес-логики)
- `paths.env` — дополнительный конфигурационный файл (но простой, 5 переменных)

## Связанные документы
- 03-paths-protocol.md
- ADR-0008 (PathManager подробно)
