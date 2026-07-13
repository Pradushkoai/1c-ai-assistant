"""TaskState — главное состояние pipeline.

Иммутабельное (frozen=True). Каждый узел возвращает НОВЫЙ state,
не мутирует старый. LangGraph checkpoint'ы сериализуют это в Postgres.

См. ADR-0009 (Pipeline contracts — центральный контракт).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from parsers.models import ModelConfig, ObjectRef
from pydantic import Field


class FSMState(StrEnum):
    """Состояния pipeline. Сохраняются в TaskState.fsm_state."""

    INIT = "init"
    PLANNING = "planning"
    GATHERING = "gathering"
    CODING = "coding"
    VALIDATING = "validating"
    REVIEWING = "reviewing"
    COMMITTING = "committing"
    ESCALATED = "escalated"
    DONE = "done"
    FAILED = "failed"


class SubtaskConstraints(ModelConfig):
    """Ограничения подзадачи — инжектируются в промпт."""

    dont_list: list[str] = Field(default_factory=list, description="Что НЕ делать")
    must_list: list[str] = Field(default_factory=list, description="Что ОБЯЗАТЕЛЬНО сделать")
    available_modules: list[str] = Field(
        default_factory=list,
        description="Имена общих модулей, которые можно вызывать",
    )
    target_context: str = Field(
        default="server",
        description="server | thin_client | mobile_client — для check_method_availability",
    )


class Subtask(ModelConfig):
    """Подзадача — результат декомпозиции Plan'ом."""

    id: str = Field(description="UUID подзадачи")
    name: str = Field(description="Человеческое имя, например 'ОбработкаПроведения'")
    target_module: ObjectRef = Field(description="Catalog.Контрагенты.ObjectModule")
    description: str = Field(description="Что нужно сделать")
    inputs: list[str] = Field(default_factory=list, description="Что подаётся на вход")
    outputs: list[str] = Field(default_factory=list, description="Что ожидается на выходе")
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="Критерии приёмки — используются в Test/Review",
    )
    json_schema: dict[str, Any] | None = Field(
        default=None,
        description="JSON Schema для structured_output Coder'а",
    )
    constraints: SubtaskConstraints | None = None
    max_iterations: int = Field(default=3, ge=1, le=5)
    status: Literal["pending", "in_progress", "done", "failed", "escalated"] = "pending"


class Iteration(ModelConfig):
    """Итерация генерации кода — одна попытка Coder'а для подзадачи."""

    number: int = Field(ge=1, description="1 = первая попытка, 2 = первый retry, ...")
    code: str = Field(description="Сгенерированный BSL-код")
    llm_response: dict[str, Any] = Field(description="Полный ответ LLM (для трассировки)")
    bsl_ls_diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    review_findings: list[dict[str, Any]] = Field(default_factory=list)
    test_result: bool | None = None  # без Vanessa — всегда None
    edit_distance_vs_prev: float = Field(default=0.0, description="0..1, мера изменения кода")
    failed_checks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Конкретные ошибки для retry-промпта",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TaskState(ModelConfig):
    """Главное состояние pipeline. Передаётся между всеми узлами.

    Frozen. Каждый узел возвращает новый TaskState через model_copy(update={...}).
    """

    # Идентификация
    task_id: str = Field(description="UUID задачи")
    description: str = Field(description="Исходный промпт пользователя")
    config_name: str = Field(description="Имя конфигурации: 'ut11'")
    config_version: str = Field(description="Версия конфигурации: '4.5.3'")
    platform_version: str = Field(description="Версия платформы: '8.3.20'")

    # Версия схемы TaskState (ADR-0018). Bump только при breaking change
    # (rename/type-change поля). Добавление/удаление полей — bump НЕ нужен.
    schema_version: int = Field(default=1, ge=1, description="Версия схемы TaskState (ADR-0018)")

    # Декомпозиция
    subtasks: list[Subtask] = Field(default_factory=list)
    current_subtask_idx: int = Field(default=0, ge=0)

    # Итерации
    current_iteration: int = Field(default=0, ge=0, description="0 = ещё не было попыток")
    iterations: list[Iteration] = Field(default_factory=list, description="Только для текущей подзадачи")

    # FSM
    fsm_state: FSMState = FSMState.INIT

    # Фокус-контроль
    constraints_reminder: str = Field(
        default="",
        description="Строка, добавляемая в начало каждого промпта retry",
    )

    # Роутер-сигналы (заполняются узлами, читаются роутерами)
    validation_passed: bool = False
    review_passed: bool = False
    critical_findings: int = 0

    # Промежуточные результаты (для facade и для тестов)
    plan_result: dict[str, Any] | None = None
    gather_result: dict[str, Any] | None = None
    validate_result: dict[str, Any] | None = None
    review_result: dict[str, Any] | None = None
    commit_result: dict[str, Any] | None = None

    # Метаданные
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    parent_checkpoint_id: str | None = None

    # Трассировка (для LangSmith)
    trace_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def current_subtask(self) -> Subtask | None:
        """Текущая подзадача или None, если все выполнены."""
        if self.current_subtask_idx >= len(self.subtasks):
            return None
        return self.subtasks[self.current_subtask_idx]
