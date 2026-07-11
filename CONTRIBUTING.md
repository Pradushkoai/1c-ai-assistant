# CONTRIBUTING

Спасибо за интерес к проекту 1C AI Assistant.

## Перед началом работы

1. Прочтите [docs/architecture/CONCEPTUAL.md](docs/architecture/CONCEPTUAL.md) — концептуальная архитектура без кода
2. Прочтите [adr/](adr/) — 17 ADR с обоснованием решений
3. Прочтите [AGENTS.md](AGENTS.md) — правила для AI-агентов

## Разработка

```bash
# Установка
git clone https://github.com/Pradushkoai/1c-ai-assistant.git
cd 1c-ai-assistant
uv sync --all-extras

# Тесты
uv run pytest tests/ -v

# Линтеры
uv run ruff check packages/
uv run mypy packages/

# Docker (3 контейнера)
docker compose up -d
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
- Docstrings и комментарии — русский (см. ADR-0008 в старом проекте)

## Лицензия

MIT — см. [LICENSE](LICENSE)
