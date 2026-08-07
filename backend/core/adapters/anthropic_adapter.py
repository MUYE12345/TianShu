"""Anthropic Messages API 适配器（直接 HTTP 调用）。"""
import json
from typing import Any, AsyncIterator, Dict, List

import httpx

from .base import BaseLLMAdapter


class AnthropicAdapter(BaseLLMAdapter):
    """适配 Anthropic Messages API (claude-* 系列模型)。"""

    MODELS = [
        "claude-sonnet-4-20250514",
        "claude-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
    ]

    API_BASE = "https://api.anthropic.com/v1"

    def __init__(self, api_base: str = "", api_key: str = ""):
        self.api_base = (api_base.rstrip("/") if api_base else self.API_BASE)
        self.api_key = api_key

    async def chat(
        self,
        messages: list,
        model: str,
        **kwargs: Any,
    ) -> str:
        """非流式对话，返回完整文本。"""
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        system = None
        msgs = messages
        if messages and messages[0].get("role") == "system":
            system = messages[0]["content"]
            msgs = messages[1:]

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": msgs,
            "max_tokens": kwargs.pop("max_tokens", 8192),
        }
        if system:
            payload["system"] = system
        payload.update(kwargs)

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.api_base}/messages",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return "".join(
                block["text"] for block in data.get("content", []) if block.get("type") == "text"
            )

    async def chat_with_thinking(
        self,
        messages: list,
        model: str,
        **kwargs: Any,
    ) -> Dict[str, str]:
        """非流式对话（带 Extended Thinking），返回 {"thinking": "...", "content": "..."}。"""
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        system = None
        msgs = messages
        if messages and messages[0].get("role") == "system":
            system = messages[0]["content"]
            msgs = messages[1:]

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        thinking_budget = kwargs.pop("thinking_budget", 4000)
        payload = {
            "model": model,
            "messages": msgs,
            "max_tokens": kwargs.pop("max_tokens", 8192),
            "thinking": {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            },
        }
        if system:
            payload["system"] = system
        payload.update(kwargs)

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.api_base}/messages",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            content_blocks = data.get("content", [])
            thinking = "".join(
                block["thinking"] for block in content_blocks if block.get("type") == "thinking"
            )
            text = "".join(
                block["text"] for block in content_blocks if block.get("type") == "text"
            )
            return {"thinking": thinking, "content": text}

    async def chat_stream(
        self,
        messages: list,
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """流式对话，逐块产出文本（sse 格式）。"""
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        system = None
        msgs = messages
        if messages and messages[0].get("role") == "system":
            system = messages[0]["content"]
            msgs = messages[1:]

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": msgs,
            "max_tokens": kwargs.pop("max_tokens", 8192),
            "stream": True,
        }
        if system:
            payload["system"] = system
        payload.update(kwargs)

        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream(
                "POST",
                f"{self.api_base}/messages",
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[len("data: "):]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            if chunk.get("type") == "content_block_delta":
                                delta = chunk.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")
                        except (json.JSONDecodeError, KeyError):
                            continue

    def get_models(self) -> List[str]:
        return list(self.MODELS)
