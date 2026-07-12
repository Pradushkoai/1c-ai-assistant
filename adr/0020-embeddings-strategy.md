# ADR-0020: Embeddings strategy — гибридный поиск с multi-layer индексацией

**Статус:** Accepted
**Дата:** 2026-07-13
**Связан:** Уточняет ADR-0015 (3-container deployment), ADR-0017 (VectorStoreProtocol)

---

## Контекст

После завершения Этапа 1 (контекст для Coder) система имеет 5 источников
контекста: формы, подсистемы, export-методы, граф вызовов, граф зависимостей.
Но отсутствует **семантический поиск по коду** — Coder не может найти
существующие решения похожих задач.

### Реальные метрики (из Sprint 3.2 на УТ 11/4.5.3)

| Метрика | Значение |
|---|---|
| BSL модулей | 7,141 |
| Строк кода | 3,528,799 |
| Export-методов | 27,581 |
| Средний размер модуля | 494 строк |
| Среднее методов на модуль | 14.4 |
| Платформенных методов (8.3.25) | 10,150 |
| Объектов метаданных | 5,575 |
| Рёбер зависимостей | 6,802 |

### Три ключевых вводных (от product owner, 2026-07-13)

1. **Граф вызовов с цепочками** — Planner и Reviewer нуждаются в transitive
   closure для оценки blast radius. Coder — нет (достаточно 1-hop).
2. **Доступ ко всем export-методам** — api-reference уже построен, но
   должен быть подключён к pipeline и использоваться как chunk boundaries.
3. **Множественные конфигурации** — БСП, БПО, типовые и нетиповые конфиги,
   разные версии платформы. Требуется разделение слоёв индексации.

---

## Решение

### 1. Гибридный поиск: BM25 + pgvector + RRF

**Не чистый BM25, не чистый векторный — именно гибрид.**

| Компонент | Что ищет | Технология |
|---|---|---|
| **BM25** | Точные имена методов, ключевые слова | postgres tsvector + GIN index |
| **Векторный** | Семантика, синонимы, смысл | pgvector + cosine similarity |
| **RRF** | Объединение результатов | Reciprocal Rank Fusion: `1/(k+rank)` |

**Почему гибрид, а не один:**
- BM25 пропускает «ОбработкаПроведения» при запросе «проведение документа»
- Векторный пропускает точное имя «ПодобратьМестаХранения» (редкое имя)
- Гибрид получает лучшие результаты обоих

### 2. Embeddings модель: multilingual-e5-large (1024 dim)

| Параметр | Значение | Обоснование |
|---|---|---|
| Модель | intfloat/multilingual-e5-large | Мультилингвальный (100+ языков), отлично с русским |
| Размерность | 1024 | Компактнее чем OpenAI 3072, достаточно для recall >90% |
| Запуск | Локально через fastembed | Бесплатно, не требует API ключа, ~30 мин на CPU |
| Хранение | pgvector `VECTOR(1024)` | 27,581 × 1024 × 4 bytes ≈ 107 MB — влезает в память |

**Примечание:** BGE-M3 был запланирован первоначально, но недоступен в fastembed.
multilingual-e5-large — 1024 dim, мультилингвальный (100+ языков), проверенный.

**Альтернатива (отклонена):** OpenAI text-embedding-3-large (3072 dim).
Причины: платно, требует API ключ, 3x больше хранилища, recall +1-2%
не оправдывает стоимость и сложность.

### 3. Chunking стратегия: по методам

**Chunk = один export-метод (сигнатура + тело + комментарии).**

| Параметр | Значение |
|---|---|
| Количество чанков | 27,581 (по числу export-методов) |
| Средний размер чанка | ~34 строки (3.5M / 103k методов) |
| Содержимое чанка | method_name, parameters, body, comments, module_ref |

**Почему по методам, а не по модулям:**
- Средний модуль: 494 строк, 14.4 методов → один chunk содержит 14 тем
- Вектор «размазывается» по темам → неточный поиск
- Метод — тематически однороден → вектор точный
- Gatherer находит конкретный метод, а не весь модуль

**Chunk metadata (критично для multi-layer):**
```json
{
  "chunk_id": "ut11_4.5.3_CommonModule_ОбщегоНазначения_СообщитьПользователю",
  "source_layer": "config",
  "source_config": "ut11",
  "source_version": "4.5.3",
  "platform_version": "8.3.25",
  "module_kind": "CommonModule",
  "object_ref": "CommonModule.ОбщегоНазначения",
  "method_name": "СообщитьПользователю",
  "is_export": true,
  "is_function": false,
  "parameters": ["Сообщение", "КлючСтроки"],
  "tsvector": "...",
  "embedding": [0.1, 0.2, ...]
}
```

### 4. Multi-layer индексация (4 слоя)

Реальный мир 1С имеет несколько слоёв кода, которые нужно разделять:

```
┌─────────────────────────────────────────────┐
│  Слой 1: Платформа (per-version)            │
│  platform-methods.db (8.3.20, 8.3.25, ...)  │
│  10,150 методов × N версий                   │
│  Embeddings: НЕТ (это справочник, не код)   │
│  Поиск: SQLite lookup (точный)               │
├─────────────────────────────────────────────┤
│  Слой 2: Библиотеки (БСП, БПО)              │
│  Отдельный индекс, шарится между конфигами   │
│  Embeddings: ДА, source_layer=library        │
│  Поиск: гибридный (BM25 + vector + RRF)      │
├─────────────────────────────────────────────┤
│  Слой 3: Конфигурация (per-config)          │
│  metadata, api-reference, call graph, deps   │
│  Embeddings: ДА, source_layer=config         │
│  Поиск: гибридный (BM25 + vector + RRF)      │
├─────────────────────────────────────────────┤
│  Слой 4: KB (глобальная)                    │
│  patterns, antipatterns, standards           │
│  Embeddings: НЕТ (15 документов — FTS5)      │
│  Поиск: SQLite FTS5 (BM25 на малой коллекции)│
└─────────────────────────────────────────────┘
```

**Почему 4 слоя, а не 2:**
- БСП включается в УТ11, ERP, Бухгалтерию — без отдельного слоя embeddings
  БСП дублируются для каждого конфига
- С разделением: БСП индексируется один раз, шарится между конфигами
- Gatherer фильтрует: `WHERE source_layer IN ('config', 'library')`

**Gatherer search query (пример):**
```sql
-- Гибридный поиск с фильтром по слоям
WITH bm25_results AS (
  SELECT chunk_id, ts_rank(tsvector, query) AS bm25_score
  FROM code_chunks
  WHERE source_layer IN ('config', 'library')
    AND source_config = 'ut11' OR source_layer = 'library'
  ORDER BY bm25_score DESC LIMIT 20
),
vector_results AS (
  SELECT chunk_id, 1 - (embedding <=> $1) AS vector_score
  FROM code_chunks
  WHERE source_layer IN ('config', 'library')
  ORDER BY embedding <=> $1 LIMIT 20
)
-- RRF fusion
SELECT chunk_id, SUM(1.0 / (60 + ROW_NUMBER())) AS rrf_score
FROM (
  SELECT chunk_id, ROW_NUMBER() OVER (ORDER BY bm25_score DESC) FROM bm25_results
  UNION ALL
  SELECT chunk_id, ROW_NUMBER() OVER (ORDER BY vector_score DESC) FROM vector_results
) ranked
GROUP BY chunk_id
ORDER BY rrf_score DESC LIMIT 10;
```

### 5. Переиндексация

| Событие | Действие |
|---|---|
| `1c-ai config build --force` | Переиндексация metadata + api-reference + call graph + dependency graph |
| `1c-ai config build-embeddings --force` | Переиндексация embeddings (отдельная команда, долго) |
| Смена модели embeddings | Полная переиндексация (через `embeddings_model_version` в meta) |
| Добавление библиотеки (БСП) | `1c-ai library add --name БСП --version 3.1 --zip bsp.zip` |
| Загрузка новой версии платформы | `1c-ai hbk load --version 8.3.25 --path ...` |

**Stale detection:** если `embeddings_model_version` в code_chunks не совпадает
с текущей моделью — помечаем как `stale_embeddings=True`, Gatherer предупреждает.

### 6. Transitive closure (отдельно от embeddings)

**Не часть ADR-0020, но зафиксировано здесь как связанное решение:**

| Роль | Transitive closure | Формат |
|---|---|---|
| Planner | ✅ Критично | Полный список + count (blast radius) |
| Reviewer | ⚠️ Полезно | Count транзитивных callers (impact) |
| Coder | ❌ Нет | 1-hop (прямые callers + callees) |

**Почему Coder не нуждается в transitive:**
1. Coder модифицирует один модуль (CONCEPTUAL.md §1.3)
2. Сигнатуры защищены 1-hop callers
3. Поведение защищено Reviewer'ом с impact count
4. Pipeline (Validator + retry + escalate) — последний рубеж

---

## Схема БД (pgvector)

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- для BM25 триграмм (опционально)

CREATE TABLE code_chunks (
    id BIGSERIAL PRIMARY KEY,
    chunk_id TEXT UNIQUE NOT NULL,
    source_layer TEXT NOT NULL,  -- 'platform' | 'library' | 'config' | 'kb'
    source_config TEXT,          -- 'ut11', 'БСП', 'ERP', NULL для platform/kb
    source_version TEXT,         -- '4.5.3', '3.1', NULL для platform/kb
    platform_version TEXT,       -- '8.3.25'
    module_kind TEXT,            -- 'CommonModule', 'ObjectModule', 'FormModule'
    object_ref TEXT,             -- 'CommonModule.ОбщегоНазначения'
    method_name TEXT,
    is_export BOOLEAN DEFAULT FALSE,
    is_function BOOLEAN DEFAULT TRUE,
    parameters JSONB DEFAULT '[]',
    code_text TEXT NOT NULL,     -- исходный код метода
    tsvector TSVECTOR,           -- для BM25
    embedding VECTOR(1024),      -- BGE-M3 вектор
    embeddings_model_version TEXT,  -- 'bge-m3-v1' для stale detection
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индексы
CREATE INDEX idx_chunks_tsvector ON code_chunks USING GIN (tsvector);
CREATE INDEX idx_chunks_embedding ON code_chunks USING IVFFLAT (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_chunks_layer ON code_chunks (source_layer, source_config, source_version);
CREATE INDEX idx_chunks_object ON code_chunks (object_ref);
```

## Целевые метрики качества

| Метрика | Цель | Метод измерения |
|---|---|---|
| Recall@10 | >90% | 100 тестовых запросов — есть ли релевантный в топ-10 |
| Precision@5 | >80% | В топ-5 — сколько релевантных |
| Latency | <100ms | pgvector IVFFlat + GIN tsvector |
| Хранилище | <500 MB | 27,581 чанков × (1024 × 4 + text + meta) |

---

## Последствия

### Положительные
- Coder находит существующие решения похожих задач
- Gatherer передаёт релевантный контекст (не случайный)
- Multi-layer: БСП индексируется один раз, шарится
- Гибридный поиск: точность BM25 + семантика векторов
- Локально через fastembed — не требует API ключа

### Отрицательные
- Требуется postgres с pgvector (ADR-0015 уже предусматривает)
- Переиндексация ~30 минут на 27,581 чанков (один раз)
- Дополнительная команда `1c-ai library add` для БСП/БПО
- IVFFlat индекс требует перестройки при больших изменениях

### Связанные ADR
- ADR-0015: 3-container deployment (postgres + pgvector) — основа
- ADR-0017: VectorStoreProtocol — pgvector как default, Qdrant как опция
- ADR-0018: TaskState migration — embeddings_model_version в state

---

## Реализация (порядок)

1. **`1c-ai library add`** — команда для БСП/БПО (отдельный от config)
2. **Embeddings indexer** — `parsers/indexers/embeddings_indexer.py`
   - fastembed + BGE-M3
   - chunking по export-методам
   - multi-layer metadata
3. **codebase MCP server** — `mcp_servers/codebase/server.py`
   - BM25 (tsvector) + vector (pgvector) + RRF
   - VectorStoreProtocol (ADR-0017)
4. **Gatherer integration** — подключить api-reference + codebase search
5. **Transitive closure** — `get_transitive_dependents` для Planner
6. **Бенчмарк** — 100 тестовых запросов, recall@10 / precision@5
