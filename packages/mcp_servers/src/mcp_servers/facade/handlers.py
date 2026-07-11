"""Handlers для 7 lifecycle tools — заглушки.

В Sprint 1.5 (каркас) — все handlers возвращают NotImplementedError.
Реализация: Sprint 2-4.

См. ADR-0013 (Agent-Facade — 7 lifecycle tools).
"""

from __future__ import annotations

from typing import Any


class FacadeHandlers:
    """Все lifecycle handlers в одном классе.

    В Sprint 1.5 — заглушки. Реализация в Sprint 2-4.
    """

    async def handle_plan(self, args: dict[str, Any]) -> dict[str, Any]:
        """plan — декомпозиция задачи на подзадачи."""
        raise NotImplementedError("handle_plan — реализация в Sprint 3")

    async def handle_gather(self, args: dict[str, Any]) -> dict[str, Any]:
        """gather — сбор контекста для подзадачи."""
        raise NotImplementedError("handle_gather — реализация в Sprint 3")

    async def handle_generate(self, args: dict[str, Any]) -> dict[str, Any]:
        """generate — LLM генерация BSL-кода."""
        raise NotImplementedError("handle_generate — реализация в Sprint 2")

    async def handle_validate(self, args: dict[str, Any]) -> dict[str, Any]:
        """validate — BSL LS + KB антипаттерны."""
        raise NotImplementedError("handle_validate — реализация в Sprint 2")

    async def handle_review(self, args: dict[str, Any]) -> dict[str, Any]:
        """review — LLM-рецензент: proceed/retry/escalate."""
        raise NotImplementedError("handle_review — реализация в Sprint 3")

    async def handle_explain(self, args: dict[str, Any]) -> dict[str, Any]:
        """explain — обратный путь: код → объяснение."""
        raise NotImplementedError("handle_explain — реализация в Sprint 4")

    async def handle_run_cli(self, args: dict[str, Any]) -> dict[str, Any]:
        """run_cli — proxy к скрытым MCP tools."""
        raise NotImplementedError("handle_run_cli — реализация в Sprint 4")

    async def handle_data_status(self, args: dict[str, Any]) -> dict[str, Any]:
        """data_status — статус данных проекта."""
        raise NotImplementedError("handle_data_status — реализация в Sprint 4")
