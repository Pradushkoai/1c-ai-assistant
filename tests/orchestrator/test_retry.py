"""Тесты для orchestrator.retry — with_retry функция."""

from __future__ import annotations

import asyncio

import pytest

from orchestrator.errors import (
    AgentError,
    ErrorAction,
    MaxIterationsExceededError,
    RoleForbiddenError,
    ToolTimeoutError,
)
from orchestrator.retry import _compute_delay, with_retry


class TestWithRetry:
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_succeeds_first_attempt(self):
        async def func():
            return "ok"

        result = await with_retry(func, max_attempts=3, base_delay=0.01)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_succeeds_second_attempt(self):
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ToolTimeoutError("test.tool", 5)
            return "ok"

        result = await with_retry(func, max_attempts=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_exhausted_raises(self):
        async def func():
            raise ToolTimeoutError("test.tool", 5)

        with pytest.raises(ToolTimeoutError):
            await with_retry(func, max_attempts=2, base_delay=0.01)

    @pytest.mark.asyncio
    async def test_non_retryable_raises_immediately(self):
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            raise RoleForbiddenError("CODER", "metadata.get_metadata")

        with pytest.raises(RoleForbiddenError):
            await with_retry(func, max_attempts=3, base_delay=0.01)
        assert call_count == 1  # не retry'илось

    @pytest.mark.asyncio
    async def test_non_agent_error_raises_immediately(self):
        async def func():
            raise ValueError("not an AgentError")

        with pytest.raises(ValueError):
            await with_retry(func, max_attempts=3, base_delay=0.01)

    @pytest.mark.asyncio
    async def test_on_retry_callback(self):
        retries: list[int] = []

        async def func():
            raise ToolTimeoutError("test.tool", 5)

        def on_retry(err: Exception, attempt: int) -> None:
            retries.append(attempt)

        with pytest.raises(ToolTimeoutError):
            await with_retry(func, max_attempts=3, base_delay=0.01, on_retry=on_retry)
        assert len(retries) == 2  # 2 retry (attempt 1 and 2)


class TestComputeDelay:
    def test_exponential_backoff(self):
        err = AgentError("test", action=ErrorAction.RETRY)
        d1 = _compute_delay(err, 1, 1.0, 30.0)
        d2 = _compute_delay(err, 2, 1.0, 30.0)
        d3 = _compute_delay(err, 3, 1.0, 30.0)
        assert d1 == 1.0  # 1 * 2^0
        assert d2 == 2.0  # 1 * 2^1
        assert d3 == 4.0  # 1 * 2^2

    def test_max_delay_cap(self):
        err = AgentError("test", action=ErrorAction.RETRY)
        delay = _compute_delay(err, 10, 1.0, 5.0)
        assert delay == 5.0  # capped at max_delay

    def test_linear_backoff_for_connection_error(self):
        from orchestrator.errors import ToolConnectionError

        err = ToolConnectionError("test.tool", ConnectionError("refused"))
        d1 = _compute_delay(err, 1, 1.0, 30.0)
        d2 = _compute_delay(err, 2, 1.0, 30.0)
        d3 = _compute_delay(err, 3, 1.0, 30.0)
        assert d1 == 1.0  # 1 * 1
        assert d2 == 2.0  # 1 * 2
        assert d3 == 3.0  # 1 * 3
