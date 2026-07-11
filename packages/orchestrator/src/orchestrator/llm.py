"""LLM конфигурация для orchestrator.

Абстракция над LangChain LLM — позволяет тестировать узлы с mock.
См. ADR-0019 (Observability strategy).
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.language_models import BaseChatModel

from .logging import get_logger

log = get_logger(__name__)


class LLMConfig:
    """Конфигурация LLM из env vars.

    Поддерживаемые провайдеры:
    - openai: OPENAI_API_KEY + model (gpt-4o, gpt-4o-mini)
    - anthropic: ANTHROPIC_API_KEY + model (claude-sonnet)
    - ollama: OLLAMA_BASE_URL + model (local)
    """

    def __init__(self) -> None:
        self.provider = os.environ.get("LLM_PROVIDER", "openai")
        self.model_name = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        self.api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = os.environ.get("LLM_BASE_URL")
        self.temperature = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
        self.max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "8000"))


def create_llm(config: LLMConfig | None = None) -> BaseChatModel:
    """Создать LLM инстанс по конфигурации.

    Args:
        config: конфигурация LLM. Если None — из env vars.

    Returns:
        BaseChatModel (LangChain).

    Raises:
        ImportError: если провайдер не установлен.
        ValueError: если API key не указан.
    """
    if config is None:
        config = LLMConfig()

    if config.provider == "openai":
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": config.model_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.base_url:
            kwargs["base_url"] = config.base_url

        llm: BaseChatModel = ChatOpenAI(**kwargs)
        return llm

    if config.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model=config.model_name,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            api_key=config.api_key,
        )
        return llm

    if config.provider == "ollama":
        from langchain_ollama import ChatOllama

        llm = ChatOllama(
            model=config.model_name,
            temperature=config.temperature,
            base_url=config.base_url or "http://localhost:11434",
        )
        return llm

    raise ValueError(f"Unknown LLM provider: {config.provider}")


def render_prompt(template_path: str, **kwargs: Any) -> str:
    """Отрендерить Jinja2 промпт.

    Args:
        template_path: путь к .j2 файлу.
        **kwargs: переменные для шаблона.

    Returns:
        Отрендеренный текст.
    """
    import os

    from jinja2 import Environment, FileSystemLoader

    template_dir = os.path.dirname(template_path)
    template_name = os.path.basename(template_path)

    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=False,
        keep_trailing_newline=True,
    )
    template = env.get_template(template_name)
    return template.render(**kwargs)
