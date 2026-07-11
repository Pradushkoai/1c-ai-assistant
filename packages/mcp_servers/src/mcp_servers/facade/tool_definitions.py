"""Tool definitions для Facade — 8 visible tools.

Это единственное, что видит LLM внешнего клиента (Cursor, Claude).

См. ADR-0013 (Agent-Facade — 7 lifecycle tools).
"""

from __future__ import annotations

from typing import Any

# 8 visible tools Facade'а
FACADE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "plan",
        "gather",
        "generate",
        "validate",
        "review",
        "explain",
        "run_cli",
        "data_status",
    }
)

# Описания tools (для MCP inputSchema)
FACADE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "plan",
        "description": (
            "Запустить план декомпозиции задачи. Возвращает plan_id + список подзадач + "
            "next_action (что вызывать дальше). "
            "Пример: plan(task='Добавить обработку проведения для Реализации', "
            "config_name='ut11', config_version='4.5.3', platform_version='8.3.20')"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Описание задачи"},
                "config_name": {"type": "string"},
                "config_version": {"type": "string"},
                "platform_version": {"type": "string"},
            },
            "required": ["task", "config_name", "config_version", "platform_version"],
        },
    },
    {
        "name": "gather",
        "description": (
            "Собрать контекст для подзадачи. Запускает metadata + codebase + kb MCP-серверы "
            "параллельно. Возвращает context_summary + next_action=generate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "subtask_id": {"type": "string"},
            },
            "required": ["plan_id", "subtask_id"],
        },
    },
    {
        "name": "generate",
        "description": (
            "Сгенерировать BSL-код для подзадачи. Coder agent использует собранный контекст. "
            "Возвращает код + explanation + next_action=validate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "subtask_id": {"type": "string"},
                "iteration": {"type": "integer", "minimum": 1, "default": 1},
            },
            "required": ["plan_id", "subtask_id"],
        },
    },
    {
        "name": "validate",
        "description": (
            "Запустить детерминированную валидацию (BSL LS + KB антипаттерны). "
            "Возвращает passed/findings + next_action (review или generate для retry)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string", "description": "Из generate.artifact_id"},
            },
            "required": ["artifact_id"],
        },
    },
    {
        "name": "review",
        "description": (
            "LLM-рецензент: проверить код и решить proceed/retry/escalate. "
            "При proceed — открывается PR. При retry — next_action=generate. "
            "При escalate — next_action=data_status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string"},
            },
            "required": ["artifact_id"],
        },
    },
    {
        "name": "explain",
        "description": (
            "Объяснить существующий BSL-код или найти ответ на вопрос. "
            "Read-only — не изменяет код. Использует kb + codebase MCP."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "query": {"type": "string"},
                "config_name": {"type": "string"},
                "config_version": {"type": "string"},
            },
        },
    },
    {
        "name": "run_cli",
        "description": (
            "Proxy к скрытым MCP tools (не lifecycle). "
            "Пример: run_cli(tool_name='metadata.get_metadata', "
            "args={'object_ref': 'Catalog.Контрагенты', ...}, caller_role='GATHERER')"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string"},
                "args": {"type": "object"},
                "caller_role": {"type": "string", "default": "GATHERER"},
            },
            "required": ["tool_name", "args"],
        },
    },
    {
        "name": "data_status",
        "description": "Статус данных проекта: paths, configs, freshness, missing prerequisites.",
        "input_schema": {"type": "object", "properties": {}},
    },
]
