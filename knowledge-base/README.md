# Knowledge Base

KB-as-code — паттерны, антипаттерны, промпты. В git, ревью через PR.

См. [docs/architecture/07-kb-as-code.md](../docs/architecture/07-kb-as-code.md) для формата.

## Структура

- `schemas/` — JSON Schemas (валидация YAML + structured outputs)
- `patterns/` — YAML-эталоны (`posting-handler.yaml`, `transaction-wrapper.yaml`, ...)
- `antipatterns/` — YAML с `detect:` блоком (`query-in-loop.yaml`, ...)
- `prompts/` — Jinja2 системные промпты (`planner.system.j2`, `coder.system.j2`, ...)
- `standards/` — СТО 1С, БСП (Markdown)
- `examples/` — .bsl файлы good/bad

## Заполнение

KB заполняется в Спринте 3. Сейчас — пустые директории.
