"""code node — LLM генерация BSL-кода (simple node, без инструментов).

Реализация: Sprint 2.
"""

from __future__ import annotations

from typing import Any

from ..state import TaskState


async def code_node(state: TaskState) -> dict[str, Any]:
    """Сгенерировать BSL-код через LLM с structured_output.

    Coder не имеет MCP-инструментов (TOOL_GROUPS[CODER] = {}).
    Получает контекст от Gatherer и только генерирует.

    Returns:
        dict с iterations (новая Iteration добавлена) и current_iteration.

    Raises:
        NotImplementedError: в Sprint 1.5 (каркас).
    """
    raise NotImplementedError("code_node — реализация в Sprint 2")
