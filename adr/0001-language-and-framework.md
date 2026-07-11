# ADR-0001: Python 3.12 + LangGraph 1.x (изолирован в orchestrator/)

**Статус:** Accepted
**Дата:** 2026-07-11

## Контекст

Проект решает задачи разработки на платформе 1С:Предприятие 8.3 через мульти-агентный pipeline. Нужен фреймворк для оркестрации LLM-агентов с поддержкой:
- детерминированных роутеров (LLM не может пропускать этапы)
- subgraph'ов (mini-supervisor pattern)
- checkpoint'ов для длинных задач
- типизированного state (Pydantic)

## Рассмотренные варианты

1. **Native Python (без фреймворка)** — pros: полный контроль; cons: инфраструктура state/checkpoint/retry пишется с нуля, что уже сделано в LangGraph
2. **CrewAI** — pros: простой API; cons: слабая поддержка детерминированных роутеров, меньше контроля над графом
3. **AutoGen** — pros: мощный multi-agent; cons: ориентирован на диалог, не на pipeline
4. **LangGraph 1.x** — pros: явные StateGraph, conditional edges, checkpointers, mini-supervisor subgraphs; cons: молодой, API меняется

## Решение

**LangGraph 1.x**, изолированный в `packages/orchestrator/`. Бизнес-логика оперирует чистыми Pydantic-моделями и Protocol-контрактами; LangGraph живёт только в `orchestrator/graph.py` и `orchestrator/nodes/*.py`.

## Последствия

### Положительные
- Детерминированные роутеры `route_after_*` гарантируют, что LLM не пропустит валидацию
- `PostgresSaver` даёт персистентность из коробки
- Subgraph'ы позволяют мини-supervisor pattern без дублирования
- LangSmith integration для трассировки LLM-вызовов

### Отрицательные
- LangGraph 1.x — молодой, breaking changes возможны (митигация: pinned minor в `pyproject.toml`)
- `with_structured_output()` из langchain-core — неявная зависимость от langchain
- Изоляция в `orchestrator/` — это инкапсуляция, не настоящая развязка (state всё равно Pydantic)

## Связанные документы
- 00-overview.md (раздел 4: agent pipeline)
- 04-pipeline-contracts.md
- ADR-0009 (Pipeline contracts)
