# CONTRIBUTING

Спасибо за интерес к проекту 1C AI Assistant.

## Перед началом работы

1. Прочтите [docs/architecture/CONCEPTUAL.md](docs/architecture/CONCEPTUAL.md) — концептуальная архитектура без кода
2. Прочтите [adr/](adr/) — 21 ADR с обоснованием решений
3. Прочтите [AGENTS.md](AGENTS.md) — правила для AI-агентов
4. Прочтите [CHANGELOG.md](CHANGELOG.md) — история изменений

## Разработка

### Установка

```bash
git clone https://github.com/Pradushkoai/1c-ai-assistant.git
cd 1c-ai-assistant
uv sync --all-extras --all-packages
```

### Running tests locally

```bash
# Все тесты (344 теста, ~2 секунды)
uv run pytest tests/ -v

# Только smoke тесты (быстро, ~1 секунда)
uv run pytest tests/ -m "smoke" -v

# С coverage отчётом
uv run pytest tests/ --cov=packages --cov-report=term-missing --cov-fail-under=80

# Только определённый пакет
uv run pytest tests/parsers/ -v
uv run pytest tests/data_layer/ -v
uv run pytest tests/agent/ -v

# Property-based тесты (hypothesis)
uv run pytest tests/ -m "property" -v

# Конкретный тест
uv run pytest tests/parsers/test_models.py::TestObjectRef::test_from_string_valid -v
```

### Линтеры

```bash
# Ruff — линтер и форматтер
uv run ruff check packages/ tests/
uv run ruff format packages/ tests/

# Mypy — типизация
uv run mypy packages/

# Проверка границ пакетов (CI-скрипт)
python scripts/check_package_boundaries.py
```

### Перед коммитом (чек-лист)

- [ ] `uv run ruff check packages/ tests/` — без ошибок
- [ ] `uv run ruff format --check packages/ tests/` — отформатировано
- [ ] `uv run mypy packages/` — без ошибок
- [ ] `uv run pytest tests/ -m "smoke"` — зелёные
- [ ] `python scripts/check_package_boundaries.py` — OK
- [ ] Если добавлен новый код — есть тесты
- [ ] Coverage не упал

### CLI разработка

```bash
# Инициализация тестового проекта
mkdir /tmp/test-project && cd /tmp/test-project
cat > paths.env << 'EOF'
DATA_DIR=./data
DERIVED_DIR=./derived
RUNTIME_DIR=./runtime
KNOWLEDGE_BASE_DIR=./kb
VENDOR_DIR=./vendor
EOF

# Запуск CLI из репозитория
uv run --directory /path/to/1c-ai-assistant 1c-ai --project /tmp/test-project init
uv run --directory /path/to/1c-ai-assistant 1c-ai --project /tmp/test-project config add --name mini --version 1.0 --zip /path/to/1c-ai-assistant/tests/fixtures/mini_config.zip
uv run --directory /path/to/1c-ai-assistant 1c-ai --project /tmp/test-project config build --name mini
uv run --directory /path/to/1c-ai-assistant 1c-ai --project /tmp/test-project config list
```

### Docker (Sprint 4+)

```bash
# 3 контейнера: app + bsl-ls + postgres
docker compose up -d

# Логи
docker compose logs -f 1c-ai-app

# Остановка
docker compose down
```

## Коммиты

Формат: `<type>(<scope>): <description>`

Типы:
- `feat` — новая функциональность
- `fix` — bugfix
- `docs` — документация
- `refactor` — рефакторинг без изменения API
- `test` — тесты
- `chore` — инфраструктура, зависимости
- `adr` — новый ADR или изменение существующего

Пример: `feat(parsers): add XML catalog parser`

## ADR

Любое архитектурное решение — через новый ADR:
1. Скопировать `adr/0000-template.md` (создать при необходимости)
2. Назвать `adr/00NN-short-kebab-title.md`
3. PR с меткой `adr`

## Code Style

- Python 3.12+
- Ruff для линтинга (конфиг в `pyproject.toml`)
- Mypy strict (без `Any` кроме явных исключений)
- Строки ≤ 120 символов
- Имена функций/переменных — английский
- Docstrings и комментарии — русский

## Лицензия

MIT — см. [LICENSE](LICENSE)
