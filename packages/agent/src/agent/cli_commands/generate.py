"""`1c-ai generate` — генерация BSL-кода через pipeline.

Запускает LangGraph pipeline: preflight → plan → gather → code → validate → review → commit.

См. ADR-0004 (Hierarchical orchestration) и ADR-0009 (Pipeline contracts).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import click
from data_layer import ConfigRegistry, PathManager


def cmd_generate(
    task: str,
    config_name: str,
    config_version: str | None,
    platform_version: str,
    output: str | None,
) -> int:
    """Сгенерировать BSL-код через pipeline.

    Args:
        task: описание задачи на естественном языке.
        config_name: имя конфигурации.
        config_version: версия (если None — единственная).
        platform_version: версия платформы 1С.
        output: путь для сохранения результата (если None — stdout).

    Returns:
        0 при успехе, 1 при ошибке.
    """
    try:
        pm = PathManager()
    except FileNotFoundError as exc:
        click.echo(f"❌ {exc}", err=True)
        return 1

    # Найти конфигурацию
    registry = ConfigRegistry(pm.config_registry_path())
    entries = [e for e in registry.list() if e.name == config_name]
    if not entries:
        click.echo(
            f"❌ Конфигурация '{config_name}' не найдена. Используйте `1c-ai config list` для списка.",
            err=True,
        )
        return 1

    if config_version:
        entries = [e for e in entries if e.version == config_version]
        if not entries:
            click.echo(f"❌ Конфигурация {config_name}/{config_version} не найдена.", err=True)
            return 1
    else:
        if len(entries) > 1:
            click.echo(
                f"❌ Найдено {len(entries)} версий конфигурации '{config_name}'. "
                f"Укажите --version. Доступные: {', '.join(e.version for e in entries)}",
                err=True,
            )
            return 1

    entry = entries[0]
    config_version = entry.version

    click.echo("Генерация BSL-кода для задачи:")
    click.echo(f"  Конфигурация: {config_name}/{config_version}")
    click.echo(f"  Платформа: {platform_version}")
    click.echo(f"  Задача: {task[:100]}{'...' if len(task) > 100 else ''}")
    click.echo()

    # Запускаем pipeline
    try:
        result = asyncio.run(_run_pipeline(task, config_name, config_version, platform_version))
    except Exception as exc:
        click.echo(f"❌ Ошибка pipeline: {exc}", err=True)
        return 1

    # Вывод результата
    return _print_result(result, output)


async def _run_pipeline(
    task: str,
    config_name: str,
    config_version: str,
    platform_version: str,
) -> dict[str, Any]:
    """Запустить LangGraph pipeline.

    Sprint 3.2.1: серверы (BslLsServer, KbServer) создаются ЗДЕСЬ, в agent-слое,
    и передаются в build_graph через DI. Это устраняет boundary violations.

    Stage 3 (TD-S5-01): persistence через PersistenceManager — если задана env
    DATABASE_URL, используется AsyncPostgresSaver (checkpoints переживают рестарт
    контейнера); иначе MemorySaver (dev/tests).
    """
    from orchestrator.graph import build_graph
    from orchestrator.logging import configure_logging
    from orchestrator.persistence import PersistenceManager
    from orchestrator.state import FSMState, TaskState

    configure_logging()

    initial_state = TaskState(
        task_id=f"task-{config_name}-{config_version}",
        description=task,
        config_name=config_name,
        config_version=config_version,
        platform_version=platform_version,
        fsm_state=FSMState.INIT,
    )

    # Sprint 3.2.1: создаем MCP servers в agent-слое (вне orchestrator).
    bsl_ls_server = None
    try:
        from mcp_servers.bsl_ls.server import BslLsServer

        bsl_ls_server = BslLsServer()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("bsl_ls_server_init_failed: %s", exc)

    kb_server = None
    try:
        from mcp_servers.kb.server import KbServer

        kb_server = KbServer()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("kb_server_init_failed: %s", exc)

    # Stage 4 (TD-S6-01): metadata server для gather (api-reference) + plan (dep graph).
    metadata_server = None
    try:
        from mcp_servers.metadata.server import MetadataServer

        metadata_server = MetadataServer()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("metadata_server_init_failed: %s", exc)

    # Stage 3 (TD-S5-01): persistence. PostgresSaver (production) или MemorySaver.
    async with PersistenceManager.from_env() as pm:
        # Собираем граф с DI + checkpointer из PersistenceManager.
        graph = build_graph(
            checkpointer=pm.get_checkpointer(),
            bsl_ls_server=bsl_ls_server,
            kb_server=kb_server,
            metadata_server=metadata_server,
        )

        config: dict[str, Any] = {"configurable": {"thread_id": initial_state.task_id}}
        final_state = await graph.ainvoke(initial_state.model_dump(), config=config)

    return dict(final_state) if final_state else {}


def _print_result(final_state: dict[str, Any], output: str | None) -> int:
    """Вывести результат pipeline.

    Args:
        final_state: финальный state от LangGraph.
        output: путь для сохранения (None = stdout).

    Returns:
        0 при успехе.
    """
    fsm_state = final_state.get("fsm_state", "unknown")

    if fsm_state == "done":
        click.echo("✅ Задача выполнена успешно!")

        # Выводим сгенерированный код
        iterations = final_state.get("iterations", [])
        if iterations:
            last_iteration = iterations[-1]
            # Sprint 3.3: last_iteration может быть Iteration (Pydantic) или dict.
            if hasattr(last_iteration, "code"):
                code = last_iteration.code
            elif isinstance(last_iteration, dict):
                code = last_iteration.get("code", "")
            else:
                code = str(last_iteration)

            if output:
                output_path = Path(output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(code, encoding="utf-8")
                click.echo(f"  📁 Код сохранён: {output_path}")
            else:
                click.echo("\n--- Сгенерированный BSL-код ---\n")
                click.echo(code)
                click.echo("\n--- Конец ---\n")

            # Статистика
            click.echo(f"  Итераций: {len(iterations)}")
            click.echo(f"  Строк кода: {code.count(chr(10)) + 1}")

            # Commit result
            commit_result = final_state.get("commit_result")
            if commit_result:
                # Sprint 3.3: commit_result может быть CommitResult (Pydantic) или dict.
                if hasattr(commit_result, "files_changed"):
                    files = commit_result.files_changed
                elif isinstance(commit_result, dict):
                    files = commit_result.get("files_changed", [])
                else:
                    files = []
                if files:
                    click.echo(f"  Файлы: {', '.join(files)}")

        return 0

    if fsm_state == "escalated":
        click.echo("⚠️  Задача эскалирована — требуется ручная проверка.")

        escalate_result = final_state.get("escalate_result")
        if escalate_result:
            reason = escalate_result.get("reason", "unknown")
            click.echo(f"  Причина: {reason}")

            suggested = escalate_result.get("suggested_actions", [])
            if suggested:
                click.echo("  Рекомендации:")
                for action in suggested:
                    click.echo(f"    - {action}")

            # Сохраняем код последней итерации
            iterations = final_state.get("iterations", [])
            if iterations:
                last_iter = iterations[-1]
                if hasattr(last_iter, "code"):
                    code = last_iter.code
                elif isinstance(last_iter, dict):
                    code = last_iter.get("code", "")
                else:
                    code = ""
                if output:
                    output_path = Path(output)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(code, encoding="utf-8")
                    click.echo(f"  📁 Код сохранён: {output_path}")
                else:
                    click.echo("\n--- Код последней итерации ---\n")
                    click.echo(code)

        return 1

    click.echo(f"❌ Pipeline завершился в неожиданном состоянии: {fsm_state}", err=True)
    return 1
