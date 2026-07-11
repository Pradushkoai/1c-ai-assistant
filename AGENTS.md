# AGENTS.md — Правила для AI-агентов в репозитории 1c-ai-assistant

> **Этот файл — журнал правил для AI-агентов (Cursor, Claude, Codex).**
> Прочитай перед каждой рабочей сессией.

---

## Текущий статус

**Sprint 1 завершён.** `1c-ai config build` работает end-to-end.
344 теста проходят. CI зелёная (после фикса mypy).

**Что готово:**
- `parsers/models/` — 22 Pydantic v2 модели
- `parsers/xml/` — 4 парсера + универсальный парсер
- `parsers/indexers/` — metadata_indexer
- `data_layer/` — PathManager, ConfigRegistry, freshness
- `agent/` — CLI `1c-ai` (init, config add/build/list/remove, validate, hbk load)
- `tests/` — 344 теста (smoke, property-based, persistence, end-to-end)
- CI/CD — `.github/workflows/ci.yml` + `integration.yml`

**Что не готово (Sprint 2+):**
- `parsers/bsl/` — парсер .bsl файлов (Sprint 2)
- `mcp_servers/` — все 5 MCP серверов (Sprint 2-4)
- `orchestrator/` — LangGraph pipeline (Sprint 2)
- `knowledge-base/` — KB-as-code (Sprint 3)
- Docker — 3 контейнера (Sprint 4)

---

## Перед началом работы

1. **Прочитай AGENTS.md** (этот файл)
2. **Прочитай [docs/architecture/CONCEPTUAL.md](docs/architecture/CONCEPTUAL.md)** — концептуальная архитектура
3. **Прочитай [adr/](adr/)** — 17 ADR с обоснованием решений
4. **Прочитай [CHANGELOG.md](CHANGELOG.md)** — история изменений
5. **Пойми контекст задачи** — какой спринт, какой компонент

## Архитектурные правила (НЕ нарушать)

### 1. 6 слоёв, зависимости только вниз

```
Entry Points → Orchestrator → MCP → Parsers → Data → KB
```

**Запрещено:**
- `parsers/` не может импортировать из `orchestrator/`, `mcp_servers/`, `data_layer/`
- `data_layer/` не может импортировать из `orchestrator/`, `mcp_servers/`
- `mcp_servers/` не может импортировать из `orchestrator/`, `agent/`
- `orchestrator/` импортирует из `mcp_servers.shared.protocol`, но НЕ из `mcp_servers.{metadata,codebase,...}` напрямую

### 2. Coder без инструментов (ADR-0005, ADR-0011)

`TOOL_GROUPS[CODER] = {}` — строго. Coder не имеет MCP-инструментов. Это **главный принцип фокус-контроля**.

Если появляется искушение дать Coder'у tool — это сигнал, что Gatherer плохо собирает контекст. Улучшай Gatherer, не давай Coder'у инструменты.

### 3. Детерминированные роутеры (ADR-0004, ADR-0009)

Роутеры `route_after_validate`, `route_after_review`, `route_after_retry` — **Python-функции, не LLM**. LLM не может пропустить валидацию, не может сделать 4-ю итерацию, не может решить «commit без review».

### 4. Pydantic v2 frozen (ADR-0007)

Все модели — `frozen=True`, `extra="forbid"`, `strict=True`. Иммутабельность = корректные LangGraph checkpoint'ы.

Исключения (`extra="allow"`) — только через ADR.

### 5. KB-as-code (ADR-0012)

- YAML — для машины (детект + генерация промпта)
- Markdown — для человека (расширенные описания)
- JSON Schema валидация при загрузке
- Любое новое правило — через PR

## Технические правила

### Python
- 3.12+, type hints обязательно
- Ruff + Mypy strict
- Строки ≤ 120 символов
- Docstrings — русский, имена — английский

### subprocess
- **НИКОГДА `shell=True`** — всегда list-form: `subprocess.run(["cmd", "arg1"], ...)`
- **ВСЕГДА `timeout=N`** — без timeout процесс может зависнуть
- **ВСЕГДА `capture_output=True`**
- Используй `sys.executable` для Python subprocess

### Secrets
- **НИКОГДА не коммить `.env`** с реальными секретами
- **НИКОГДА не коммить `.github-token`** — он в `.gitignore`
- Используй `.env.example` как шаблон
- При утечке токена — немедленно отзовите

### BSL LS
- BSL LS в отдельном контейнере (`1c-ai-bsl-ls`), HTTP API на :8080
- Timeout: 60 секунд (через `BSL_LS_TIMEOUT`)
- Если BSL LS не отвечает 10 секунд — fallback на `kb.check_antipatterns` (без Java)

## Process rules

### Перед изменением архитектуры
1. Проверь — может, уже есть ADR, описывающий это
2. Если нужно новое решение — создай ADR (см. шаблон в `adr/README.md`)
3. Изменения ADR — через PR с меткой `adr`

### Перед `1c-ai config build`
- **ВСЕГДА** сначала проверяй свежесть: `1c-ai config build --name X --check-freshness`
- Если индексы свежие — не пересобирай без `--force`
- Если устарели — `1c-ai config build --name X` (без `--force`, пересоберёт автоматически)

### Перед коммитом
```bash
# Полный чек-лист (см. CONTRIBUTING.md)
uv run ruff check packages/ tests/
uv run ruff format --check packages/ tests/
uv run mypy packages/
uv run pytest tests/ -m smoke
python scripts/check_package_boundaries.py
```

### Коммиты
- Формат: `<type>(<scope>): <description>`
- Один коммит — одно логическое изменение
- Перед push: тесты проходят

### 1С XML namespace handling (ВАЖНО)
- 1С XML использует `xmlns="http://v8.1c.ru/8.3/data/core"`, теги в lxml → `{ns}Catalog`
- `elem.find('Catalog')` НЕ находит — нужно `elem.xpath('./*[local-name()="Catalog"]')`
- В `parsers/xml/_xml_utils.py` все функции поиска используют xpath с local-name()
- `_local_name(elem)` парсит tag вручную (работает с {ns}Name и prefix:Name)
- **НЕ ИСПОЛЬЗОВАТЬ** `elem.find/findall` напрямую для 1С XML — только через `_xml_utils`

### Pydantic strict + JSON round-trip
- `strict=True` (ADR-0007) ломает `model_validate(dict)` для datetime полей
- Решение: `model_validate_json(json.dumps(entry))` — паттерн для всех JSON-persistence
- Для `model_dump(mode="json")` — оборачивай в `dict()`: `dict(obj.model_dump(mode="json"))`

## Структура BSL-модуля (для генерации)
- Области: `ПрограммныйИнтерфейс` → `СлужебныйПрограммныйИнтерфейс` → `СлужебныеПроцедурыИФункции` → `ОбработчикиСобытийФормы`
- Без `ё` в коде
- Без EM DASH (`—`), используй дефис (`-`)
- Отступы — табы, не пробелы
- Экспортные процедуры — с комментариями-документацией

## Запросы 1С
- Ключевые слова КАПСОМ: `ВЫБРАТЬ`, `ИЗ`, `ГДЕ`, `УПОРЯДОЧИТЬ ПО`
- Без `SELECT *` — указывай конкретные поля
- Без функций в `WHERE` — замедляет запрос

## Антипаттерны (НЕ делать)
- ❌ Модифицировать архитектуру без ADR
- ❌ Давать Coder'у инструменты
- ❌ Делать роутеры на LLM
- ❌ Использовать мутабельные модели
- ❌ Коммитить `.env`, `.github-token`, `data/`, `derived/`, `runtime/`
- ❌ Использовать `shell=True` в subprocess
- ❌ Пробелы вместо табов в BSL
- ❌ Букву `ё` в BSL
- ❌ EM DASH в BSL
- ❌ Дублировать правила в AGENTS.md и CONTRIBUTING.md

---

*Этот файл — живой документ. Добавляй правила при новых инцидентах.*
*Каждая новая строка — результат инцидента, не фантазия.*
