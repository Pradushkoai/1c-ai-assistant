"""`1c-ai health` — health check для Docker / orchestration (TD-S5-04).

Проверяет:
1. PersistenceManager.health_check() (если DATABASE_URL задан — PostgresSaver ping;
   иначе MemorySaver → True).
2. BSL LS HTTP ping (если BSL_LS_HTTP_URL задан — GET /health; иначе skip).

Выход:
- 0 если все проверки OK (или пропущены).
- 1 если любая проверка failed.

Вывод: JSON в stdout (для логов/парсинга), человекочитаемые ошибки в stderr.

См. ADR-0015 (deployment), D-2026-07-13-04 (PersistenceManager.health_check),
D-2026-07-13-09.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any


def cmd_health() -> int:
    """Запустить health check.

    Returns:
        0 если OK, 1 если есть проблемы.
    """
    result = asyncio.run(_run_health_checks())
    # JSON в stdout (для логов/парсинга).
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


async def _run_health_checks() -> dict[str, Any]:
    """Выполнить все health checks. Вернуть dict с результатами."""
    checks: dict[str, Any] = {}
    all_ok = True

    # ─── 1. Persistence check ────────────────────────────────────────────────
    persistence_status = await _check_persistence()
    checks["persistence"] = persistence_status
    if persistence_status["status"] != "ok":
        all_ok = False

    # ─── 2. BSL LS HTTP ping (опц.) ─────────────────────────────────────────
    bsl_ls_url = os.environ.get("BSL_LS_HTTP_URL")
    if bsl_ls_url:
        bsl_ls_status = await _check_bsl_ls(bsl_ls_url)
        checks["bsl_ls"] = bsl_ls_status
        if bsl_ls_status["status"] != "ok":
            all_ok = False
    else:
        checks["bsl_ls"] = {"status": "skipped", "reason": "BSL_LS_HTTP_URL not set"}

    return {
        "status": "ok" if all_ok else "failed",
        "checks": checks,
    }


async def _check_persistence() -> dict[str, Any]:
    """Проверка PersistenceManager.health_check()."""
    try:
        from orchestrator.persistence import PersistenceManager

        async with PersistenceManager.from_env() as pm:
            healthy = await pm.health_check()
            return {
                "status": "ok" if healthy else "failed",
                "type": "postgres" if pm.is_postgres else "memory",
                "dsn": _mask_dsn(os.environ.get("DATABASE_URL", "")) if pm.is_postgres else None,
            }
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}


async def _check_bsl_ls(url: str) -> dict[str, Any]:
    """Проверка BSL LS HTTP /health endpoint."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{url}/health")
            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "ok",
                    "url": url,
                    "bsl_ls_available": bool(data.get("bsl_ls_available", False)),
                }
            return {
                "status": "failed",
                "url": url,
                "http_status": response.status_code,
            }
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "url": url, "error": f"{type(exc).__name__}: {exc}"}


def _mask_dsn(dsn: str) -> str:
    """Скрыть пароль в DSN для логов."""
    if "@" in dsn and "://" in dsn:
        prefix, _, rest = dsn.partition("://")
        creds, _, host_part = rest.partition("@")
        if ":" in creds:
            user, _, _ = creds.partition(":")
            return f"{prefix}://{user}:***@{host_part}"
    return dsn


if __name__ == "__main__":
    sys.exit(cmd_health())
