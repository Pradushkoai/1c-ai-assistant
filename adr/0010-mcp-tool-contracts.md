# ADR-0010: MCP tool contracts — двойной контракт

**Статус:** Accepted
**Дата:** 2026-07-11

## Контекст

5 MCP-серверов экспонируют 19 tools. Orchestrator (через Gather/Validate subgraph'ы) вызывает их параллельно. Без явных контрактов:
- orchestrator не знает, что возвращает tool (dict[str, Any] everywhere)
- нельзя сгенерировать snapshot-тесты
- нельзя валидировать input на стороне MCP-сервера
- error handling размазан

## Решение

**Двойной контракт для каждого tool:**

1. **MCP-сторона** (`ToolContract` Protocol): `name`, `description`, `input_schema` (JSON Schema), `output_model` (Pydantic v2), `error_contract` (exception / error_dict / empty_result), `timeout`, `idempotent`, `required_role`
2. **Orchestrator-сторона**: вызывает tool, результат валидируется через `output_model.model_validate()`

19 tools в 5 серверах:
- `metadata` (4): get_metadata, get_form_structure, get_api_reference, get_dependency_graph
- `codebase` (4): semantic_search, get_module, get_similar, call_graph
- `kb` (5): get_pattern, get_antipattern, search_kb, check_method_availability, check_antipatterns
- `bsl_ls` (2): lint, format
- `git` (4): create_branch, commit, open_pr, diff

## Snapshot-тесты

```python
def test_snapshot_tool_names(snapshot):
    all_names = sorted(t.name for t in ALL_TOOLS)
    snapshot.assert_match("\n".join(all_names), "tool_names.txt")

def test_input_schema_is_valid_json_schema():
    for tool in ALL_TOOLS:
        Draft7Validator.check_schema(tool.input_schema)
```

Любое изменение в составе tools или их схемах → `--snapshot-update` + code review.

## Последствия

### Положительные
- End-to-end типизация: MCP-клиент → JSON Schema → Pydantic → orchestrator
- Snapshot-тесты ловят незапланированные изменения контрактов
- `required_role` синхронизирован с `TOOL_GROUPS` (Шаг 6)

### Отрицательные
- 19 классов с метаданными — boilerplate
- `error_contract` — 3 варианта, нужно помнить какой когда (митигация: документация в каждом contracts.py)

## Связанные документы
- 05-mcp-tool-contracts.md (все 19 контрактов)
- ADR-0005 (TOOL_GROUPS, использует `required_role`)
- ADR-0007 (Pydantic v2 для `output_model`)
