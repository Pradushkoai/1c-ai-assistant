"""kb-server: база знаний + platform methods.

Источник 1: knowledge-base/{patterns,antipatterns}/*.yaml
Источник 2: derived/platform/{version}/platform-methods.db (SQLite из .hbk)
Парсер: parsers.hbk + YAML loader
Рантайм: Python

См. ADR-0010 (MCP tool contracts) и ADR-0012 (KB-as-code).
"""

from __future__ import annotations

from typing import Any, Literal

from parsers.models import PlatformMethod
from pydantic import BaseModel, Field

# ─── Inputs ──────────────────────────────────────────────────────────────────


class GetPatternInput(BaseModel):
    """Input для kb.get_pattern."""

    pattern_id: str = Field(description="transaction-wrapper | posting-handler | ...")
    target_object_type: str | None = Field(
        default=None,
        description="Catalog | Document — фильтр по применимости",
    )


class GetAntipatternInput(BaseModel):
    """Input для kb.get_antipattern."""

    antipattern_id: str = Field(description="query-in-loop | try-catch-silent | ...")


class SearchKbInput(BaseModel):
    """Input для kb.search_kb."""

    query: str = Field(description="Текстовый запрос")
    top_k: int = Field(default=5, ge=1, le=20)
    category: Literal["pattern", "antipattern", "standard", "all"] = "all"


class CheckMethodAvailabilityInput(BaseModel):
    """Input для kb.check_method_availability."""

    method_name: str = Field(description="ЗаписьЖурналаРегистрации")
    target_context: str = Field(description="server | thin_client | mobile_client")
    platform_version: str = Field(description="8.3.20")


class CheckAntipatternsInput(BaseModel):
    """Input для kb.check_antipatterns."""

    code: str = Field(description="BSL-код для проверки")
    severity_filter: list[Literal["critical", "warning", "info"]] = Field(default=["critical", "warning"])
    category_filter: list[str] | None = None


# ─── Outputs ─────────────────────────────────────────────────────────────────


class GetPatternOutput(BaseModel):
    """Output для kb.get_pattern."""

    pattern_id: str
    title: str
    when_to_use: str
    code_template: str | None
    variables: list[dict[str, Any]]
    example_good: str


class GetAntipatternOutput(BaseModel):
    """Output для kb.get_antipattern."""

    antipattern_id: str
    title: str
    severity: Literal["critical", "warning", "info"]
    detect_method: str  # 'regex' | 'ast_pattern' | 'bsl_ls_rule'
    recommendation_for_llm: str
    example_bad: str
    example_good: str


class SearchKbOutput(BaseModel):
    """Output для kb.search_kb."""

    query: str
    results: list[dict[str, Any]] = Field(description="[{id, type, title, score}]")


class CheckMethodAvailabilityOutput(BaseModel):
    """Output для kb.check_method_availability."""

    method_name: str
    available: bool
    target_context: str
    reason: str | None = None
    platform_method: PlatformMethod | None = None


class CheckAntipatternsOutput(BaseModel):
    """Output для kb.check_antipatterns."""

    findings: list[dict[str, Any]] = Field(description="[{antipattern_id, severity, line, message}]")


class GetStandardInput(BaseModel):
    """Input для kb.get_standard (TD-S4.2-03)."""

    standard_id: str = Field(description="sto-6.1-no-tabs | bsp-find-by-name | ...")


class CheckStandardsInput(BaseModel):
    """Input для kb.check_standards (TD-S4.2-03)."""

    code: str = Field(description="BSL-код для проверки")
    severity_filter: list[Literal["critical", "warning", "info"]] = Field(
        default=["critical", "warning", "info"]
    )
    source_type_filter: list[Literal["СТО", "БСП", "1C-EDT", "internal"]] | None = None
    category_filter: list[str] | None = None


class GetStandardOutput(BaseModel):
    """Output для kb.get_standard (TD-S4.2-03)."""

    standard_id: str
    title: str
    source_type: str = Field(description="СТО | БСП | 1C-EDT | internal")
    source_code: str = Field(description="Например, '6.1' для СТО 6.1")
    source_url: str = ""
    severity: Literal["critical", "warning", "info"]
    detect_method: str  # 'regex' | 'ast_pattern' | 'bsl_ls_rule'
    description: str
    recommendation_for_llm: str
    example_bad: str
    example_good: str


class CheckStandardsOutput(BaseModel):
    """Output для kb.check_standards (TD-S4.2-03)."""

    findings: list[dict[str, Any]] = Field(
        description=(
            "[{standard_id, severity, source, line, message, match}] — "
            "source = {type: СТО|БСП, code: '6.1', url: ...}"
        )
    )


# ─── Tool contracts ──────────────────────────────────────────────────────────


class GetPattern:
    """kb.get_pattern — получить эталонный паттерн."""

    name: str = "kb.get_pattern"
    description: str = (
        "Получить эталонный паттерн из knowledge-base/patterns/. "
        "Используется Gather'ом для подачи примера в Coder. "
        "Пример: kb.get_pattern(pattern_id='posting-handler')"
    )
    input_schema: dict[str, Any] = GetPatternInput.model_json_schema()
    output_model: type[BaseModel] = GetPatternOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 5
    idempotent: bool = True
    required_role: str = "GATHERER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(
            "kb.get_pattern — контракт. Реализация в mcp_servers.kb.server.KbServer.get_pattern"
        )


class GetAntipattern:
    """kb.get_antipattern — получить описание антипаттерна."""

    name: str = "kb.get_antipattern"
    description: str = "Получить описание антипаттерна по id (для Reviewer'а)."
    input_schema: dict[str, Any] = GetAntipatternInput.model_json_schema()
    output_model: type[BaseModel] = GetAntipatternOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 5
    idempotent: bool = True
    required_role: str = "REVIEWER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(
            "kb.get_antipattern — контракт. Реализация в mcp_servers.kb.server.KbServer.get_antipattern"
        )


class SearchKb:
    """kb.search_kb — полнотекстовый поиск по базе знаний."""

    name: str = "kb.search_kb"
    description: str = "Полнотекстовый поиск по базе знаний (паттерны + антипаттерны + standards)."
    input_schema: dict[str, Any] = SearchKbInput.model_json_schema()
    output_model: type[BaseModel] = SearchKbOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 5
    idempotent: bool = True
    required_role: str = "PLANNER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(
            "kb.search_kb — контракт. Реализация в mcp_servers.kb.server.KbServer.search_kb"
        )


class CheckMethodAvailability:
    """kb.check_method_availability — проверить доступность метода платформы."""

    name: str = "kb.check_method_availability"
    description: str = (
        "Проверить доступность метода платформы в контексте. "
        "Пример: kb.check_method_availability(method_name='ЗаписьЖурналаРегистрации', "
        "target_context='thin_client', platform_version='8.3.20') → available=False"
    )
    input_schema: dict[str, Any] = CheckMethodAvailabilityInput.model_json_schema()
    output_model: type[BaseModel] = CheckMethodAvailabilityOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 5
    idempotent: bool = True
    required_role: str = "GATHERER"  # также VALIDATOR — см. MULTI_ROLE_OK

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(
            "kb.check_method_availability — контракт. "
            "Реализация в mcp_servers.kb.server.KbServer.check_method_availability "
            "(через platform-methods.db из .hbk, fallback на хардкод)"
        )


class CheckAntipatterns:
    """kb.check_antipatterns — проверить BSL-код на антипаттерны."""

    name: str = "kb.check_antipatterns"
    description: str = (
        "Проверить BSL-код на антипаттерны (regex/AST-правила из knowledge-base/antipatterns/). "
        "Используется Validator'ом и Reviewer'ом. "
        "Пример: kb.check_antipatterns(code='...')"
    )
    input_schema: dict[str, Any] = CheckAntipatternsInput.model_json_schema()
    output_model: type[BaseModel] = CheckAntipatternsOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 15
    idempotent: bool = True
    required_role: str = "VALIDATOR"  # также REVIEWER

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(
            "kb.check_antipatterns — контракт. Реализация в mcp_servers.kb.server.KbServer.check_antipatterns"
        )


class GetStandard:
    """kb.get_standard — получить стандарт 1С (СТО/БСП) по id (TD-S4.2-03)."""

    name: str = "kb.get_standard"
    description: str = (
        "Получить описание стандарта 1С (СТО или БСП) по id. "
        "Возвращает источник (its.1c.ru / БСП), описание, примеры bad/good, "
        "рекомендацию для LLM. Используется Reviewer'ом и Coder'ом. "
        "Пример: kb.get_standard(standard_id='sto-6.1-no-tabs')"
    )
    input_schema: dict[str, Any] = GetStandardInput.model_json_schema()
    output_model: type[BaseModel] = GetStandardOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 5
    idempotent: bool = True
    required_role: str = "REVIEWER"  # также CODER, GATHERER

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(
            "kb.get_standard — контракт. Реализация в mcp_servers.kb.server.KbServer.get_standard"
        )


class CheckStandards:
    """kb.check_standards — проверить BSL-код на соответствие стандартам 1С (TD-S4.2-03)."""

    name: str = "kb.check_standards"
    description: str = (
        "Проверить BSL-код на соответствие стандартам 1С (СТО + БСП) "
        "из knowledge-base/standards/. Возвращает findings с ссылкой на источник. "
        "Используется Validator'ом как 4-й параллельный валидатор. "
        "Пример: kb.check_standards(code='...', source_type_filter=['СТО'])"
    )
    input_schema: dict[str, Any] = CheckStandardsInput.model_json_schema()
    output_model: type[BaseModel] = CheckStandardsOutput
    error_contract: Literal["exception", "error_dict", "empty_result"] = "error_dict"
    timeout: int = 15
    idempotent: bool = True
    required_role: str = "VALIDATOR"  # также REVIEWER

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError(
            "kb.check_standards — контракт. Реализация в mcp_servers.kb.server.KbServer.check_standards"
        )


KB_TOOLS: list[type[Any]] = [
    GetPattern,
    GetAntipattern,
    SearchKb,
    CheckMethodAvailability,
    CheckAntipatterns,
    GetStandard,
    CheckStandards,
]
