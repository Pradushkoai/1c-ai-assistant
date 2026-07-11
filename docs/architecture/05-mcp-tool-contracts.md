# Шаг 5 — MCP tool contracts (5 серверов)

> **ADR-0010:** MCP tool contracts — двойной контракт (server обязуется, orchestrator вызывает)
> **Зависимости:** Шаг 2 (модели), Шаг 4 (GatherResult, ValidateResult формы)
> **Артефакт:** `packages/mcp_servers/src/mcp_servers/shared/protocol.py` + `contracts.py` для каждого сервера

## 1. Что фиксирует этот шаг

5 доменных MCP-серверов:
- `metadata-server` — метаданные 1С (XML-парсинг)
- `codebase-server` — BSL-код (semantic search, call graph)
- `kb-server` — база знаний (паттерны, антипаттерны, platform methods)
- `bsl_ls-server` — BSL Language Server (Java 17, 187 диагностик)
- `git-server` — git operations

Для каждого: список tools с `input_schema`, `output_model`, `error_contract`, `timeout`, `idempotent`.

## 2. Общий `ToolContract` Protocol

```python
# packages/mcp_servers/src/mcp_servers/shared/protocol.py
"""Общий Protocol для всех MCP tool contracts.

Каждый MCP-сервер реализует свои tools согласно этому Protocol.
Orchestrator (через ToolProvider, Шаг 6) вызывает tools, опираясь на контракт.
"""
from __future__ import annotations

from typing import Any, Protocol, Literal, Type, runtime_checkable
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
    - required_role: какая роль может вызывать (для TOOL_GROUPS, Шаг 6)
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    output_model: Type[BaseModel]
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
    """Базовая ошибка MCP tool. Расширяется в Шаге 9."""

    code: str = "TOOL_ERROR"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


def make_mcp_tool(contract_cls: Type[ToolContract]) -> Any:
    """Декоратор/фабрика: превратить ToolContract в mcp.types.Tool.

    Используется каждым MCP-сервером для регистрации в mcp.server.Server.
    """
    import mcp.types as types
    return types.Tool(
        name=contract_cls.name,
        description=contract_cls.description,
        inputSchema=contract_cls.input_schema,
    )
```

## 3. metadata-server — контракты

```python
# packages/mcp_servers/src/mcp_servers/metadata/contracts.py
"""metadata-server: метаданные 1С.

Источник: data/configs/{name}/{version}/ → unified-metadata-index.json
Парсер: parsers.xml
Рантайм: Python
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field
from parsers.models import (
    ObjectMetadata, CatalogMetadata, DocumentMetadata,
    CommonModuleMetadata, FormMetadata, DependencyEdge,
)
from ..shared.protocol import ToolContract


# ─── Inputs ──────────────────────────────────────────────────────────────────

class GetMetadataInput(BaseModel):
    object_ref: str = Field(description="Catalog.Контрагенты | Document.Реализация | CommonModule.ОбщегоНазначения")
    config_name: str
    config_version: str


class GetFormStructureInput(BaseModel):
    object_ref: str = Field(description="Catalog.Контрагенты")
    form_name: str = Field(description="ФормаСписка | ФормаЭлемента | ФормаВыбора")
    config_name: str
    config_version: str


class GetApiReferenceInput(BaseModel):
    module_name: str = Field(description="ОбщегоНазначения")
    config_name: str
    config_version: str


class GetDependencyGraphInput(BaseModel):
    config_name: str
    config_version: str
    object_ref: str | None = Field(default=None, description="Если None — весь граф")
    direction: Literal["depends_on", "depended_by"] = "depends_on"
    depth: int = Field(default=1, ge=1, le=5)


# ─── Outputs ─────────────────────────────────────────────────────────────────

class GetMetadataOutput(BaseModel):
    object_ref: str
    metadata: ObjectMetadata | CatalogMetadata | DocumentMetadata | CommonModuleMetadata


class GetFormStructureOutput(BaseModel):
    object_ref: str
    form_name: str
    form: FormMetadata


class GetApiReferenceOutput(BaseModel):
    module_name: str
    methods: list[dict[str, Any]] = Field(description="Экспортные методы с сигнатурами")


class GetDependencyGraphOutput(BaseModel):
    object_ref: str | None
    edges: list[DependencyEdge]
    stats: dict[str, Any]


# ─── Tool contracts ──────────────────────────────────────────────────────────

class GetMetadata(ToolContract):
    name = "metadata.get_metadata"
    description = (
        "Получить метаданные объекта 1С (Catalog, Document, CommonModule, ...). "
        "Возвращает: атрибуты, формы, шаблоны, команды. "
        "Пример: metadata.get_metadata(object_ref='Catalog.Контрагенты', "
        "config_name='ut11', config_version='4.5.3')"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "object_ref": {"type": "string", "description": "Catalog.Контрагенты"},
            "config_name": {"type": "string"},
            "config_version": {"type": "string"},
        },
        "required": ["object_ref", "config_name", "config_version"],
    }
    output_model = GetMetadataOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 30
    idempotent = True
    required_role = "GATHERER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...  # реализация в server.py


class GetFormStructure(ToolContract):
    name = "metadata.get_form_structure"
    description = (
        "Получить структуру управляемой формы: элементы, дата-пути, события, реквизиты. "
        "Пример: metadata.get_form_structure(object_ref='Catalog.Контрагенты', "
        "form_name='ФормаЭлемента', config_name='ut11', config_version='4.5.3')"
    )
    input_schema = GetFormStructureInput.model_json_schema()
    output_model = GetFormStructureOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 30
    idempotent = True
    required_role = "GATHERER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


class GetApiReference(ToolContract):
    name = "metadata.get_api_reference"
    description = (
        "API-справочник общего модуля: список экспортных методов с сигнатурами. "
        "Пример: metadata.get_api_reference(module_name='ОбщегоНазначения', "
        "config_name='ut11', config_version='4.5.3')"
    )
    input_schema = GetApiReferenceInput.model_json_schema()
    output_model = GetApiReferenceOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 30
    idempotent = True
    required_role = "GATHERER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


class GetDependencyGraph(ToolContract):
    name = "metadata.get_dependency_graph"
    description = (
        "Граф зависимостей метаданных: кто на кого ссылается. "
        "Используется Planner'ом для структурного анализа. "
        "Пример: metadata.get_dependency_graph(config_name='ut11', "
        "config_version='4.5.3', object_ref='Catalog.Контрагенты', depth=2)"
    )
    input_schema = GetDependencyGraphInput.model_json_schema()
    output_model = GetDependencyGraphOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 30
    idempotent = True
    required_role = "PLANNER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


# Реестр tools metadata-server'а
METADATA_TOOLS: list[type[ToolContract]] = [
    GetMetadata,
    GetFormStructure,
    GetApiReference,
    GetDependencyGraph,
]
```

## 4. codebase-server — контракты

```python
# packages/mcp_servers/src/mcp_servers/codebase/contracts.py
"""codebase-server: BSL-код конфигурации.

Источник: data/configs/{name}/{version}/*.bsl → Qdrant embeddings + call-graph.json
Парсер: parsers.bsl
Рантайм: Python + Qdrant (Docker)
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field
from parsers.models import BslModule, CallEdge
from ..shared.protocol import ToolContract


# ─── Inputs ──────────────────────────────────────────────────────────────────

class SemanticSearchInput(BaseModel):
    query: str = Field(description="ОбработкаПроведения, регистрация движений, ...")
    config_name: str
    config_version: str
    top_k: int = Field(default=5, ge=1, le=20)
    filters: dict[str, Any] | None = Field(
        default=None,
        description="{'module_kind': 'ObjectModule', 'object_type': 'Document'}"
    )


class GetModuleInput(BaseModel):
    object_ref: str = Field(description="CommonModule.ОбщегоНазначения")
    module_kind: str = Field(default="ObjectModule", description="ObjectModule | ManagerModule | FormModule | CommonModule")
    config_name: str
    config_version: str


class GetSimilarInput(BaseModel):
    object_ref: str = Field(description="Найти похожие на этот модуль")
    config_name: str
    config_version: str
    top_k: int = Field(default=5, ge=1, le=20)


class CallGraphInput(BaseModel):
    config_name: str
    config_version: str
    object_ref: str | None = Field(default=None, description="Подграф для объекта")
    method_name: str | None = Field(default=None, description="Только вызовы из этого метода")


# ─── Outputs ─────────────────────────────────────────────────────────────────

class SemanticSearchOutput(BaseModel):
    query: str
    results: list[dict[str, Any]] = Field(
        description="[{module, score, snippet, object_ref}]"
    )


class GetModuleOutput(BaseModel):
    module: BslModule


class GetSimilarOutput(BaseModel):
    object_ref: str
    similar: list[dict[str, Any]] = Field(description="[{module, score}]")


class CallGraphOutput(BaseModel):
    object_ref: str | None
    edges: list[CallEdge]
    stats: dict[str, Any]


# ─── Tool contracts ──────────────────────────────────────────────────────────

class SemanticSearch(ToolContract):
    name = "codebase.semantic_search"
    description = (
        "Гибридный поиск (BM25 + vector) по BSL-кодам конфигурации. "
        "Возвращает top-K релевантных модулей со сниппетами. "
        "Пример: codebase.semantic_search(query='ОбработкаПроведения', "
        "config_name='ut11', config_version='4.5.3')"
    )
    input_schema = SemanticSearchInput.model_json_schema()
    output_model = SemanticSearchOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 10  # Qdrant быстрый, но fallback BM25 — дольше
    idempotent = True
    required_role = "GATHERER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


class GetModule(ToolContract):
    name = "codebase.get_module"
    description = "Получить полный BslModule (с методами, регионами, AST)."
    input_schema = GetModuleInput.model_json_schema()
    output_model = GetModuleOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 10
    idempotent = True
    required_role = "GATHERER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


class GetSimilar(ToolContract):
    name = "codebase.get_similar"
    description = "Найти модули, похожие на заданный (через embeddings)."
    input_schema = GetSimilarInput.model_json_schema()
    output_model = GetSimilarOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 10
    idempotent = True
    required_role = "REVIEWER"  # Reviewer смотрит похожие — может, есть pattern

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


class CallGraph(ToolContract):
    name = "codebase.call_graph"
    description = (
        "Граф вызовов BSL-методов. "
        "Используется для анализа: что вызывает данный метод, кто вызывает его."
    )
    input_schema = CallGraphInput.model_json_schema()
    output_model = CallGraphOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 15
    idempotent = True
    required_role = "GATHERER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


CODEBASE_TOOLS: list[type[ToolContract]] = [
    SemanticSearch,
    GetModule,
    GetSimilar,
    CallGraph,
]
```

## 5. kb-server — контракты

```python
# packages/mcp_servers/src/mcp_servers/kb/contracts.py
"""kb-server: база знаний + platform methods.

Источник 1: knowledge-base/{patterns,antipatterns}/*.yaml
Источник 2: derived/platform/{version}/platform-methods.db (SQLite из .hbk)
Парсер: parsers.hbk + YAML loader
Рантайм: Python
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field
from parsers.models import PlatformMethod
from ..shared.protocol import ToolContract


# ─── Inputs ──────────────────────────────────────────────────────────────────

class GetPatternInput(BaseModel):
    pattern_id: str = Field(description="transaction-wrapper | posting-handler | ...")
    target_object_type: str | None = Field(
        default=None,
        description="Catalog | Document — фильтр по применимости"
    )


class GetAntipatternInput(BaseModel):
    antipattern_id: str = Field(description="query-in-loop | try-catch-silent | ...")


class SearchKbInput(BaseModel):
    query: str = Field(description="Текстовый запрос")
    top_k: int = Field(default=5, ge=1, le=20)
    category: Literal["pattern", "antipattern", "standard", "all"] = "all"


class CheckMethodAvailabilityInput(BaseModel):
    method_name: str = Field(description="ЗаписьЖурналаРегистрации")
    target_context: str = Field(description="server | thin_client | mobile_client")
    platform_version: str = Field(description="8.3.20")


class CheckAntipatternsInput(BaseModel):
    code: str = Field(description="BSL-код для проверки")
    severity_filter: list[Literal["critical", "warning", "info"]] = Field(
        default=["critical", "warning"]
    )
    category_filter: list[str] | None = None


# ─── Outputs ─────────────────────────────────────────────────────────────────

class GetPatternOutput(BaseModel):
    pattern_id: str
    title: str
    when_to_use: str
    code_template: str | None
    variables: list[str]
    example_good: str


class GetAntipatternOutput(BaseModel):
    antipattern_id: str
    title: str
    severity: Literal["critical", "warning", "info"]
    detect_method: str  # 'regex' | 'ast_pattern' | 'bsl_ls_rule'
    recommendation_for_llm: str
    example_bad: str
    example_good: str


class SearchKbOutput(BaseModel):
    query: str
    results: list[dict[str, Any]] = Field(description="[{id, type, title, score}]")


class CheckMethodAvailabilityOutput(BaseModel):
    method_name: str
    available: bool
    target_context: str
    reason: str | None = None
    platform_method: PlatformMethod | None = None


class CheckAntipatternsOutput(BaseModel):
    findings: list[dict[str, Any]] = Field(
        description="[{antipattern_id, severity, line, message}]"
    )


# ─── Tool contracts ──────────────────────────────────────────────────────────

class GetPattern(ToolContract):
    name = "kb.get_pattern"
    description = (
        "Получить эталонный паттерн из knowledge-base/patterns/. "
        "Используется Gather'ом для подачи примера в Coder. "
        "Пример: kb.get_pattern(pattern_id='posting-handler')"
    )
    input_schema = GetPatternInput.model_json_schema()
    output_model = GetPatternOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 5
    idempotent = True
    required_role = "GATHERER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


class GetAntipattern(ToolContract):
    name = "kb.get_antipattern"
    description = "Получить описание антипаттерна по id (для Reviewer'а)."
    input_schema = GetAntipatternInput.model_json_schema()
    output_model = GetAntipatternOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 5
    idempotent = True
    required_role = "REVIEWER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


class SearchKb(ToolContract):
    name = "kb.search_kb"
    description = "Полнотекстовый поиск по базе знаний (паттерны + антипаттерны + standards)."
    input_schema = SearchKbInput.model_json_schema()
    output_model = SearchKbOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 5
    idempotent = True
    required_role = "PLANNER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


class CheckMethodAvailability(ToolContract):
    name = "kb.check_method_availability"
    description = (
        "Проверить доступность метода платформы в контексте. "
        "Пример: kb.check_method_availability(method_name='ЗаписьЖурналаРегистрации', "
        "target_context='thin_client', platform_version='8.3.20') → available=False"
    )
    input_schema = CheckMethodAvailabilityInput.model_json_schema()
    output_model = CheckMethodAvailabilityOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 5
    idempotent = True
    required_role = "GATHERER"  # также VALIDATOR — см. MULTI_ROLE_OK в Шаге 6

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


class CheckAntipatterns(ToolContract):
    name = "kb.check_antipatterns"
    description = (
        "Проверить BSL-код на антипаттерны (regex/AST-правила из knowledge-base/antipatterns/). "
        "Используется Validator'ом и Reviewer'ом. "
        "Пример: kb.check_antipatterns(code='...')"
    )
    input_schema = CheckAntipatternsInput.model_json_schema()
    output_model = CheckAntipatternsOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 15
    idempotent = True
    required_role = "VALIDATOR"  # также REVIEWER

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


KB_TOOLS: list[type[ToolContract]] = [
    GetPattern,
    GetAntipattern,
    SearchKb,
    CheckMethodAvailability,
    CheckAntipatterns,
]
```

## 6. bsl_ls-server — контракты

```python
# packages/mcp_servers/src/mcp_servers/bsl_ls/contracts.py
"""bsl_ls-server: BSL Language Server (Java 17).

Источник: 1c-syntax/bsl-language-server (Docker image с sha256)
Рантайм: Java 17 subprocess
Stateless: каждый вызов — новый subprocess
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field
from ..shared.protocol import ToolContract


class LintInput(BaseModel):
    code: str = Field(description="BSL-код")
    file_path: str = Field(default="/tmp/module.bsl", description="Виртуальный путь (для диагностик)")
    rules: list[str] | None = Field(
        default=None,
        description="Subset правил. None = все 187 диагностик."
    )
    baseline_path: str | None = Field(
        default=None,
        description="Путь к baseline.json — известные ошибки, которые исключаются"
    )


class FormatInput(BaseModel):
    code: str
    style: Literal["1c", "bsp"] = "1c"


class LintOutput(BaseModel):
    total: int
    by_code: dict[str, int] = Field(description="{'BSL-WS-001': 3, 'BSL-NAMESPACE-001': 1}")
    diagnostics: list[dict[str, Any]] = Field(
        description="[{code, severity, line, column, message}]"
    )


class FormatOutput(BaseModel):
    formatted_code: str
    changes_made: bool


class Lint(ToolContract):
    name = "bsl_ls.lint"
    description = (
        "Запуск BSL Language Server (187 диагностик). "
        "ВЫЗЫВАЕТСЯ ВАЛИДАТОРОМ — это главный детерминированный gate. "
        "Timeout: 60 сек. Пример: bsl_ls.lint(code='...')"
    )
    input_schema = LintInput.model_json_schema()
    output_model = LintOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 60  # Java startup + анализ
    idempotent = True
    required_role = "VALIDATOR"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        # subprocess.run(["java", "-jar", BSL_LS_JAR, "analyze", ...], timeout=60)
        ...


class Format(ToolContract):
    name = "bsl_ls.format"
    description = "Форматирование BSL-кода (1C или BSP style)."
    input_schema = FormatInput.model_json_schema()
    output_model = FormatOutput
    error_contract: Literal["error_dict"] = "error_dict"
    timeout = 30
    idempotent = True
    required_role = "VALIDATOR"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


BSL_LS_TOOLS: list[type[ToolContract]] = [Lint, Format]
```

## 7. git-server — контракты

```python
# packages/mcp_servers/src/mcp_servers/git/contracts.py
"""git-server: git operations.

Рантайм: Python + git CLI (subprocess)
Stateless
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field
from ..shared.protocol import ToolContract


class CreateBranchInput(BaseModel):
    repo_path: str
    branch_name: str = Field(description="feature/add-posting-handler-для-реализации")


class CommitInput(BaseModel):
    repo_path: str
    message: str = Field(description="feat(Реализация): add posting handler")
    files: list[str] = Field(description="Пути относительно repo_path")
    branch: str | None = None  # None = current


class OpenPrInput(BaseModel):
    repo_path: str
    branch: str
    title: str
    body: str
    base: str = "main"
    labels: list[str] = Field(default_factory=list)


class DiffInput(BaseModel):
    repo_path: str
    branch_a: str
    branch_b: str
    paths: list[str] | None = None


class CreateBranchOutput(BaseModel):
    branch_name: str
    base: str


class CommitOutput(BaseModel):
    commit_sha: str
    files_changed: list[str]


class OpenPrOutput(BaseModel):
    pr_number: int
    pr_url: str
    branch: str


class DiffOutput(BaseModel):
    diff: str
    stats: dict[str, int]


class CreateBranch(ToolContract):
    name = "git.create_branch"
    description = "Создать ветку в репозитории."
    input_schema = CreateBranchInput.model_json_schema()
    output_model = CreateBranchOutput
    error_contract: Literal["exception"] = "exception"
    timeout = 10
    idempotent = False
    required_role = "COMMITTER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


class Commit(ToolContract):
    name = "git.commit"
    description = "Закоммитить файлы в текущей (или указанной) ветке."
    input_schema = CommitInput.model_json_schema()
    output_model = CommitOutput
    error_contract: Literal["exception"] = "exception"
    timeout = 15
    idempotent = False
    required_role = "COMMITTER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


class OpenPr(ToolContract):
    name = "git.open_pr"
    description = "Открыть Pull Request через `gh` CLI."
    input_schema = OpenPrInput.model_json_schema()
    output_model = OpenPrOutput
    error_contract: Literal["exception"] = "exception"
    timeout = 30
    idempotent = False
    required_role = "COMMITTER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


class Diff(ToolContract):
    name = "git.diff"
    description = "Получить diff между двумя ветками."
    input_schema = DiffInput.model_json_schema()
    output_model = DiffOutput
    error_contract: Literal["exception"] = "exception"
    timeout = 10
    idempotent = True
    required_role = "COMMITTER"

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        ...


GIT_TOOLS: list[type[ToolContract]] = [CreateBranch, Commit, OpenPr, Diff]
```

## 8. Сводная таблица всех MCP tools

| Сервер | Tool | Роль | Timeout | Idempotent |
|---|---|---|---|---|
| metadata | `metadata.get_metadata` | GATHERER | 30s | ✅ |
| metadata | `metadata.get_form_structure` | GATHERER | 30s | ✅ |
| metadata | `metadata.get_api_reference` | GATHERER | 30s | ✅ |
| metadata | `metadata.get_dependency_graph` | PLANNER | 30s | ✅ |
| codebase | `codebase.semantic_search` | GATHERER | 10s | ✅ |
| codebase | `codebase.get_module` | GATHERER | 10s | ✅ |
| codebase | `codebase.get_similar` | REVIEWER | 10s | ✅ |
| codebase | `codebase.call_graph` | GATHERER | 15s | ✅ |
| kb | `kb.get_pattern` | GATHERER | 5s | ✅ |
| kb | `kb.get_antipattern` | REVIEWER | 5s | ✅ |
| kb | `kb.search_kb` | PLANNER | 5s | ✅ |
| kb | `kb.check_method_availability` | GATHERER + VALIDATOR | 5s | ✅ |
| kb | `kb.check_antipatterns` | VALIDATOR + REVIEWER | 15s | ✅ |
| bsl_ls | `bsl_ls.lint` | VALIDATOR | 60s | ✅ |
| bsl_ls | `bsl_ls.format` | VALIDATOR | 30s | ✅ |
| git | `git.create_branch` | COMMITTER | 10s | ❌ |
| git | `git.commit` | COMMITTER | 15s | ❌ |
| git | `git.open_pr` | COMMITTER | 30s | ❌ |
| git | `git.diff` | COMMITTER | 10s | ✅ |

**Итого: 19 tools в 5 серверах.**

## 9. Error contract — единый формат

Все tools возвращают ошибки по одному из 3 контрактов:

```python
# Error dict (для большинства tools):
{
    "error": "Configuration 'ut11' not found",
    "code": "CONFIG_NOT_FOUND",
    "details": {"config_name": "ut11"}
}

# Exception (для git-server, где ошибки редки, но критичны):
raise ToolError("git commit failed: ...", code="GIT_COMMIT_FAILED")

# Empty result (для search tools):
{"results": [], "query": "..."}
```

Шаг 9 определяет полный taxonomy кодов ошибок.

## 10. Snapshot-тесты контрактов

Каждый контракт замораживается в snapshot:

```python
# tests/snapshots/test_mcp_contracts.py
import pytest
from mcp_servers.metadata.contracts import METADATA_TOOLS
from mcp_servers.codebase.contracts import CODEBASE_TOOLS
from mcp_servers.kb.contracts import KB_TOOLS
from mcp_servers.bsl_ls.contracts import BSL_LS_TOOLS
from mcp_servers.git.contracts import GIT_TOOLS

ALL_TOOLS = METADATA_TOOLS + CODEBASE_TOOLS + KB_TOOLS + BSL_LS_TOOLS + GIT_TOOLS


def test_tool_names_unique():
    names = [t.name for t in ALL_TOOLS]
    assert len(names) == len(set(names)), f"Duplicate tool names: {names}"


def test_tool_names_follow_convention():
    """Все имена вида '{server}.{action}'."""
    for tool in ALL_TOOLS:
        assert "." in tool.name, f"Invalid tool name: {tool.name}"
        server, action = tool.name.split(".", 1)
        assert server in {"metadata", "codebase", "kb", "bsl_ls", "git"}
        assert action.islower()


def test_all_tools_have_required_attributes():
    for tool in ALL_TOOLS:
        assert hasattr(tool, "name")
        assert hasattr(tool, "description")
        assert hasattr(tool, "input_schema")
        assert hasattr(tool, "output_model")
        assert hasattr(tool, "error_contract")
        assert hasattr(tool, "timeout")
        assert hasattr(tool, "idempotent")
        assert hasattr(tool, "required_role")


def test_input_schema_is_valid_json_schema():
    """Все input_schema — валидные JSON Schemas."""
    import jsonschema
    from jsonschema.validators import Draft7Validator
    for tool in ALL_TOOLS:
        Draft7Validator.check_schema(tool.input_schema)  # raise если invalid


def test_snapshot_tool_names(snapshot):
    """Freeze состава tools — любое изменение требует --snapshot-update."""
    all_names = sorted(t.name for t in ALL_TOOLS)
    snapshot.assert_match("\n".join(all_names), "tool_names.txt")


def test_snapshot_tool_descriptions(snapshot):
    """Freeze описаний — для отслеживания изменений в LLM-facing текстах."""
    for tool in ALL_TOOLS:
        snapshot.assert_match(tool.description, f"{tool.name}.description.txt")
```

## 11. Взаимосвязь с другими шагами

| Шаг | Связь |
|---|---|
| Шаг 4 (Pipeline contracts) | `GatheredMetadata`, `GatheredCode`, `GatheredKnowledge` — формы результатов MCP tools |
| Шаг 6 (TOOL_GROUPS) | `required_role` каждого tool → маппинг в `TOOL_GROUPS` |
| Шаг 7 (KB-as-code) | `kb.check_antipatterns` парсит YAML из KB — формат фиксируется в шаге 7 |
| Шаг 8 (Facade) | `run_cli` proxy проверяет `required_role` перед вызовом скрытых tools |
| Шаг 9 (Error taxonomy) | `error_contract` и `code` поля — из таксономии ошибок |

---

**Шаг 5 завершён.** Следующий — Шаг 6: `TOOL_GROUPS` registry — маппинг `AgentRole → MCPServer → frozenset(tool_names)`, который собирает все 19 tools в декларативную таблицу.
