"""commit node — сохранение сгенерированного кода (git commit или file fallback).

Stage 4 (TD-S6-02): если ``git_server`` и ``repo_path`` заданы — real git flow
(create_branch + commit + опц. open_pr через GitServer). Иначе — fallback на
Sprint 2 логику (file save в ``runtime/generated/``). Backward compat для dev/tests.

См. ADR-0004 (Hierarchical orchestration), ADR-0009 (Pipeline contracts),
ADR-0005 (TOOL_GROUPS[COMMITTER] = git.*), ADR-0010 (MCP tool contracts),
D-2026-07-13-11.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..contracts import CommitResult
from ..logging import get_logger
from ..state import FSMState, TaskState

log = get_logger(__name__)


async def commit_node(
    state: TaskState,
    git_server: Any = None,
    repo_path: str | None = None,
) -> dict[str, Any]:
    """Сохранить сгенерированный код: git commit (если git_server задан) или file fallback.

    Args:
        state: текущее состояние pipeline.
        git_server: GitServer инстанс (TD-S5-03). Если None — file fallback.
        repo_path: путь к git-репозиторию для коммита. Если None — file fallback.
            Читается из env ``1C_AI_REPO_PATH`` если не передан явно.

    Returns:
        dict с commit_result, fsm_state.
    """
    subtask = state.current_subtask
    assert subtask is not None
    assert state.iterations, "No iterations in state"

    current_iteration = state.iterations[-1]
    code = current_iteration.code

    log.info(
        "commit_start",
        task_id=state.task_id,
        subtask_id=subtask.id,
        iteration=current_iteration.number,
        git_enabled=git_server is not None,
    )

    # repo_path: явный параметр > env 1C_AI_REPO_PATH.
    effective_repo_path = repo_path or os.environ.get("1C_AI_REPO_PATH")

    # ─── Branch: feature/{task_id[:8]}-{subtask_id[:8]} ──────────────────────
    branch_name = f"feature/{state.task_id[:8]}-{subtask.id[:8]}"

    # ─── file_path derivation ────────────────────────────────────────────────
    file_path = _derive_file_path(subtask, current_iteration.number)

    if git_server is not None and effective_repo_path:
        # ─── Real git flow (Stage 4, TD-S6-02) ───────────────────────────────
        commit_result = await _git_flow(
            git_server=git_server,
            repo_path=effective_repo_path,
            file_path=file_path,
            code=code,
            branch_name=branch_name,
            state=state,
            subtask=subtask,
            iteration_num=current_iteration.number,
        )
    else:
        # ─── Fallback: file save (Sprint 2 логика, backward compat) ──────────
        log.warning(
            "commit_fallback_file_save",
            hint="Set git_server + 1C_AI_REPO_PATH env for real git commits",
        )
        commit_result = _file_fallback(
            file_path=file_path,
            code=code,
            branch_name=branch_name,
            subtask=subtask,
            iteration_num=current_iteration.number,
        )

    log.info(
        "commit_done",
        task_id=state.task_id,
        subtask_id=subtask.id,
        branch=commit_result.branch_name,
        commit_sha=commit_result.commit_sha[:12] if commit_result.commit_sha else None,
        pr_url=commit_result.pr_url,
    )

    return {
        "commit_result": commit_result.model_dump(mode="json"),
        "fsm_state": FSMState.DONE,
    }


async def _git_flow(
    *,
    git_server: Any,
    repo_path: str,
    file_path: str,
    code: str,
    branch_name: str,
    state: TaskState,
    subtask: Any,
    iteration_num: int,
) -> CommitResult:
    """Real git flow: create_branch + write file + commit + опц. open_pr."""
    # 1. Create branch.
    branch_output = await git_server.create_branch(
        repo_path=repo_path,
        branch_name=branch_name,
    )
    actual_branch = branch_output.branch_name

    # 2. Write code to file (relative path в repo_path).
    full_path = Path(repo_path) / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(code, encoding="utf-8")

    # 3. git add + commit.
    commit_message = _build_commit_message(state, subtask, iteration_num)
    commit_output = await git_server.commit(
        repo_path=repo_path,
        message=commit_message,
        files=[file_path],
        branch=actual_branch,
    )

    pr_url: str | None = None
    pr_number: int | None = None

    # 4. Опц. open_pr (если 1C_AI_OPEN_PR=1).
    if os.environ.get("1C_AI_OPEN_PR") == "1":
        try:
            pr_output = await git_server.open_pr(
                repo_path=repo_path,
                branch=actual_branch,
                title=commit_message.split("\n")[0],
                body=_build_pr_body(state, subtask, iteration_num),
                base=branch_output.base,
            )
            pr_url = pr_output.pr_url
            pr_number = pr_output.pr_number
        except Exception as exc:  # noqa: BLE001
            log.warning("commit_open_pr_failed: %s", exc)

    return CommitResult(
        subtask_id=subtask.id,
        branch_name=actual_branch,
        commit_sha=commit_output.commit_sha,
        pr_url=pr_url,
        pr_number=pr_number,
        files_changed=commit_output.files_changed,
        diff_summary=f"Generated {code.count(chr(10)) + 1} lines of BSL code in {file_path}",
    )


def _file_fallback(
    *,
    file_path: str,
    code: str,
    branch_name: str,
    subtask: Any,
    iteration_num: int,
) -> CommitResult:
    """Fallback: сохранить код в runtime/generated/ (Sprint 2 логика)."""
    output_dir = Path("runtime/generated")
    output_dir.mkdir(parents=True, exist_ok=True)
    # В fallback используем basename из file_path (без subdir).
    filename = Path(file_path).name
    if not filename.endswith(".bsl"):
        filename = f"{subtask.id}_{iteration_num}.bsl"
    output_file = output_dir / filename
    output_file.write_text(code, encoding="utf-8")

    return CommitResult(
        subtask_id=subtask.id,
        branch_name=branch_name,
        commit_sha="n/a (file fallback: no git_server)",
        pr_url=None,
        pr_number=None,
        files_changed=[str(output_file)],
        diff_summary=f"Generated {code.count(chr(10)) + 1} lines of BSL code (file fallback)",
    )


def _derive_file_path(subtask: Any, iteration: int) -> str:
    """Путь к файлу BSL (relative) по convention 1С.

    CommonModule.Имя → CommonModules/Имя/Ext/Module.bsl
    Catalog.Имя → Catalogs/Имя/Ext/ObjectModule.bsl
    Document.Имя → Documents/Имя/Ext/ObjectModule.bsl
    Иначе → Generated/{subtask_id}_{iteration}.bsl
    """
    target = subtask.target_module
    type_ = getattr(target, "type", "")
    name = getattr(target, "name", "")

    if type_ == "CommonModule" and name:
        return f"CommonModules/{name}/Ext/Module.bsl"
    if type_ == "Catalog" and name:
        return f"Catalogs/{name}/Ext/ObjectModule.bsl"
    if type_ == "Document" and name:
        return f"Documents/{name}/Ext/ObjectModule.bsl"
    # Fallback для других типов.
    return f"Generated/{subtask.id}_{iteration}.bsl"


def _build_commit_message(state: TaskState, subtask: Any, iteration: int) -> str:
    """Commit message по convention."""
    return (
        f"feat({subtask.name}): generated BSL code (iter {iteration})\n\n"
        f"Task: {state.description[:200]}\n"
        f"Subtask: {subtask.id}\n"
        f"Target: {subtask.target_module}\n\n"
        f"Generated by 1c-ai-assistant (task_id={state.task_id})"
    )


def _build_pr_body(state: TaskState, subtask: Any, iteration: int) -> str:
    """PR body с описанием задачи и критериями приёмки."""
    criteria = "\n".join(f"- {c}" for c in subtask.acceptance_criteria) or "- Код компилируется"
    return (
        f"## Задача\n{state.description}\n\n"
        f"## Подзадача\n{subtask.name} ({subtask.id})\n"
        f"**Target:** {subtask.target_module}\n\n"
        f"## Критерии приёмки\n{criteria}\n\n"
        f"## Итерация\n{iteration}\n\n"
        f"---\n_Generated by 1c-ai-assistant_"
    )
