"""Handlers для 8 lifecycle tools Facade'а (TD-S5-02, ADR-0013).

Каждый handler:
1. Валидирует input через Pydantic Input-контракт.
2. Загружает/создаёт state (in-memory dict по plan_id; тип state — Any,
   в production это TaskState из orchestrator, но facade не импортирует
   orchestrator — DI через конструктор: ``state_factory`` + ``node_*`` callables).
3. Вызывает соответствующий node callable (DI).
4. Применяет обновление: ``state.model_copy(update=node_result)``.
5. Сохраняет state в in-memory dict.
6. Формирует Output через Pydantic Output-контракт + ``next_action`` builder.

Архитектурное правило (CONCEPTUAL.md §1.1, ADR-0002): ``mcp_servers`` НЕ импортирует
``orchestrator``. Node callables и state_factory инжектируются agent-слоем
(см. ``agent/cli_commands/facade_entry.py``).

State management: in-memory dict (достаточно для MCP stdio server, один процесс).
Для production survival-restart — отдельный TD (hooks в checkpointer.aput/aget_tuple
через PersistenceManager, фундамент TD-S5-01 готов).

См. ADR-0013 (Agent-Facade — 7 lifecycle tools + data_status), ADR-0010 (MCP tool
contracts), ADR-0009 (pipeline contracts), ADR-0003 (MCP-архитектура).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from .contracts import (
    DataStatusOutput,
    ExplainInput,
    ExplainOutput,
    GatherInput,
    GatherOutput,
    GenerateInput,
    GenerateOutput,
    PlanInput,
    PlanOutput,
    ReviewInput,
    ReviewOutput,
    RunCliInput,
    RunCliOutput,
    ValidateInput,
    ValidateOutput,
)
from .next_action import (
    after_gather,
    after_generate,
    after_plan,
    after_review,
    after_validate,
)

log = logging.getLogger(__name__)

# ─── helpers ─────────────────────────────────────────────────────────────────

# Валидация plan_id: UUID-подобная строка (безопасная для ключа state dict).
_PLAN_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")


def _validate_plan_id(plan_id: str) -> None:
    """Валидация plan_id — защита от инъекций в in-memory dict key."""
    if not plan_id or not _PLAN_ID_RE.match(plan_id):
        raise ValueError(
            f"Invalid plan_id: {plan_id!r}. Expected alphanumeric/underscore/hyphen, <=128 chars."
        )


# Type aliases для DI (не импортируем orchestrator — см. CONCEPTUAL.md §1.1).
StateFactory = Callable[..., Any]  # state_factory(task_id, description, config_name, ...) -> state
NodeCallable = Callable[..., Any]  # async (state, **di_kwargs) -> dict[str, Any]


class FacadeNotConfiguredError(RuntimeError):
    """Raised when a handler is called without required DI dependency."""


# ─── FacadeHandlers ──────────────────────────────────────────────────────────


class FacadeHandlers:
    """Все 8 lifecycle handlers в одном классе.

    DI через конструктор (CONCEPTUAL.md §1.1: mcp_servers НЕ импортирует
    orchestrator — node callables и state_factory инжектируются agent-слоем).

    Args:
        state_factory: ``Callable[..., state]`` для создания нового state
            (в production — ``TaskState``). Параметры: task_id, description,
            config_name, config_version, platform_version, fsm_state.
        node_plan: async callable ``plan_node(state, llm=...)``.
        node_gather: async callable ``gather_node(state, kb_server=...)``.
        node_code: async callable ``code_node(state, llm=...)``.
        node_validate: async callable ``validate_node(state, bsl_ls_server=..., kb_server=...)``.
        node_review: async callable ``review_node(state, llm=..., kb_server=...)``.
        node_commit: async callable ``commit_node(state)``.
        state_store: ``FacadeStateStore`` для persistence (survival-restart, TD-S7-01).
            Если None — in-memory fallback (state не переживает restart процесса).
        kb_server: KbServer инстанс (для gather, validate, review, explain, run_cli).
        bsl_ls_server: BslLsServer инстанс (для validate, run_cli).
        llm: LLM инстанс (для plan, generate, review).
        path_manager: PathManager (для data_status).
        config_registry: ConfigRegistry (для data_status).
    """

    def __init__(
        self,
        state_factory: StateFactory | None = None,
        node_plan: NodeCallable | None = None,
        node_gather: NodeCallable | None = None,
        node_code: NodeCallable | None = None,
        node_validate: NodeCallable | None = None,
        node_review: NodeCallable | None = None,
        node_commit: NodeCallable | None = None,
        state_store: Any = None,
        kb_server: Any = None,
        bsl_ls_server: Any = None,
        metadata_server: Any = None,
        git_server: Any = None,
        repo_path: Any = None,
        llm: Any = None,
        path_manager: Any = None,
        config_registry: Any = None,
    ) -> None:
        self.state_factory = state_factory
        self.node_plan = node_plan
        self.node_gather = node_gather
        self.node_code = node_code
        self.node_validate = node_validate
        self.node_review = node_review
        self.node_commit = node_commit
        # State store (TD-S7-01): FacadeStateStore или None (in-memory fallback).
        from .state_store import FacadeStateStore

        self._state_store = state_store or FacadeStateStore()
        self.kb_server = kb_server
        self.bsl_ls_server = bsl_ls_server
        self.metadata_server = metadata_server
        self.git_server = git_server
        self.repo_path = repo_path
        self.llm = llm
        self.path_manager = path_manager
        self.config_registry = config_registry
        # In-memory cache: subtask_id → plan_id (для handle_validate/review).
        # После restart cache пустой — клиент должен начать с plan (MVP-ограничение).
        self._subtask_to_plan: dict[str, str] = {}

    # ─── state helpers ──────────────────────────────────────────────────────

    async def _get_state(self, plan_id: str) -> Any:
        """Загрузить state по plan_id. Raises KeyError если нет."""
        _validate_plan_id(plan_id)
        state = await self._state_store.load_state(plan_id)
        if state is None:
            raise KeyError(f"plan_id={plan_id!r} not found. Call 'plan' first.")
        return state

    async def _save_state(self, plan_id: str, state: Any) -> None:
        """Сохранить state по plan_id."""
        _validate_plan_id(plan_id)
        await self._state_store.save_state(plan_id, state)
        # Обновляем subtask→plan cache для handle_validate/review.
        for subtask in getattr(state, "subtasks", []) or []:
            subtask_id = getattr(subtask, "id", None)
            if subtask_id:
                self._subtask_to_plan[subtask_id] = plan_id

    def _require(self, attr: str, name: str) -> Any:
        """Проверить, что DI dependency задана. Raises FacadeNotConfiguredError."""
        val = getattr(self, attr)
        if val is None:
            raise FacadeNotConfiguredError(
                f"{name} not configured. Pass it to FacadeHandlers(...) constructor."
            )
        return val

    # ─── 1. plan ────────────────────────────────────────────────────────────

    async def handle_plan(self, args: dict[str, Any]) -> dict[str, Any]:
        """plan — декомпозиция задачи на подзадачи через LLM Planner.

        Создаёт новый state, вызывает ``node_plan``, сохраняет state,
        возвращает ``PlanOutput`` с ``next_action=gather``.
        """
        log.info("facade_plan_start: task=%s", args.get("task", "")[:100])
        parsed = PlanInput.model_validate(args)

        state_factory = self._require("state_factory", "state_factory")
        node_plan = self._require("node_plan", "node_plan")

        from uuid import uuid4

        plan_id = f"plan-{uuid4().hex[:12]}"
        state = state_factory(
            task_id=plan_id,
            description=parsed.task,
            config_name=parsed.config_name,
            config_version=parsed.config_version,
            platform_version=parsed.platform_version,
            fsm_state="planning",
        )

        update = await node_plan(state, llm=self.llm, metadata_server=self.metadata_server)
        state = state.model_copy(update=update)
        await self._save_state(plan_id, state)

        subtasks = state.subtasks
        first_subtask_id = subtasks[0].id if subtasks else None
        next_action = after_plan(plan_id, first_subtask_id)

        return PlanOutput(
            plan_id=plan_id,
            subtasks=[s.model_dump() for s in subtasks],
            decomposition_strategy=str(state.plan_result.get("strategy", "single")) if state.plan_result else "single",
            rationale=str(state.plan_result.get("rationale", "")) if state.plan_result else "",
            next_action=next_action,
            artifact_id=plan_id,
        ).model_dump()

    # ─── 2. gather ──────────────────────────────────────────────────────────

    async def handle_gather(self, args: dict[str, Any]) -> dict[str, Any]:
        """gather — сбор контекста для подзадачи (metadata + codebase + kb)."""
        parsed = GatherInput.model_validate(args)
        log.info("facade_gather_start: plan_id=%s subtask_id=%s", parsed.plan_id, parsed.subtask_id)

        node_gather = self._require("node_gather", "node_gather")
        state = await self._get_state(parsed.plan_id)
        idx = _find_subtask_idx(state, parsed.subtask_id)
        if idx is None:
            raise KeyError(f"subtask_id={parsed.subtask_id!r} not found in plan {parsed.plan_id!r}")
        if idx != state.current_subtask_idx:
            state = state.model_copy(update={"current_subtask_idx": idx})

        update = await node_gather(state, kb_server=self.kb_server, metadata_server=self.metadata_server)
        state = state.model_copy(update=update)
        await self._save_state(parsed.plan_id, state)

        gather_result = state.gather_result or {}
        next_action = after_gather(parsed.plan_id, parsed.subtask_id)

        return GatherOutput(
            subtask_id=parsed.subtask_id,
            context_summary=str(gather_result.get("context_summary", "")),
            patterns_applied=list(gather_result.get("patterns_applied", [])),
            mcp_calls_made=list(gather_result.get("mcp_calls_made", [])),
            next_action=next_action,
            artifact_id=f"{parsed.plan_id}#{parsed.subtask_id}",
        ).model_dump()

    # ─── 3. generate ────────────────────────────────────────────────────────

    async def handle_generate(self, args: dict[str, Any]) -> dict[str, Any]:
        """generate — LLM генерация BSL-кода через Coder (без MCP tools)."""
        parsed = GenerateInput.model_validate(args)
        log.info(
            "facade_generate_start: plan_id=%s subtask_id=%s iteration=%s",
            parsed.plan_id,
            parsed.subtask_id,
            parsed.iteration,
        )

        node_code = self._require("node_code", "node_code")
        state = await self._get_state(parsed.plan_id)
        idx = _find_subtask_idx(state, parsed.subtask_id)
        if idx is None:
            raise KeyError(f"subtask_id={parsed.subtask_id!r} not found in plan {parsed.plan_id!r}")
        if idx != state.current_subtask_idx:
            state = state.model_copy(update={"current_subtask_idx": idx})

        update = await node_code(state, llm=self.llm)
        state = state.model_copy(update=update)
        await self._save_state(parsed.plan_id, state)

        current_iteration = state.iterations[-1] if state.iterations else None
        if current_iteration is None:
            raise RuntimeError("code_node did not produce an iteration")

        next_action = after_generate(parsed.plan_id, parsed.subtask_id, current_iteration.number)
        artifact_id = f"{parsed.subtask_id}#{current_iteration.number}"

        return GenerateOutput(
            subtask_id=parsed.subtask_id,
            iteration=current_iteration.number,
            code=current_iteration.code,
            explanation=str(current_iteration.llm_response.get("explanation", "")),
            patterns_applied=list(current_iteration.llm_response.get("patterns_applied", [])),
            next_action=next_action,
            artifact_id=artifact_id,
        ).model_dump()

    # ─── 4. validate ────────────────────────────────────────────────────────

    async def handle_validate(self, args: dict[str, Any]) -> dict[str, Any]:
        """validate — BSL LS + KB антипаттерны (4 параллельных валидатора)."""
        parsed = ValidateInput.model_validate(args)
        log.info("facade_validate_start: artifact_id=%s", parsed.artifact_id)

        node_validate = self._require("node_validate", "node_validate")
        subtask_id, iteration_num = _parse_artifact_id(parsed.artifact_id)
        plan_id = self._subtask_to_plan.get(subtask_id)
        if plan_id is None:
            raise KeyError(
                f"subtask_id={subtask_id!r} not in cache. "
                "After restart, call 'plan' first to populate cache, or pass plan_id explicitly."
            )

        state = await self._get_state(plan_id)

        update = await node_validate(
            state,
            bsl_ls_server=self.bsl_ls_server,
            kb_server=self.kb_server,
        )
        state = state.model_copy(update=update)
        await self._save_state(plan_id, state)

        validate_result = state.validate_result or {}
        passed = bool(state.validation_passed)
        next_action = after_validate(plan_id, subtask_id, iteration_num, passed)

        return ValidateOutput(
            artifact_id=parsed.artifact_id,
            passed=passed,
            findings=list(validate_result.get("findings", [])),
            severity_breakdown=dict(validate_result.get("severity_breakdown", {})),
            failed_checks=list(validate_result.get("failed_checks", [])),
            next_action=next_action,
        ).model_dump()

    # ─── 5. review ──────────────────────────────────────────────────────────

    async def handle_review(self, args: dict[str, Any]) -> dict[str, Any]:
        """review — LLM-рецензент: proceed/retry/escalate.

        При ``proceed`` дополнительно вызывает ``node_commit`` (ADR-0013:
        «при proceed — открывается PR»).
        """
        parsed = ReviewInput.model_validate(args)
        log.info("facade_review_start: artifact_id=%s", parsed.artifact_id)

        node_review = self._require("node_review", "node_review")
        subtask_id, iteration_num = _parse_artifact_id(parsed.artifact_id)
        plan_id = self._subtask_to_plan.get(subtask_id)
        if plan_id is None:
            raise KeyError(
                f"subtask_id={subtask_id!r} not in cache. "
                "After restart, call 'plan' first to populate cache, or pass plan_id explicitly."
            )

        state = await self._get_state(plan_id)

        update = await node_review(state, llm=self.llm, kb_server=self.kb_server)
        state = state.model_copy(update=update)

        decision = "proceed"
        if state.review_result:
            decision = str(state.review_result.get("decision", "proceed"))
        pr_url: str | None = None

        # При proceed — вызываем node_commit (review → commit в одном tool).
        if decision == "proceed":
            node_commit = self._require("node_commit", "node_commit")
            commit_update = await node_commit(state, git_server=self.git_server, repo_path=self.repo_path)
            state = state.model_copy(update=commit_update)
            if state.commit_result and state.commit_result.get("files_changed"):
                pr_url = state.commit_result.get("pr_url")

        await self._save_state(plan_id, state)

        # Следующая подзадача (если есть).
        next_subtask_id: str | None = None
        if decision == "proceed":
            next_idx = state.current_subtask_idx + 1
            if next_idx < len(state.subtasks):
                next_subtask_id = state.subtasks[next_idx].id

        next_action = after_review(
            plan_id=plan_id,
            subtask_id=subtask_id,
            iteration=iteration_num,
            decision=decision,
            next_subtask_id=next_subtask_id,
        )

        return ReviewOutput(
            artifact_id=parsed.artifact_id,
            decision=decision,  # type: ignore[arg-type]
            findings=list(state.review_result.get("findings", [])) if state.review_result else [],
            rationale=str(state.review_result.get("rationale", "")) if state.review_result else "",
            pr_url=pr_url,
            next_action=next_action,
        ).model_dump()

    # ─── 6. explain ─────────────────────────────────────────────────────────

    async def handle_explain(self, args: dict[str, Any]) -> dict[str, Any]:
        """explain — обратный путь: код/запрос → объяснение. Read-only.

        Не требует state/node_* — работает напрямую с kb_server (если задан)
        и codebase_server (создаёт временный инстанс через mcp_servers.codebase,
        что разрешено — intra-package импорт).
        """
        parsed = ExplainInput.model_validate(args)
        log.info("facade_explain_start: query=%s has_code=%s", parsed.query, parsed.code is not None)

        related_patterns: list[dict[str, Any]] = []
        related_antipatterns: list[dict[str, Any]] = []
        similar_modules: list[dict[str, Any]] = []
        explanation_parts: list[str] = []

        # KB search (если kb_server доступен).
        if self.kb_server is not None:
            query = parsed.query or (parsed.code[:200] if parsed.code else "")
            if query:
                try:
                    search_result = await self.kb_server.search_kb(query=query, top_k=3)
                    for result in search_result.results:
                        item = {"id": result.get("id"), "category": result.get("category")}
                        if result.get("category") == "pattern":
                            related_patterns.append(item)
                        elif result.get("category") == "antipattern":
                            related_antipatterns.append(item)
                    explanation_parts.append(f"KB: найдено {len(search_result.results)} релевантных сущностей.")
                except Exception as exc:  # noqa: BLE001
                    log.warning("facade_explain_kb_failed: %s", exc)
                    explanation_parts.append(f"KB недоступен: {exc}")
        else:
            explanation_parts.append("KB сервер не настроен.")

        # Codebase semantic search (если есть code и config).
        if parsed.code and parsed.config_name and parsed.config_version:
            try:
                # mcp_servers.facade → mcp_servers.codebase: intra-package импорт
                # разрешён (codebase не в FORBIDDEN_IMPORTS для mcp_servers).
                from mcp_servers.codebase.server import CodebaseServer

                cs = CodebaseServer()
                sim = await cs.semantic_search(
                    query=parsed.code[:500],
                    config_name=parsed.config_name,
                    config_version=parsed.config_version,
                    top_k=3,
                )
                similar_modules = [
                    r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in sim.results
                ]
                explanation_parts.append(f"Codebase: найдено {len(similar_modules)} похожих модулей.")
            except Exception as exc:  # noqa: BLE001
                log.warning("facade_explain_codebase_failed: %s", exc)
                explanation_parts.append(f"Codebase недоступен: {exc}")

        return ExplainOutput(
            explanation="\n".join(explanation_parts) or "Нет данных для объяснения.",
            related_patterns=related_patterns,
            related_antipatterns=related_antipatterns,
            similar_modules=similar_modules,
        ).model_dump()

    # ─── 7. run_cli ─────────────────────────────────────────────────────────

    async def handle_run_cli(self, args: dict[str, Any]) -> dict[str, Any]:
        """run_cli — proxy к скрытым MCP tools (не lifecycle)."""
        parsed = RunCliInput.model_validate(args)
        log.info("facade_run_cli_start: tool_name=%s caller_role=%s", parsed.tool_name, parsed.caller_role)

        tool_name = parsed.tool_name
        result: dict[str, Any]
        warning: str | None = None

        try:
            if tool_name.startswith("kb.") and self.kb_server is not None:
                result = await self._proxy_kb(tool_name, parsed.args)
            elif tool_name.startswith("bsl_ls.") and self.bsl_ls_server is not None:
                result = await self._proxy_bsl_ls(tool_name, parsed.args)
            elif tool_name.startswith("metadata.") and self.metadata_server is not None:
                result = await self._proxy_metadata(tool_name, parsed.args)
            else:
                warning = (
                    f"Tool {tool_name!r} not available. "
                    "Поддерживаются: kb.* (если kb_server задан), bsl_ls.* (если bsl_ls_server задан), "
                    "metadata.* (если metadata_server задан). "
                    "codebase.*/git.* — будут добавлены в следующих спринтах."
                )
                result = {}
        except Exception as exc:  # noqa: BLE001
            warning = f"Tool {tool_name!r} failed: {exc}"
            result = {}

        return RunCliOutput(
            tool_name=tool_name,
            result=result,
            warning=warning,
        ).model_dump()

    async def _proxy_kb(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Proxy к kb_server methods."""
        method = tool_name.removeprefix("kb.")
        method_map = {
            "search_kb": "search_kb",
            "get_pattern": "get_pattern",
            "get_antipattern": "get_antipattern",
            "check_method_availability": "check_method_availability",
            "check_antipatterns": "check_antipatterns",
            "get_standard": "get_standard",
            "check_standards": "check_standards",
        }
        if method not in method_map:
            raise ValueError(f"Unknown kb tool: {tool_name!r}. Available: {list(method_map)}")
        fn = getattr(self.kb_server, method_map[method])
        out = await fn(**args)
        return out.model_dump() if hasattr(out, "model_dump") else dict(out)

    async def _proxy_bsl_ls(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Proxy к bsl_ls_server methods."""
        method = tool_name.removeprefix("bsl_ls.")
        method_map = {"lint": "lint", "format": "format"}
        if method not in method_map:
            raise ValueError(f"Unknown bsl_ls tool: {tool_name!r}. Available: {list(method_map)}")
        fn = getattr(self.bsl_ls_server, method_map[method])
        out = await fn(**args)
        return out.model_dump() if hasattr(out, "model_dump") else dict(out)

    async def _proxy_metadata(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Proxy к metadata_server methods (Stage 4 TD-S6-01)."""
        method = tool_name.removeprefix("metadata.")
        method_map = {
            "get_metadata": "get_metadata",
            "get_form_structure": "get_form_structure",
            "get_api_reference": "get_api_reference",
            "get_dependency_graph": "get_dependency_graph",
        }
        if method not in method_map:
            raise ValueError(f"Unknown metadata tool: {tool_name!r}. Available: {list(method_map)}")
        fn = getattr(self.metadata_server, method_map[method])
        out = await fn(**args)
        return out.model_dump(mode="json") if hasattr(out, "model_dump") else dict(out)

    # ─── 8. data_status ─────────────────────────────────────────────────────

    async def handle_data_status(self, args: dict[str, Any]) -> dict[str, Any]:
        """data_status — статус данных проекта: paths, configs, freshness.

        Не требует state/node_* — работает напрямую с path_manager и
        config_registry (data_layer, разрешено).
        """
        if args:
            raise ValueError(f"data_status takes no arguments, got: {list(args)}")

        log.info("facade_data_status_start")

        paths: dict[str, bool] = {}
        configs: list[dict[str, Any]] = []
        indexes_freshness: dict[str, dict[str, bool]] = {}
        missing: list[str] = []

        # PathManager validation.
        if self.path_manager is not None:
            try:
                validation = self.path_manager.validate()
                paths = {k: bool(v) for k, v in validation.items()}
                missing_keys = [k for k, v in validation.items() if not v]
                if missing_keys:
                    missing.append(f"Paths missing: {missing_keys}. Run: 1c-ai init")
            except Exception as exc:  # noqa: BLE001
                missing.append(f"PathManager.validate failed: {exc}")
        else:
            missing.append("PathManager not configured.")

        # ConfigRegistry list.
        if self.config_registry is not None:
            try:
                for entry in self.config_registry.list():
                    configs.append(
                        {
                            "name": entry.name,
                            "version": entry.version,
                            "is_fresh": getattr(entry, "is_fresh", None),
                        }
                    )
                    # Freshness check per config.
                    if self.path_manager is not None:
                        try:
                            freshness = self.path_manager.freshness_check(entry.name, entry.version)
                            indexes_freshness[f"{entry.name}:{entry.version}"] = {
                                k: bool(v) for k, v in freshness.items()
                            }
                        except Exception:  # noqa: BLE001
                            indexes_freshness[f"{entry.name}:{entry.version}"] = {"error": False}
            except Exception as exc:  # noqa: BLE001
                missing.append(f"ConfigRegistry.list failed: {exc}")
        else:
            missing.append("ConfigRegistry not configured.")

        return DataStatusOutput(
            paths=paths,
            configs=configs,
            indexes_freshness=indexes_freshness,
            missing_prerequisites=missing,
        ).model_dump()


# ─── module-level helpers ────────────────────────────────────────────────────


def _find_subtask_idx(state: Any, subtask_id: str) -> int | None:
    """Найти индекс подзадачи по id. None если не найдена."""
    for i, s in enumerate(state.subtasks):
        if s.id == subtask_id:
            return i
    return None


def _parse_artifact_id(artifact_id: str) -> tuple[str, int]:
    """Разобрать artifact_id формата '{subtask_id}#{iteration}'.

    Raises:
        ValueError: если формат некорректен.
    """
    if "#" not in artifact_id:
        raise ValueError(
            f"Invalid artifact_id format: {artifact_id!r}. Expected '{{subtask_id}}#{{iteration}}'."
        )
    subtask_id, _, iter_str = artifact_id.rpartition("#")
    try:
        iteration = int(iter_str)
    except ValueError as exc:
        raise ValueError(
            f"Invalid iteration in artifact_id: {artifact_id!r}. Expected integer after '#'."
        ) from exc
    if iteration < 1:
        raise ValueError(f"Iteration must be >= 1, got: {iteration}")
    return subtask_id, iteration
