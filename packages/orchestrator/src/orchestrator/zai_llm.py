"""ZaiLLM — LangChain BaseChatModel adapter для z-ai CLI.

Я (Z.ai GLM) как LLM для pipeline. Использует `z-ai chat` CLI через subprocess.
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)


def _content_to_str(content: str | list[str | dict[str, Any]]) -> str:
    """Привести LangChain message content (str | list) к str.

    LangChain content может быть str или list of parts (str | dict). Для z-ai CLI
    нужен plain str.
    """
    if isinstance(content, str):
        return content
    # list of parts — конкатенируем str parts, dict parts сериализуем.
    parts: list[str] = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        else:
            parts.append(json.dumps(part, ensure_ascii=False))
    return "".join(parts)


class ZaiLLMConfig(BaseModel):
    """Конфигурация ZaiLLM."""

    model_config = ConfigDict(protected_namespaces=())

    model: str = Field(default="glm-4-plus")
    temperature: float = Field(default=0.2)
    max_tokens: int = Field(default=8000)
    timeout: int = Field(default=120)
    thinking_enabled: bool = Field(default=False)


class ZaiLLM(BaseChatModel):
    """LangChain BaseChatModel adapter для z-ai CLI."""

    config: ZaiLLMConfig = Field(default_factory=ZaiLLMConfig)

    def __init__(self, config: ZaiLLMConfig | None = None, **kwargs: Any) -> None:
        super().__init__(config=config or ZaiLLMConfig(), **kwargs)  # type: ignore[call-arg]

    @property
    def _llm_type(self) -> str:
        return "zai-cli"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return asyncio.run(self._agenerate(messages, stop, run_manager, **kwargs))

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        system_content = ""
        user_contents: list[str] = []

        for msg in messages:
            if msg.type == "system":
                system_content += _content_to_str(msg.content) + "\n"
            elif msg.type in ("human", "user"):
                user_contents.append(_content_to_str(msg.content))
            elif msg.type in ("ai", "assistant"):
                user_contents.append(f"[Previous AI response]: {_content_to_str(msg.content)}")

        user_content = "\n\n".join(user_contents) if user_contents else ""

        structured_schema = kwargs.get("structured_output_schema")
        if structured_schema:
            schema_json = json.dumps(structured_schema, ensure_ascii=False, indent=2)
            system_content += (
                "\n\n## ВАЖНО: Формат ответа\n"
                "Ответь СТРОГО валидным JSON согласно этой JSON Schema:\n"
                f"{schema_json}\n\n"
                "Только JSON, без markdown-обёрток, без пояснений."
            )

        log.info(
            "zai_llm_call_start: system_length=%d user_length=%d",
            len(system_content),
            len(user_content),
        )

        response_text = await self._call_cli(
            system=system_content,
            user=user_content,
        )

        log.info("zai_llm_call_done: response_length=%d", len(response_text))

        message = AIMessage(content=response_text)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    def with_structured_output(self, schema: type[BaseModel], **kwargs: Any) -> Any:  # type: ignore[override]
        """Обёртка для structured output."""
        return _ZaiStructuredOutput(parent=self, schema=schema)

    async def _call_cli(self, system: str, user: str) -> str:
        """Вызвать z-ai CLI (делегирует в _call_zai_cli)."""
        return await _call_zai_cli(system, user, self.config)


class _ZaiStructuredOutput:
    """Callable обёртка для with_structured_output."""

    def __init__(self, parent: ZaiLLM, schema: type[BaseModel]) -> None:
        self.parent = parent
        self.schema = schema
        self.json_schema = schema.model_json_schema()

    async def ainvoke(self, messages: list[BaseMessage], **kwargs: Any) -> BaseModel:
        """Async вызов с structured output."""
        result = await self.parent._agenerate(
            messages,
            structured_output_schema=self.json_schema,
            **kwargs,
        )
        content_raw = result.generations[0].message.content
        # LangChain content может быть str или list. Приводим к str.
        content = content_raw if isinstance(content_raw, str) else json.dumps(content_raw, ensure_ascii=False)

        json_text = self._extract_json(content)
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as exc:
            log.error(
                "zai_llm_json_parse_failed: error=%s content_preview=%.500s",
                exc,
                content,
            )
            raise ValueError(
                f"LLM response is not valid JSON: {exc}. "
                f"Content preview: {content[:200]}"
            ) from exc

        try:
            return self.schema.model_validate(data)
        except Exception as exc:
            log.error(
                "zai_llm_schema_validation_failed: error=%s data_preview=%.500s",
                exc,
                str(data),
            )
            raise

    def invoke(self, messages: list[BaseMessage], **kwargs: Any) -> BaseModel:
        """Синхронный вызов (делегирует в async)."""
        return asyncio.run(self.ainvoke(messages, **kwargs))

    @staticmethod
    def _extract_json(text: str) -> str:
        """Извлечь JSON из текста (может быть в markdown-обёртке)."""
        text = text.strip()

        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            return "\n".join(lines).strip()

        if text.startswith("{"):
            return text

        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return text[first_brace : last_brace + 1]

        return text


async def _call_cli_via_subprocess(
    cmd: list[str],
    timeout: int,
) -> str:
    """Вызвать subprocess асинхронно."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError(f"z-ai CLI timed out after {timeout}s") from None

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"z-ai CLI failed (exit {proc.returncode}): {err}")

    return stdout.decode("utf-8", errors="replace")


async def _call_zai_cli(system: str, user: str, config: ZaiLLMConfig) -> str:
    """Вызвать z-ai chat CLI с system и user prompt."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        output_path = Path(f.name)

    try:
        cmd: list[str] = ["z-ai", "chat", "-p", user, "-o", str(output_path)]
        if system:
            cmd.extend(["-s", system])
        if config.thinking_enabled:
            cmd.append("-t")

        raw = await _call_cli_via_subprocess(cmd, timeout=config.timeout)

        json_text = output_path.read_text(encoding="utf-8") if output_path.exists() else raw

        first_brace = json_text.find("{")
        last_brace = json_text.rfind("}")
        if first_brace != -1 and last_brace != -1:
            json_text = json_text[first_brace : last_brace + 1]

        data = json.loads(json_text)
        content_raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return str(content_raw) if content_raw is not None else ""
    finally:
        if output_path.exists():
            output_path.unlink()


async def _zai_call_cli_method(self: ZaiLLM, system: str, user: str) -> str:
    """Legacy helper (для backward compat, если кто-то импортирует)."""
    return await _call_zai_cli(system, user, self.config)
