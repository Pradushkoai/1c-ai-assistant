# AGENTS.md — Правила для AI-агентов в репозитории 1c-ai-assistant

> **Этот файл — журнал правил для AI-агентов (Cursor, Claude, Codex).**
> Прочитай перед каждой рабочей сессией.

---

## Текущий статус

**Stage 5 (Production Hardening) завершён.** Все 5 этапов закрыты.
**1032 теста** проходят + 14 skipped. CI зелёная. **mypy 0 ошибок**. ruff check+format чистый.

**Что готово (Этапы 1-5):**
- **Этап 1** (5/5): parsers (xml/bsl/hbk/models/indexers), data_layer, agent CLI
- **Этап 2** (7/7): ADR-0020 embeddings, codebase MCP, standards (4 СТО + 4 БСП),
  BSL LS Docker, library add, transitive closure, api-reference в pipeline
- **Stage 3** (4/4): PostgresSaver persistence, Facade handlers (8 lifecycle tools),
  git MCP (4 tools + безопасность), Docker production (multi-stage + `1c-ai health`)
- **Stage 4** (4/4): metadata MCP server + gather/plan wiring (ADR-0003/0005/0010),
  commit_node → git MCP (real git flow), `1c-ai mcp serve` CLI + режим C (6 серверов),
  integration tests + docs sync
- **Stage 5** (4/4): FacadeStateStore survival-restart, REST API HTTP server
  (`1c-ai serve` FastAPI :8000), ZaiLLM mypy cleanup (TD-011 закрыт, 0 ошибок),
  CI integration tests + ruff format

**Метрики:**
- **21 ADR** (Architecture Decision Records) в `adr/`
- **29 MCP tools** (21 domain + 8 facade) в 6 серверах
- **4 параллельных валидатора** в validate_node (asyncio.TaskGroup)
- **23 KB сущности** (5 patterns + 10 antipatterns + 8 standards)
- **0 boundary violations** (DI через functools.partial)
- **mypy: 0 ошибок** (TD-011 закрыт)
- **HBK**: 10,150 методов платформы 8.3.25

**CLI команды:**
- `1c-ai init` / `config add|build|list|remove` / `validate` / `health`
- `1c-ai generate` — pipeline end-to-end (real git commit если `1C_AI_REPO_PATH` задан)
- `1c-ai mcp serve --server {facade|metadata|codebase|kb|bsl_ls|git}` — MCP stdio (режим B/C)
- `1c-ai serve` — HTTP REST API server (FastAPI :8000, режим A)
- `1c-ai hbk load` / `library add|build|list|remove`

---

## Перед началом работы

1. **Прочитай AGENTS.md** (этот файл)
2. **Прочитай [docs/architecture/CONCEPTUAL.md](docs/architecture/CONCEPTUAL.md)** — концептуальная архитектура
3. **Прочитай [adr/](adr/)** — 21 ADR с обоснованием решений
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
