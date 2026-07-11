"""Retry-логика для всех ошибок с action=RETRY.

Не spread'ится по коду — единая функция.

См. ADR-0014 (Error taxonomy + PostgresSaver).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .errors import AgentError, ErrorAction, LLMRateLimitError, ToolConnectionError, ToolTimeoutError

log = logging.getLogger(__name__)

T = TypeVar("T")


# Ошибки, которые можно retry'ить
RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    ToolTimeoutError,
    ToolConnectionError,
    LLMRateLimitError,
)


async def with_retry[T](
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    on_retry: Callable[[Exception, int], None] | None = None,
) -> T:
    """Выполнить func с retry для retryable ошибок.

    Логика:
    - LLMRateLimitError → delay = retry_after (если есть)
    - ToolTimeoutError → exponential backoff (base * 2^attempt)
    - ToolConnectionError → linear backoff (base * attempt)
    - Другие AgentError с action=RETRY → exponential backoff
    - action=ESCALATE/ABORT → raise immediately

    Args:
        func: async функция для выполнения.
        max_attempts: максимум попыток (включая первую).
        base_delay: базовая задержка в секундах.
        max_delay: максимальная задержка в секундах.
        on_retry: опциональный callback перед каждым retry.

    Returns:
        Результат func.

    Raises:
        AgentError: если все попытки исчерпаны или ошибка не retryable.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await func()
        except AgentError as err:
            last_error = err
            if err.action != ErrorAction.RETRY:
                raise
            if attempt == max_attempts:
                log.warning(
                    "Retry exhausted: %s (code=%s, attempt=%d/%d)",
                    err,
                    err.code,
                    attempt,
                    max_attempts,
                )
                raise
            delay = _compute_delay(err, attempt, base_delay, max_delay)
            log.info(
                "Retry %d/%d after %.1fs: %s (code=%s)",
                attempt,
                max_attempts,
                delay,
                err,
                err.code,
            )
            if on_retry:
                on_retry(err, attempt)
            await asyncio.sleep(delay)
        except Exception:
            # Не AgentError — не retry'им
            raise

    # Unreachable, но для mypy
    assert last_error is not None
    raise last_error


def _compute_delay(
    err: AgentError,
    attempt: int,
    base: float,
    max_delay: float,
) -> float:
    """Вычислить задержку перед retry.

    Args:
        err: ошибка.
        attempt: номер попытки (1-based).
        base: базовая задержка.
        max_delay: максимальная задержка.

    Returns:
        Задержка в секундах.
    """
    if isinstance(err, LLMRateLimitError):
        retry_after_raw = err.details.get("retry_after")
        retry_after = float(retry_after_raw) if retry_after_raw is not None else base
        return min(retry_after, max_delay)
    if isinstance(err, ToolConnectionError):
        # Linear backoff
        return float(min(base * attempt, max_delay))
    # Exponential backoff (для ToolTimeoutError и других retryable)
    return float(min(base * (2 ** (attempt - 1)), max_delay))
