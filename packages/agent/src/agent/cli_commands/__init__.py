"""agent.cli_commands — подкоманды CLI 1c-ai.

Каждый модуль экспортирует cmd_* функцию, которая возвращает exit code (int).
CLI (cli.py) вызывает эти функции через click.
"""

from __future__ import annotations

__all__ = [
    "config",
    "generate",
    "hbk",
    "init",
    "validate",
]
