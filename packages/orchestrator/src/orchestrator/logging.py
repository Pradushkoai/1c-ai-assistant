"""structlog конфигурация для orchestrator.

JSON формат для CI/Docker, console для dev.
См. ADR-0019 (Observability strategy).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog


def configure_logging() -> None:
    """Настроить structlog.

    Читает LOG_FORMAT из env:
    - 'json' — JSON lines (для CI/Docker)
    - 'console' — цветной console (для dev, по умолчанию)
    """
    log_format = os.environ.get("LOG_FORMAT", "console")

    shared_processors: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_format == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # also configure standard logging to not interfere
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), stream=sys.stderr)


def get_logger(name: str) -> Any:
    """Получить structlog logger.

    Args:
        name: имя логгера (обычно __name__).

    Returns:
        structlog BoundLogger.
    """
    return structlog.get_logger(name)
