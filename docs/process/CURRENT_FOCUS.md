# CURRENT FOCUS — точка входа для каждой сессии

> **Этот файл живёт в git репозитории (docs/process/), чтобы переживать сбросы окружения.**
> Последнее обновление: 2026-07-12 (восстановление после сброса)

---

## 🎯 ФОКУС СЕССИИ

> **Задача:** Восстановление завершено → Этап 1 (контекст для Coder)
> **Статус:** восстановление завершено, готов к Этапу 1
> **Блокеры:** нет
> **Следующий шаг:** TD-S4.1-01 Form/Subsystem/Role парсеры (metadata MCP)
>
> **Принцип «Глубина сначала»** (D-2026-07-12-08): качество важнее скорости.

---

## 📊 Текущий статус

- **Спринты завершены:** 0, 1, 1.5, 2, 3, 3.1 (восстановлены: 3.2, 3.2.1, 3.3)
- **Тесты:** 650 проходят
- **MVP:** ✅ `1c-ai generate` работает с реальной LLM (ZaiLLM через z-ai CLI)
- **HBK:** 10,150 методов платформы 8.3.25 (Container32 парсер)
- **Boundary violations:** 0 (DI через functools.partial)
- **Данные:** УТ11 (5,575 объектов, 7,141 BSL модулей) + HBK 8.3.25 (80 файлов)

---

## 📂 Файлы проекта (все в git репозитории)

| Файл | Назначение |
|---|---|
| `docs/process/PROJECT_BOOTSTRAP.md` | Точка входа для нового агента |
| `docs/process/CURRENT_FOCUS.md` | Этот файл — ФОКУС + статус |
| `docs/process/INTERNAL_ROADMAP.md` | Стратегический план |
| `docs/process/DECISIONS.md` | Журнал решений (D-YYYY-MM-DD-NN) |
| `docs/process/BACKLOG.md` | Реестр техдолга (TD-NNN) |
| `docs/process/worklog.md` | Журнал выполненных задач |
| `docs/process/TESTING_POLICY.md` | Политика тестирования |
| `docs/architecture/CONCEPTUAL.md` | Главный контракт |
| `adr/` | 19 ADR |

---

## 🔒 Contract Check (читать ПЕРЕД git commit)

### Триггеры по файлам

| Меняешь | Сверить с |
|---|---|
| `packages/orchestrator/nodes/*.py` | CONCEPTUAL.md §2.1 + ADR-0004 + ADR-0009 |
| `packages/parsers/src/parsers/hbk/*` | 12-real-data-validation.md + ADR-0006 |
| `packages/mcp_servers/*/contracts.py` | ADR-0010 + 05-mcp-tool-contracts.md |
| `packages/orchestrator/state.py` | ADR-0009 + ADR-0018 |
| `packages/orchestrator/tool_groups.py` | ADR-0005 + ADR-0011 + CONCEPTUAL.md §2.2 |
| `packages/parsers/models/*` | ADR-0007 + 02-pydantic-models.md |
| `knowledge-base/prompts/*.j2` | 10-prompts-spec.md |
| `knowledge-base/{patterns,antipatterns}/*.yaml` | ADR-0012 + 07-kb-as-code.md |

### Общие проверки

- [ ] Новый техдолг → BACKLOG.md?
- [ ] Изменён план → INTERNAL_ROADMAP.md?
- [ ] Операционное решение → DECISIONS.md?
- [ ] ФОКУС-строка актуальна?
- [ ] worklog.md обновлён?

---

## ✅ Session Checkpoint (читать ПЕРЕД закрытием сессии)

- [ ] ФОКУС-строка обновлена?
- [ ] worklog.md — запись добавлена?
- [ ] DECISIONS.md — решения зафиксированы?
- [ ] BACKLOG.md — техдолг обновлён?
- [ ] Тесты проходят? ruff чистый?
- [ ] Коммит запушен от Pradushkoai?
- [ ] Security audit: токен не утёк?
- [ ] docs/process/ файлы закоммичены (переживают сброс)?

---

## 🛠 Команды

```bash
# Тесты
unset VIRTUAL_ENV && UV_CACHE_DIR=/tmp/uv-cache uv run --directory /home/z/my-project/1c-ai-assistant pytest tests/ -v

# Lint
unset VIRTUAL_ENV && UV_CACHE_DIR=/tmp/uv-cache uv run --directory /home/z/my-project/1c-ai-assistant ruff check packages/ tests/
unset VIRTUAL_ENV && UV_CACHE_DIR=/tmp/uv-cache uv run --directory /home/z/my-project/1c-ai-assistant mypy packages/

# Boundaries
unset VIRTUAL_ENV && UV_CACHE_DIR=/tmp/uv-cache uv run --directory /home/z/my-project/1c-ai-assistant python scripts/check_package_boundaries.py

# Git push (НЕ git add -A, только конкретные файлы)
TOKEN=$(cat /home/z/my-project/.github-token | tr -d '\n' | tr -d '[:space:]')
git -C /home/z/my-project/1c-ai-assistant config user.name "Pradushkoai"
git -C /home/z/my-project/1c-ai-assistant config user.email "Pradushkoai@users.noreply.github.com"
git -C /home/z/my-project/1c-ai-assistant add <file1> <file2> ...
git -C /home/z/my-project/1c-ai-assistant commit -m "feat(...): ..."
git -C /home/z/my-project/1c-ai-assistant remote set-url origin "https://x-access-token:${TOKEN}@github.com/Pradushkoai/1c-ai-assistant.git"
git -C /home/z/my-project/1c-ai-assistant push origin main
git -C /home/z/my-project/1c-ai-assistant remote set-url origin "https://github.com/Pradushkoai/1c-ai-assistant.git"
```
