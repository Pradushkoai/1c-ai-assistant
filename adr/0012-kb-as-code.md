# ADR-0012: KB-as-code — YAML + Markdown

**Статус:** Accepted
**Дата:** 2026-07-11
**Supersedes**: Markdown-only KB из `1c-ai-dev-env`

## Контекст

`1c-ai-dev-env` хранил KB как Markdown (`knowledge_base/antipatterns/common_antipatterns.md`). Это работало для человека, но не для машины:
- нельзя автоматически детектить антипаттерн в коде (нет `detect:` блока)
- нельзя валидировать структуру (JSON Schema не к Markdown)
- нельзя сгенерировать system prompt для Coder'а (`recommendation_for_llm` поле)
- нельзя версионировать отдельные правила

## Решение

**YAML — для машины, Markdown — для человека. Комплиментарно, не взаимоисключающе.**

Структура `knowledge-base/`:
- `schemas/` — JSON Schemas (валидация)
- `patterns/*.yaml` — эталоны с `code_template` и `variables`
- `antipatterns/*.yaml` — с `detect:` блоком (regex / AST / bsl_ls_rule)
- `prompts/*.j2` — Jinja2 системные промпты
- `examples/` — .bsl файлы good/bad
- `standards/` — СТО 1С, БСП (Markdown, для справки)

**JSON Schema валидация при загрузке** — `KBCollection._load_all()` использует `jsonschema.validate`.

**CI-тесты:**
- `test_all_patterns_valid` — все YAML валидны по schema
- `test_no_duplicate_ids` — нет дублей id
- `test_detect_works` — хотя бы один антипаттерн детектится в примере bad
- `test_recommendation_for_llm_present` — каждый антипаттерн имеет текст для retry-промпта

## Структура антипаттерна (кратко)

```yaml
id: query-in-loop
title: "Запрос в цикле"
severity: critical
detect:
  regex:
    pattern: "Для\\s+Каждого.*?Запрос\\s*=\\s*Новый\\s+Запрос"
example_bad: |
  ...
example_good: |
  ...
recommendation_for_llm: |
  Замените на batch-запрос с `ГДЕ Поле В (&Массив)`...
recommendation_for_reviewer: |
  Проверьте, что для каждой циклической конструкции с запросом есть обоснование...
```

## Последствия

### Положительные
- `kb.check_antipatterns` автоматически детектит в коде
- `kb.get_pattern` отдаёт Coder'у эталон с `code_template`
- Ревью через PR — каждое правило отдельно
- JSON Schema ловит опечатки в полях

### Отрицательные
- 2 формата вместо 1 (но каждый для своей цели)
- YAML-схема — дополнительная валидация (но один раз настроенная, работает бесплатно)

## Связанные документы
- 07-kb-as-code.md (полные схемы и примеры)
- ADR-0010 (`kb.*` tool contracts используют эти YAML)
