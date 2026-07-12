# TESTING POLICY — 1C AI Assistant

> **Политика тестирования.** Обязательна для всех коммитов.
> Применяется ко всем пакетам в `packages/`.
> Последнее обновление: 2026-07-11

---

## 1. Принципы

### 1.1. Тесты — это часть кода, не отдельная активность

Любой новый код → тесты в том же коммите. Никаких «потом допишу тесты».

### 1.2. Контракты — тестируются обязательно

Если есть Pydantic-модель, Protocol, JSON Schema — есть тест на её инварианты:
- frozen (мутация невозможна)
- extra=forbid (лишние поля невозможны)
- round-trip (model_dump_json → model_validate_json = исходная модель)
- JSON Schema export работает

### 1.3. Роутеры — property-based

Все детерминированные роутеры (`route_after_validate`, `route_after_review`, `route_after_retry`) тестируются через `hypothesis` — генерируем случайные `TaskState` и проверяем инварианты.

### 1.4. MCP контракты — snapshot-тесты

Любой MCP tool определён в `contracts.py` → его `name`, `description`, `input_schema`, `output_model` замораживаются в snapshot. Любое изменение → `--snapshot-update` + code review.

### 1.5. Pipeline — golden тесты

5-10 эталонных задач с известным ожидаемым результатом. Запускаются на каждом PR. Если golden тест упал — либо регрессия, либо осознанное изменение (тогда обновляем golden).

---

## 2. Структура тестов

```
tests/
├── conftest.py                    ← общие fixtures
├── fixtures/                      ← тестовые данные (в репо)
│   ├── mini_config/               ← минимальная 1С конфигурация
│   │   ├── Configuration.xml
│   │   ├── Catalogs/Товары/Товары.xml
│   │   ├── Documents/Продажа/Продажа.xml
│   │   └── CommonModules/ОбщегоНазначения/ОбщегоНазначения.xml
│   ├── mini_config.zip            ← для теста config add
│   └── bsl_samples/               ← .bsl файлы для тестов парсера
│       ├── simple_module.bsl
│       ├── with_regions.bsl
│       └── with_methods.bsl
│
├── parsers/
│   ├── test_models.py             ← Pydantic модели
│   ├── test_xml_configuration.py
│   ├── test_xml_catalog.py
│   ├── test_xml_document.py
│   ├── test_xml_common_module.py
│   ├── test_bsl_module.py
│   ├── test_hbk_syntax_helper.py
│   └── test_indexers.py
│
├── data_layer/
│   ├── test_path_manager.py
│   ├── test_config_registry.py
│   └── test_freshness.py
│
├── mcp_servers/
│   ├── test_bsl_ls_contracts.py
│   ├── test_metadata_contracts.py
│   ├── test_codebase_contracts.py
│   ├── test_kb_contracts.py
│   ├── test_git_contracts.py
│   └── snapshots/                 ← snapshot файлы
│       └── test_mcp_contracts/
│
├── orchestrator/
│   ├── test_state.py              ← TaskState, Subtask, Iteration
│   ├── test_contracts.py          ← PlanResult, GatherResult, ...
│   ├── test_routers.py            ← property-based
│   ├── test_retry.py
│   ├── test_errors.py
│   ├── test_tool_groups.py        ← CI-проверки (no_orphan, no_unexpected_multi_role)
│   ├── test_tool_provider.py
│   ├── test_graph_compile.py
│   └── test_nodes/                ← по одному на узел
│       ├── test_plan.py
│       ├── test_gather.py
│       ├── test_code.py
│       ├── test_validate.py
│       ├── test_review.py
│       └── test_commit.py
│
├── agent/
│   ├── test_cli_config.py
│   ├── test_cli_generate.py
│   └── test_cli_mcp.py
│
├── integration/                   ← требуют внешних сервисов
│   ├── test_bsl_ls_http.py        ← требует 1c-ai-bsl-ls контейнер
│   ├── test_persistence.py        ← требует postgres
│   └── test_pipeline_e2e.py       ← требует всё
│
└── golden/                        ← эталонные задачи
    ├── test_golden_simple_function.py
    ├── test_golden_posting_handler.py
    └── golden_data/               ← входы и ожидаемые выходы
```

---

## 3. pytest markers

Определены в `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "smoke: critical path tests (run with: pytest -m smoke)",
    "snapshot: MCP contract snapshot tests",
    "golden: end-to-end pipeline tests",
    "benchmark: performance benchmarks (not run by default)",
    "integration: requires external services (containers)",
    "property: hypothesis-based property tests",
]
```

### Когда использовать какой marker

| Marker | Что тестирует | Когда запускать |
|---|---|---|
| `smoke` | Критические пути (CLI работает, модели создаются) | Каждый коммит, каждый PR |
| `snapshot` | Контракты MCP tools | Каждый PR, обновляется через `--snapshot-update` |
| `golden` | End-to-end pipeline на эталонных задачах | Каждый PR (медленно, но важно) |
| `benchmark` | Производительность | По желанию, не в CI по умолчанию |
| `integration` | Требует контейнеров | Только в `integration.yml` workflow |
| `property` | Property-based через hypothesis | Каждый PR (медленно) |

### CI запуск

```bash
# Быстро (на каждый push) — ~30 секунд
pytest tests/ -m "smoke" -x

# Стандартно (на каждый PR) — ~5 минут
pytest tests/ -m "smoke or snapshot or property" -x

# Полностью (перед релизом) — ~20 минут
pytest tests/ --cov=packages --cov-fail-under=80

# Integration (отдельно, в integration.yml)
pytest tests/integration/ -m integration
```

---

## 4. Coverage

### 4.1. Цели

| Пакет | Цель | Комментарий |
|---|---|---|
| `parsers/models/` | 100% | Простые модели, легко достичь |
| `parsers/xml/` | 90% | Парсеры, edge cases важны |
| `parsers/bsl/` | 85% | Regex fallback сложнее тестировать |
| `data_layer/` | 95% | Критическая инфраструктура |
| `mcp_servers/` | 85% | Много интеграций |
| `orchestrator/` | 80% | LLM-узлы сложно тестировать без mock |
| `agent/` | 75% | CLI, много click runner |
| **Итого** | **≥80%** | В `pyproject.toml`: `fail_under = 80` |

### 4.2. Что НЕ нужно покрывать

- `__init__.py` (только re-export)
- `if TYPE_CHECKING:` блоки
- `raise NotImplementedError`
- Debug-only код (`if __name__ == "__main__":`)

Эти исключения — в `pyproject.toml` `[tool.coverage.report] exclude_lines`.

### 4.3. Coverage report

```bash
pytest tests/ --cov=packages --cov-report=term-missing --cov-report=html
# htmlcov/index.html — детальный отчёт
```

---

## 5. Test fixtures

### 5.1. `conftest.py` — общие fixtures

```python
# tests/conftest.py
import pytest
from pathlib import Path
from data_layer import PathManager, ConfigRegistry


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_paths(tmp_path: Path) -> PathManager:
    """PathManager с временными директориями."""
    env = tmp_path / "paths.env"
    env.write_text(f"""
DATA_DIR={tmp_path}/data
DERIVED_DIR={tmp_path}/derived
RUNTIME_DIR={tmp_path}/runtime
KNOWLEDGE_BASE_DIR={tmp_path}/kb
VENDOR_DIR={tmp_path}/vendor
""")
    return PathManager(env_path=env)


@pytest.fixture
def mini_config_zip() -> Path:
    """ZIP с минимальной 1С конфигурацией."""
    return FIXTURES_DIR / "mini_config.zip"


@pytest.fixture
def mini_config_dir() -> Path:
    """Распакованная мини-конфигурация."""
    return FIXTURES_DIR / "mini_config"


@pytest.fixture
def empty_registry(tmp_paths: PathManager) -> ConfigRegistry:
    """Пустой ConfigRegistry во временной директории."""
    return ConfigRegistry(tmp_paths.config_registry_path())
```

### 5.2. `mini_config/` — синтетическая 1С конфигурация

Минимальная конфигурация для тестов парсеров и индексеров:

```
mini_config/
├── Configuration.xml          ← 1 catalog + 1 document + 1 common module
├── Catalogs/
│   └── Товары/
│       └── Товары.xml         ← 3 атрибута (Наименование, Артикул, Цена)
├── Documents/
│   └── Продажа/
│       └── Продажа.xml        ← 2 атрибута (Контрагент, Сумма) + 1 register record
└── CommonModules/
    └── ОбщегоНазначения/
        └── ОбщегоНазначения.xml  ← server=true, global=false
```

**Требования к mini_config:**
- Все XML валидны по схемам 1С
- Имена на русском (для теста кодировки)
- Достаточно мал для быстрого теста (<10 КБ всего)
- Достаточно полон для покрытия всех парсеров

### 5.3. `bsl_samples/` — .bsl файлы

```
bsl_samples/
├── simple_module.bsl          ← 1 процедура, 1 функция
├── with_regions.bsl           ← с #Область ... #КонецОбласти
├── with_methods.bsl           ← 5+ методов, разные сигнатуры
├── with_async.bsl             ← Асинх Функция (для теста is_async)
├── with_antipatterns.bsl      ← query-in-loop, try-catch-silent
└── well_formed.bsl            ← эталон по стандартам 1С
```

---

## 6. Mocking strategy

### 6.1. Что мокаем

| Что | Как | Почему |
|---|---|---|
| LLM-вызовы | `unittest.mock.AsyncMock` с предзаписанным response | Тесты не должны тратить токены |
| MCP-серверы (in tests of orchestrator) | Mock `ToolProvider` | Orchestrator не должен зависеть от MCP runtime |
| Postgres | `pytest-postgresql` или testcontainers | Не зависит от локального postgres |
| BSL LS HTTP | `httpx.MockTransport` | Не требует запущенного контейнера |
| Git operations | tmp_path + `git init` | Реальный git, но в изоляции |
| Время | `freezegun.freeze_time` | Для теста freshness_check |

### 6.2. Что НЕ мокаем

- Pydantic модели — тестируем как есть
- PathManager — тестируем с tmp_path
- Роутеры — чистые функции, нечего мокать
- YAML загрузку KB — тестируем с реальными YAML файлами из `knowledge-base/`

### 6.3. Пример mock LLM

```python
# tests/orchestrator/test_nodes/test_code.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from orchestrator.nodes.code import code_node
from orchestrator.state import TaskState, Subtask, FSMState
from parsers.models import ObjectRef


@pytest.fixture
def mock_llm():
    """Mock LLM с предзаписанным structured output."""
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=llm)
    llm.ainvoke = AsyncMock(return_value=MagicMock(
        code="Процедура Тест() КонецПроцедуры",
        explanation="Test function",
        patterns_applied=[],
        antipatterns_avoided=[],
    ))
    return llm


@pytest.mark.asyncio
async def test_code_node_generates_code(mock_llm):
    state = TaskState(
        task_id="t1",
        description="Test task",
        config_name="mini",
        config_version="1.0",
        platform_version="8.3.20",
        fsm_state=FSMState.CODING,
        subtasks=[Subtask(
            id="st1",
            name="Test",
            target_module=ObjectRef.from_string("CommonModule.Тест"),
            description="Generate test function",
            acceptance_criteria=["Function exists"],
        )],
        current_subtask_idx=0,
    )

    result = await code_node(state, llm=mock_llm)
    assert "code" in result
    assert "Процедура" in result["iterations"][-1].code
```

---

## 7. Property-based тесты (hypothesis)

### 7.1. Где использовать

- Pydantic модели (round-trip, frozen, extra=forbid)
- Роутеры (для любого валидного state возвращают Literal из набора)
- PathManager (для любого валидного env — пути строятся корректно)
- ConfigRegistry (add/remove/idempotent)

### 7.2. Пример

```python
# tests/parsers/test_models.py
from hypothesis import given, strategies as st
from parsers.models import ObjectRef, BslModule


class TestObjectRefProperty:
    @given(
        ref_type=st.text(min_size=1, max_size=20, alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Lt"),  # буквы
            whitelist_characters="0123456789",
        )),
        name=st.text(min_size=1, max_size=20),
    )
    def test_round_trip(self, ref_type, name):
        """ObjectRef.from_string(str(ObjectRef(type, name))) == ObjectRef(type, name)."""
        ref = ObjectRef(type=ref_type, name=name)
        restored = ObjectRef.from_string(str(ref))
        assert restored == ref

    @given(
        # Любой ObjectRef должен быть frozen
        ref_type=st.text(min_size=1, max_size=20),
        name=st.text(min_size=1, max_size=20),
    )
    def test_frozen(self, ref_type, name):
        from pydantic import ValidationError
        ref = ObjectRef(type=ref_type, name=name)
        with pytest.raises(ValidationError):
            ref.name = "other"  # type: ignore


# tests/orchestrator/test_routers.py
from hypothesis import given, strategies as st
from orchestrator.routers import route_after_validate


class TestRouteAfterValidate:
    @given(passed=st.booleans())
    def test_returns_valid_literal(self, passed):
        """route_after_validate всегда возвращает 'review' или 'retry'."""
        state = _make_state(validation_passed=passed)
        result = route_after_validate(state)
        assert result in ("review", "retry")
        assert result == ("review" if passed else "retry")
```

---

## 8. Snapshot тесты

### 8.1. Что замораживаем

- Состав MCP tools (имена, описания, input_schema)
- JSON Schemas моделей (для отслеживания breaking changes)
- Контракты Facade lifecycle tools

### 8.2. Пример

```python
# tests/mcp_servers/test_bsl_ls_contracts.py
import pytest
from mcp_servers.bsl_ls.contracts import BSL_LS_TOOLS


def test_snapshot_tool_names(snapshot):
    """Freeze состава tools — любое изменение требует --snapshot-update."""
    names = sorted(t.name for t in BSL_LS_TOOLS)
    snapshot.assert_match("\n".join(names), "bsl_ls_tool_names.txt")


def test_snapshot_tool_descriptions(snapshot):
    """Freeze описаний — LLM-facing тексты нельзя менять без review."""
    for tool in BSL_LS_TOOLS:
        snapshot.assert_match(tool.description, f"{tool.name}.description.txt")


def test_snapshot_input_schemas(snapshot):
    """Freeze JSON Schemas — breaking changes в input."""
    for tool in BSL_LS_TOOLS:
        import json
        schema_str = json.dumps(tool.input_schema, indent=2, sort_keys=True, ensure_ascii=False)
        snapshot.assert_match(schema_str, f"{tool.name}.input_schema.json")
```

### 8.3. Обновление

```bash
pytest tests/mcp_servers/test_bsl_ls_contracts.py --snapshot-update
# → проверить git diff
# → commit если изменения осознанные
```

---

## 9. Golden тесты

### 9.1. Структура

```
tests/golden/
├── test_golden_simple_function.py
├── test_golden_posting_handler.py
├── test_golden_query_optimization.py
└── golden_data/
    ├── simple_function/
    │   ├── task.txt              ← вход: описание задачи
    │   ├── config/               ← вход: мини-конфиг
    │   ├── expected_code.bsl     ← ожидаемый код (или его часть)
    │   └── expected_subtasks.json ← ожидаемая декомпозиция
    └── ...
```

### 9.2. Пример

```python
# tests/golden/test_golden_simple_function.py
import pytest
from pathlib import Path
from orchestrator.graph import build_graph

GOLDEN_DIR = Path(__file__).parent / "golden_data" / "simple_function"


@pytest.mark.golden
@pytest.mark.asyncio
async def test_simple_function_generation(mock_llm_for_golden):
    """Эталон: генерация простой функции Сложить(a, b)."""
    task = (GOLDEN_DIR / "task.txt").read_text(encoding="utf-8")
    expected_code = (GOLDEN_DIR / "expected_code.bsl").read_text(encoding="utf-8")

    state = _make_initial_state(task=task, config="mini", version="1.0")
    graph = build_graph(checkpointer=MemorySaver())

    result = await graph.ainvoke(state)

    # Проверяем, что код сгенерирован
    assert result["fsm_state"] == "done"
    final_code = result["iterations"][-1].code
    # Проверяем ключевые элементы (не точное совпадение — LLM вариативна)
    assert "Функция Сложить" in final_code
    assert "Возврат" in final_code
    # BSL LS должен пройти без critical
    assert result["validation_passed"] is True
```

### 9.3. Когда обновлять golden

- Если изменился промпт → пересмотреть golden
- Если изменился контракт → пересмотреть golden
- Если LLM стала лучше → можно ужесточить golden (больше проверок)

---

## 10. CI интеграция

### 10.1. `ci.yml` — на каждый PR/push

```yaml
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --all-extras
      - run: uv run ruff check packages/
      - run: uv run ruff format --check packages/
      - run: uv run mypy packages/

  test-smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --all-extras
      - run: uv run pytest tests/ -m "smoke" -x --tb=short

  test-full:
    runs-on: ubuntu-latest
    needs: [lint, test-smoke]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --all-extras
      - run: uv run pytest tests/ -m "smoke or snapshot or property" --cov=packages --cov-fail-under=80

  boundary-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python scripts/check_package_boundaries.py
```

### 10.2. `integration.yml` — вручную или nightly

```yaml
jobs:
  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --all-extras
      - run: docker compose up -d
      - run: sleep 30  # ждать healthchecks
      - run: uv run pytest tests/integration/ -m integration
      - if: always()
        run: docker compose down
```

---

## 11. Чек-лист перед коммитом

- [ ] `uv run ruff check packages/` — без ошибок
- [ ] `uv run ruff format --check packages/` — отформатировано
- [ ] `uv run mypy packages/` — без ошибок
- [ ] `uv run pytest tests/ -m "smoke" -x` — зелёные
- [ ] Если добавлен новый код — есть тесты
- [ ] Если изменён контракт — snapshot обновлён (если нужно)
- [ ] `python scripts/check_package_boundaries.py` — OK
- [ ] Coverage не упал (для PR — проверить `--cov-report=term-missing`)

## 12. Чек-лист перед релизом

- [ ] Все из чек-листа коммита
- [ ] `uv run pytest tests/ --cov=packages --cov-fail-under=80` — зелёные
- [ ] `uv run pytest tests/ -m golden` — golden тесты зелёные
- [ ] `uv run pytest tests/integration/ -m integration` — integration зелёные (если есть контейнеры)
- [ ] Нет `# TODO` без issue-ссылки в критичных модулях
- [ ] CHANGELOG обновлён

---

## 13. Антипаттерны тестирования (НЕ делать)

- ❌ Тесты, которые зависят от порядка выполнения
- ❌ Тесты, которые мутируют глобальное состояние
- ❌ Тесты без assertions (просто "не упало")
- ❌ Тесты с hardcoded путями (используй `tmp_path`)
- ❌ Тесты, которые делают реальные LLM-вызовы (используй mock)
- ❌ Тесты, которые требуют интернет (кроме integration)
- ❌ Snapshot-файлы, изменяемые без code review
- ❌ Golden тесты с точным совпадением кода (LLM вариативна — проверяй ключевые элементы)
- ❌ Coverage ради coverage (90% с плохими тестами хуже 80% с хорошими)

---

## 14. Инструменты

| Инструмент | Где | Зачем |
|---|---|---|
| `pytest` | основной runner | Все тесты |
| `pytest-asyncio` | async тесты | MCP, orchestrator |
| `pytest-cov` | coverage | Отчёты, fail_under |
| `pytest-snapshot` | snapshot тесты | Контракты MCP |
| `hypothesis` | property-based | Модели, роутеры |
| `pytest-benchmark` | benchmarks | Производительность |
| `freezegun` | время | freshness_check |
| `pytest-postgresql` | postgres | Integration тесты |
| `httpx.MockTransport` | HTTP mock | BSL LS client |
| `unittest.mock` | general mock | LLM, MCP |

---

*Этот документ — обязательный для всех коммитов. Обновляется при добавлении новых стратегий тестирования.*
