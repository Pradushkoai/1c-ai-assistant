# DECISIONS.md — журнал архитектурных и операционных решений

> **Назначение:** фиксация решений, которые меняют план или архитектуру.
> ADR — для фундаментальных решений (язык, фреймворк, схема БД), ~20 за проект.
> DECISIONS — для операционных (отложить X, заменить Y, переключить фокус).
>
> **Формат ID:** `D-YYYY-MM-DD-NN` — дата + порядковый номер за день.
> **Принцип:** любое отклонение от плана → запись здесь.
> **ВАЖНО:** этот файл живёт в git репозитории (docs/process/), чтобы переживать сбросы окружения.

---

## Записи (новые сверху)

### D-2026-07-13-02: Стандарты 1С (СТО + БСП) как 3-й тип KB-сущностей

**Дата:** 2026-07-13
**Тип:** architecture
**Контекст:** TD-S4.2-03 требует проверки кода на соответствие стандартам 1С
(СТО — Стандарты Технологического Обмена, БСП — Библиотека Стандартных Подсистем).
Было два пути:
- A) Расширить существующую сущность antipattern полем `source` (СТО/БСП).
- B) Создать отдельную сущность `standard` (3-й тип KB).

**Решение:** Вариант B — отдельная сущность `standard`.

**Обоснование:**
- Семантика: antipattern = «плохая практика», standard = «требование стандарта 1С».
- У стандарта есть `source` (type+code+url) — у антипаттерна нет.
- Стандарты имеют более длинные description и url-ссылки на its.1c.ru.
- В поиске (search_kb) — отдельная категория 'standard'.
- В валидаторе — отдельный source='kb_standards' (4-й параллельный валидатор).

**Что сделано:**
- knowledge-base/standards/ — 8 YAML (4 СТО + 4 БСП), все с regex-detect.
- knowledge-base/schemas/standard.schema.json — JSON Schema.
- KBCollection.standards + get_standard + list_standards + detect_standards_violations.
- KbServer.get_standard + check_standards — 2 новых MCP tools (KB: 5→7).
- validate_node: 4-й параллельный валидатор (_run_standards_validator).
- ValidationFinding.source: Literal расширен до {"bsl_ls", "kb_antipatterns",
  "kb_standards", "custom_rules"}.
- 39 новых тестов в test_kb_standards.py.

**Повлияло на:**
- BACKLOG.md — TD-S4.2-03 закрыт
- CURRENT_FOCUS.md — Этап 2: 6/7 задач завершено
- packages/mcp_servers/src/mcp_servers/kb/ (loader.py, server.py, contracts.py)
- packages/orchestrator/src/orchestrator/nodes/validate.py + contracts.py
- knowledge-base/index.json + schemas/standard.schema.json + standards/*.yaml
- tests/mcp_servers/test_kb_standards.py + test_mcp_contracts.py

---

### D-2026-07-13-01: ADR-0020 — гибридный поиск + multi-layer индексация

**Дата:** 2026-07-13
**Тип:** architecture
**Контекст:** Этап 1 завершён, нужен семантический поиск по коду для Coder.
Пользователь дал 3 вводных: transitive closure, export-методы, множественные
конфигурации (БСП/БПО/версии).

**Решение:** ADR-0020 — гибридный BM25+pgvector+RRF, BGE-M3 1024 dim локально,
chunking по export-методам (27,581 чанков), 4-layer индексация
(platform/library/config/KB) с metadata-тегами.

**Transitive closure:** Planner — да (blast radius), Reviewer — count, Coder — 1-hop.

**Повлияло на:**
- adr/0020-embeddings-strategy.md — НОВЫЙ
- adr/README.md — 20 ADR
- BACKLOG.md — TD-S4.2-01 закрыт, добавлены TD-S4.2-05/06/07
- CURRENT_FOCUS.md — фокус на Этап 2

---

### D-2026-07-12-09: Файлы состояния переносятся в git репозиторий (docs/process/)

**Дата:** 2026-07-12
**Тип:** process + architecture
**Контекст:** Окружение сессии сбросилось — пропали DECISIONS.md, BACKLOG.md,
PROJECT_BOOTSTRAP.md, PROCESS_FRAMEWORK.md. Они были в /home/z/my-project/
(окружение сессии, не git). Пользователь указал: файлы состояния должны
переживать сброс — иначе механизмы саморегуляции бесполезны.

**Альтернативы:**
- A) Оставить в /home/z/my-project/ — но при сбросе пропадают
- B) Перенести в git репозиторий (docs/process/) — переживают сброс
- C) Внешний backup (Google Drive и т.д.) — сложнее синхронизация

**Решение:** B

**Причина:**
- Git — уже есть, не нужно новой инфраструктуры
- Коммиты автоматически версионнируют файлы состояния
- При clone репозитория — файлы подтягиваются
- Версионность: можно смотреть историю решений через git log

**Повлияло на:**
- Файлы DECISIONS.md, BACKLOG.md, PROJECT_BOOTSTRAP.md, PROCESS_FRAMEWORK.md
  переносятся в /home/z/my-project/1c-ai-assistant/docs/process/
- .gitignore — НЕ исключает docs/process/
- CURRENT_FOCUS.md, INTERNAL_ROADMAP.md, worklog.md — тоже переносятся
- В .gitignore: оставить только data/, derived/, runtime/, vendor/

**Supersedates:** D-2026-07-12-05 (где я решил что файлы НЕ в репо — ошибка)

---

### D-2026-07-12-08: Этап 1 (контекст для Coder) — начинаю сразу. ADR-0020 отложен

**Дата:** 2026-07-12
**Тип:** focus-switch + sprint-scope
**Контекст:** MVP работает, но качество кода низкое — Coder генерирует вслепую.
Пользователь подтвердил принцип «глубина сначала» как постоянное правило.
Старый план Sprint 4 делал всё сразу — неправильный порядок для качества.

**Альтернативы:**
- A) ADR-0020 сначала (документ, 1-2 часа), потом Этап 1
- B) Этап 1 сразу (контекст для Coder), ADR-0020 отложить до Этапа 2
- C) Sprint 4 целиком как в плане

**Решение:** B

**Причина:**
- Этап 1 не зависит от embeddings (metadata MCP, call graph, api-reference —
  работают на парсерах, не на векторном поиске)
- ADR-0020 нужен только для codebase MCP (Этап 2). Делать сейчас — документ ради документа
- Принцип «глубина сначала»: сначала качество кода, потом полнота фич
- Старый репо 1c-ai-dev-env (MIT, мой) — можно переносить алгоритмы

**3 этапа вместо Sprint 4:**
- **Этап 1 (Sprint 4.1): Контекст для Coder** — metadata MCP + call graph + api-reference
- **Этап 2 (Sprint 4.2): Поиск и качество** — ADR-0020 + codebase MCP + standards + BSL LS Docker
- **Этап 3 (Sprint 5): Production-readiness** — Postgres + Facade + git MCP + Docker production

**Принцип «Глубина сначала» (постоянное правило):**
Качество и глубина проработки — первостепенны. Скорость не важна.
Никогда не спрашивать пользователя про темп. Делать правильно, не быстро.

---

### D-2026-07-12-07: MVP Smoke Test — я (Z.ai GLM) как LLM для pipeline

**Дата:** 2026-07-12
**Тип:** focus-switch
**Контекст:** Пользователь сказал: «тестировать будем в твоей среде, LLM тоже
будешь ты». MVP first principle.

**Решение:** B — MVP Smoke Test, я (Z.ai GLM) как LLM через z-ai CLI subprocess.

**Результат (был потерян при сбросе, восстановлен):**
Pipeline end-to-end работает. 3 LLM-вызова (Plan/Code/Review) через ZaiLLM
adapter, structured_output работает, BSL код генерируется.

---

### D-2026-07-12-06: TD-002 — DI для orchestrator (boundary violations)

**Дата:** 2026-07-12
**Тип:** focus-switch
**Решение:** B — TD-002 сначала (DI refactor), потом ADR-0020.
**Результат (был потерян, восстановлен):** 3 boundary violations устранены
через functools.partial в build_graph(). 0 violations.

---

### D-2026-07-12-05: Механизмы саморегуляции (4 механизма + PROJECT_BOOTSTRAP)

**Дата:** 2026-07-12
**Тип:** process
**Решение:** 4 механизма (DECISIONS + BACKLOG + Contract Check + ФОКУС-строка)
+ PROJECT_BOOTSTRAP для переноса в новый чат.
**Superseded by:** D-2026-07-12-09 (файлы переносятся в git репо)

---

### D-2026-07-12-04: HBK Container32 возвращён из Sprint 4 в Sprint 3.2

**Дата:** 2026-07-12
**Тип:** focus-switch
**Решение:** B — прервать ADR-0020, реализовать HBK в Sprint 3.2.
**Результат (был потерян, восстановлен):** 10,150 методов загружено через
zlib + HTML парсинг (алгоритм из старого репо 1c-ai-dev-env).

---

### D-2026-07-12-03: Sprint 3.2 — валидация перед ADR-0020

**Дата:** 2026-07-12
**Тип:** sprint-scope
**Решение:** B — добавить Sprint 3.2 перед ADR-0020.
**Результат (был потерян, восстановлен):** Найден критичный баг (iter_metadata_files),
метрики собраны (27,581 методов, 3.5M строк).

---

### D-2026-07-12-02: HBK Container32 отложен на Sprint 4 (SUPERSeded)

**Дата:** 2026-07-12
**Тип:** tech-debt
**Решение:** Отложить, использовать хардкод 17 методов.
**Superseded by:** D-2026-07-12-04

---

### D-2026-07-12-01: Сначала аудит Sprint 1-3, потом Sprint 4

**Дата:** 2026-07-12
**Тип:** focus-switch
**Решение:** B — сначала фиксы. Sprint 4 (Postgres) закрепил бы баги.
**Результат (был потерян, восстановлен):** 4 бага закрыты в Sprint 3.1 + 3.1.1.

---

## Исторические решения (до внедрения DECISIONS.md)

### D-2026-07-11-01: EDT и Vanessa исключены из архитектуры
**Решение:** Убрать EDT и Vanessa, оставить 5 MCP серверов вместо 6+.
**Причина:** Не оправдано для solo-dev. Зафиксировано в CONCEPTUAL.md §9.

### D-2026-07-11-02: pgvector вместо Qdrant (по умолчанию)
**Решение:** pgvector как default, Qdrant как опция через VectorStoreProtocol.
**Причина:** Контейнер postgres уже нужен, меньше инфры. Зафиксировано в ADR-0017.

### D-2026-07-11-03: 3-контейнерный деплой
**Решение:** app + bsl-ls + postgres (с pgvector), вместо 1 контейнера.
**Причина:** Java изоляция критична. Зафиксировано в ADR-0015.
