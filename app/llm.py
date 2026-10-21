from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI, BadRequestError

from app.config import Settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage_tokens: int = 0


def _extract_json_object(text: str) -> dict[str, Any] | None:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        candidate = fenced.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        candidate = text[start : end + 1]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


class LLMClient:
    def __init__(self, settings: Settings):
        self.model = settings.vultr_model
        self._client = AsyncOpenAI(
            base_url=settings.vultr_base_url,
            api_key=settings.vultr_api_key or "not-set",
        )

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.2,
            )
            choice = response.choices[0].message
            usage = getattr(response, "usage", None)
            tokens = int(getattr(usage, "total_tokens", 0) or 0)
            calls: list[ToolCall] = []
            for call in choice.tool_calls or []:
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                calls.append(
                    ToolCall(
                        id=call.id,
                        name=call.function.name,
                        arguments=arguments,
                    )
                )
            if calls:
                return LLMResponse(
                    content=choice.content,
                    tool_calls=calls,
                    usage_tokens=tokens,
                )
            if choice.content:
                parsed = _parse_fallback(choice.content)
                if parsed:
                    parsed.usage_tokens = tokens
                    return parsed
            return LLMResponse(content=choice.content, usage_tokens=tokens)
        except BadRequestError:
            # Some OpenAI-compatible endpoints accept chat but not tools.
            # Only retry on a schema/tool rejection; do not double-bill on
            # 429/5xx/network errors.
            fallback_messages = list(messages)
            fallback_messages.append(
                {
                    "role": "system",
                    "content": (
                        "Respond with exactly one JSON object and no prose:\n"
                        '{"tool":"run_command|read_file|write_file|list_files|finish",'
                        '"arguments":{...}}'
                    ),
                }
            )
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=fallback_messages,
                temperature=0.2,
            )
            content = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            tokens = int(getattr(usage, "total_tokens", 0) or 0)
            parsed = _parse_fallback(content)
            if parsed:
                parsed.usage_tokens = tokens
                return parsed
            return LLMResponse(content=content, usage_tokens=tokens)


def _parse_fallback(content: str) -> LLMResponse | None:
    obj = _extract_json_object(content)
    if not obj:
        return None
    name = obj.get("tool") or obj.get("name")
    arguments = obj.get("arguments") or obj.get("args") or {}
    if not isinstance(name, str):
        return None
    if not isinstance(arguments, dict):
        arguments = {}
    return LLMResponse(
        content=None,
        tool_calls=[
            ToolCall(id="fallback-call", name=name, arguments=arguments)
        ],
    )


class FakeLLM:
    """Deterministic LLM used by tests and local smoke runs."""

    def __init__(self, script: list[LLMResponse]):
        self._initial = list(script)
        self.script = list(script)
        self.calls = 0

    def reset(self) -> None:
        self.script = list(self._initial)
        self.calls = 0

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        self.calls += 1
        if not self.script:
            return LLMResponse(
                tool_calls=[
                    ToolCall(
                        id=f"fake-finish-{self.calls}",
                        name="finish",
                        arguments={"summary": "Fake run finished."},
                    )
                ]
            )
        return self.script.pop(0)
