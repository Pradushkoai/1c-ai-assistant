# ADR-0019: Observability strategy

**Статус:** Accepted
**Дата:** 2026-07-11

## Контекст

Pipeline делает множество LLM-вызовов (Planner, Gatherer supervisor, Coder,
Reviewer). Без observability невозможно:
- Понять, почему задача провалилась
- Оценить стоимость (tokens, $)
- Найти узкое место (latency)
- Отследить drift (edit_distance_vs_prev < 5% — модель топчется)

Нужна стратегия: что трассировать, где хранить, как анализировать.

## Рассмотренные варианты

1. **Только LangSmith** — облако, платно, но лучший UX для LLM-трейсов
2. **Только structlog** — локально, бесплатно, но нет визуализации LLM-вызовов
3. **LangSmith + structlog** — гибрид: LangSmith для LLM-трейсов, structlog для инфраструктурных логов
4. **Prometheus + Grafana** — метрики, но не трейсы LLM-вызовов

## Решение

**LangSmith + structlog (гибрид).**

### 1. LangSmith — LLM-трейсы

**Что трассируется:**
- Каждый LLM-вызов: model, system_prompt, user_prompt, response, tokens_in, tokens_out, latency_ms, cost
- Pipeline run: task_id, subtask_count, iterations_count, escalation_count, total_cost, total_latency
- Retry: reason, prev_iteration_edit_distance, attempt_number

**Как включается:**
```python
import os
os.environ["LANGSMITH_API_KEY"] = "..."
os.environ["LANGSMITH_PROJECT"] = "1c-ai-assistant"
```

Если `LANGSMITH_API_KEY` не установлен — LangSmith отключается (NoOp fallback).

**Интеграция:**
- LangGraph автоматически интегрируется с LangSmith через env vars
- Каждый узел графа — отдельный step в трейсе
- `with_structured_output()` — видно JSON Schema и результат валидации

**Структура трейса:**
```
Pipeline Run (task_id=abc-123)
├── Plan Node
│   └── LLM Call (planner, model=gpt-4o, tokens=500+200, cost=$0.01)
├── Gather Node (subtask=st-001)
│   ├── LLM Call (gatherer supervisor, model=gpt-4o-mini, tokens=300+100)
│   ├── MCP: metadata.get_metadata (latency=120ms)
│   ├── MCP: codebase.semantic_search (latency=850ms)
│   └── MCP: kb.get_pattern (latency=50ms)
├── Code Node (iteration=1)
│   └── LLM Call (coder, model=claude-sonnet, tokens=2000+500, cost=$0.03)
├── Validate Node
│   ├── MCP: bsl_ls.lint (latency=3000ms)
│   └── MCP: kb.check_antipatterns (latency=200ms)
├── Review Node (iteration=1)
│   └── LLM Call (reviewer, model=gpt-4o, tokens=1500+300, cost=$0.02)
├── Code Node (iteration=2, retry)
│   └── LLM Call (coder, retry, edit_distance=0.03)
├── Validate Node (iteration=2)
├── Review Node (iteration=2, decision=proceed)
└── Commit Node
    └── MCP: git.commit + git.open_pr
```

### 2. structlog — инфраструктурные логи

**Что логируется:**
- Запуск/завершение pipeline (task_id, config, version)
- Переходы между узлами (fsm_state → new_fsm_state)
- MCP-вызовы (tool_name, latency, success/error)
- Ошибки (AgentError code, action, details)
- Freshness check результаты

**Формат:**
- CI/Docker: JSON lines (`LOG_FORMAT=json`)
- Dev: console с цветами (`LOG_FORMAT=console`)

**Конфигурация:**
```python
# orchestrator/logging.py (будет создан в Sprint 2)
import structlog
import os

def configure_logging() -> None:
    format = os.environ.get("LOG_FORMAT", "console")
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer() if format == "json"
            else structlog.dev.ConsoleRenderer(),
        ],
    )
```

**Пример лога (JSON):**
```json
{"event": "pipeline_start", "task_id": "abc-123", "config": "ut11", "version": "4.5.3", "level": "info", "timestamp": "2026-07-11T15:30:00Z"}
{"event": "node_transition", "from": "planning", "to": "gathering", "subtask_id": "st-001", "level": "info", "timestamp": "2026-07-11T15:30:05Z"}
{"event": "mcp_call", "tool": "bsl_ls.lint", "latency_ms": 3000, "success": true, "level": "info", "timestamp": "2026-07-11T15:30:10Z"}
{"event": "retry", "iteration": 2, "reason": "VALIDATION_FAILED", "edit_distance": 0.03, "level": "warning", "timestamp": "2026-07-11T15:30:15Z"}
{"event": "pipeline_end", "task_id": "abc-123", "total_cost": 0.06, "total_tokens": 5000, "total_latency_ms": 30000, "level": "info", "timestamp": "2026-07-11T15:30:30Z"}
```

### 3. Метрики (не для MVP)

Для Sprint 4+ — Prometheus метрики:
- `pipeline_runs_total` (counter)
- `pipeline_duration_seconds` (histogram)
- `pipeline_cost_usd` (histogram)
- `retry_count` (counter by reason)
- `escalation_count` (counter by reason)
- `mcp_call_duration_seconds` (histogram by tool_name)

Опционально с NoOp fallback (если prometheus-client не установлен).

### 4. Ключевые метрики для анализа

| Метрика | Где | Что значит |
|---|---|---|
| `total_cost` | LangSmith + structlog | Стоимость одной задачи |
| `total_tokens` | LangSmith | Token usage |
| `total_latency_ms` | structlog | Время выполнения |
| `iterations_count` | structlog | Сколько retry было |
| `edit_distance_vs_prev` | TaskState.iterations | Если <5% — модель топчется |
| `escalation_count` | structlog | Доля эскалаций |
| `mcp_call_duration` | structlog | Узкие места в MCP |

### 5. Alerting (не для MVP)

В Sprint 4+:
- Эскалация > 30% → alert
- Среднее retry > 2 → alert (промпты плохие)
- BSL LS latency > 30s → alert (Java проблема)

## Последствия

### Положительные
- LangSmith даёт визуальный трейс каждого LLM-вызова
- structlog — структурированные логи для CI и дебага
- NoOp fallback — работает без LangSmith API key
- Метрики для анализа эффективности pipeline

### Отрицательные
- LangSmith — платный (free tier: 5000 traces/month)
- structlog — ещё одна зависимость (но лёгкая)
- Метрики Prometheus — отложены до Sprint 4

## Реализация

- [ ] `orchestrator/logging.py` — configure_logging() (Sprint 2)
- [ ] LangSmith env vars в docker-compose.yml (Sprint 2)
- [ ] structlog log calls в узлах графа (Sprint 2)
- [ ] LangSmith trace metadata в TaskState (Sprint 2)
- [ ] Prometheus metrics (Sprint 4, опционально)

## Связанные документы

- ADR-0014 (Error taxonomy + PostgresSaver)
- ADR-0009 (Pipeline contracts — TaskState.trace_metadata)
- docs/architecture/10-prompts-spec.md (промпты)
