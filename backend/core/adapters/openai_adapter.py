"""OpenAI 兼容 API 适配器（直接 HTTP 调用，无需 LangChain）。"""
import json
from typing import Any, AsyncIterator, Dict, List

import httpx

from .base import BaseLLMAdapter


class OpenAIAdapter(BaseLLMAdapter):
    """适配任意 OpenAI 兼容接口（包括自有部署、Azure、Ollama 等）。"""

    MODELS = [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
    ]

    def __init__(self, api_base: str = "", api_key: str = ""):
        self.api_base = api_base.rstrip("/")
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
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
        }
        payload.update(kwargs)
        # 超时放宽到 180s: 部分模型(如 qwen)带长上下文时响应可能超过 60s
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code >= 400:
                # 透出响应体便于定位(400 多为参数/模型/上下文问题)
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def chat_with_thinking(
        self,
        messages: list,
        model: str,
        **kwargs: Any,
    ) -> Dict[str, str]:
        """非流式对话（带思考过程），返回 {"thinking": "...", "content": "..."}。

        支持 DeepSeek reasoner / 通义千问 enable_thinking / OpenAI o-series。
        """
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
        }
        payload.update(kwargs)
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            return {
                "thinking": msg.get("reasoning_content", ""),
                "content": msg["content"] or "",
            }

    async def chat_stream(
        self,
        messages: list,
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """流式对话，逐块产出文本。"""
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        payload.update(kwargs)
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream(
                "POST",
                f"{self.api_base}/chat/completions",
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
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

    def get_models(self) -> List[str]:
        return list(self.MODELS)
