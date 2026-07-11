# ADR-0008: PathManager — единый источник правды для путей

**Статус:** Accepted
**Дата:** 2026-07-11

## Контекст

5 MCP-серверов и orchestrator формируют пути к `data/`, `derived/`, `runtime/`, `knowledge-base/`. Без единого контракта — расхождения (`configs/ut11/4.5.3/` vs `configs/ut11-4.5.3/`), гонки freshness check, сложные тесты.

## Решение

**PathManager — Protocol + реализация с `${VAR}` подстановкой из `paths.env`.**

Контракт:
- `data_config_dir(name, version) -> Path`
- `derived_config_dir(name, version) -> Path`
- `unified_metadata_index(name, version) -> Path`
- `runtime_dir() -> Path`
- `knowledge_base_dir() -> Path`
- `validate() -> {path: exists_bool}` — preflight
- `freshness_check(name, version) -> {index: is_fresh}` — mtime source vs index
- `ensure_dirs() -> None` — создать базовые директории

`paths.env`:
```
DATA_DIR=./data
DERIVED_DIR=./derived
RUNTIME_DIR=./runtime
KNOWLEDGE_BASE_DIR=./knowledge-base
VENDOR_DIR=./vendor
```

OS env vars переопределяют `paths.env` (для CI: `DATA_DIR=${{ runner.temp }}/1c-ai-data`).

## Последствия

### Положительные
- Все пути строятся по шаблону — нет расхождений
- `freshness_check` — основа для `1c-ai config build --check-freshness`
- Тесты: `tmp_paths` fixture подменяет `paths.env` на `tmp_path`
- CI может изолировать через env vars

### Отрицательные
- PathManager — обязательная зависимость для всех MCP-серверов (но через Protocol, можно mock)
- `paths.env` — дополнительный файл (но простой, 5 переменных)

## Связанные документы
- 03-paths-protocol.md
- ADR-0006 (Data Layer)
