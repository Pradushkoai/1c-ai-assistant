"""Общий Protocol для всех MCP tool contracts.

Каждый MCP-сервер реализует свои tools согласно этому Protocol.
Orchestrator (через ToolProvider) вызывает tools, опираясь на контракт.

См. ADR-0010 (MCP tool contracts — двойной контракт).
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class ToolContract(Protocol):
    """Контракт одного MCP tool.

    Атрибуты класса (не инстанса):
    - name: уникальное имя tool'а ('metadata.get_metadata')
    - description: для LLM (что делает, когда вызывать)
    - input_schema: JSON Schema для input
    - output_model: Pydantic v2 класс, который возвращает tool
    - error_contract: как обрабатываются ошибки
    - timeout: секунды
    - idempotent: повторный вызов = тот же результат?
    - required_role: какая роль может вызывать (для TOOL_GROUPS)
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    output_model: type[BaseModel]
    error_contract: Literal["exception", "error_dict", "empty_result"]
    timeout: int
    idempotent: bool
    required_role: str  # AgentRole value

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        """Выполнить tool. Возвращает dict, валидируемый в output_model.

        При ошибке:
        - 'exception' → raises ToolError
        - 'error_dict' → returns {'error': str, 'code': str}
        - 'empty_result' → returns {} или {'items': []}
        """
        ...


class ToolError(Exception):
    """Базовая ошибка MCP tool.

    Расширяется в orchestrator.errors (Шаг 9 архитектуры) до полной таксономии:
    ToolTimeoutError, ToolConnectionError, ToolExecutionError, RoleForbiddenError.

    Attributes:
        code: код ошибки (например, 'TOOL_TIMEOUT', 'TOOL_CONNECTION_FAILED').
        details: опциональный словарь с дополнительной информацией.
    """

    code: str = "TOOL_ERROR"

    def __init__(
        self,
        message: str,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if code:
            self.code = code
        self.details = details or {}


def make_mcp_tool(contract_cls: type[ToolContract]) -> Any:
    """Превратить ToolContract в mcp.types.Tool для регистрации в MCP server.

    Args:
        contract_cls: класс, реализующий ToolContract Protocol.

    Returns:
        mcp.types.Tool с name, description, inputSchema из контракта.

    Note:
        В Sprint 1.5 (каркас) mcp.types может быть не установлен —
        функция вызывается только в реальных MCP-серверах (Sprint 2+).
    """
    import mcp.types as types

    return types.Tool(
        name=contract_cls.name,
        description=contract_cls.description,
        inputSchema=contract_cls.input_schema,
    )
