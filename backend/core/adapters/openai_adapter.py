"""OpenAI 兼容 API 适配器（直接 HTTP 调用，无需 LangChain）。"""
import asyncio
import json
from typing import Any, AsyncIterator, Dict, List

import httpx

from .base import BaseLLMAdapter


def _is_retryable(exc: Exception, status: int = 0) -> bool:
    """判断错误是否值得重试: 网络类异常 / 5xx / 429。4xx 为参数错误不重试。"""
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError, httpx.NetworkError,
                        httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout)):
        return True
    return status in (429, 500, 502, 503, 504)


class OpenAIAdapter(BaseLLMAdapter):
    """适配任意 OpenAI 兼容接口（包括自有部署、Azure、Ollama 等）。"""

    # 模型层重试配置: 暂时性错误(网络抖动/5xx/限流)最多重试 2 次, 指数退避
    MAX_RETRIES = 2
    RETRY_BASE_DELAY = 1.0

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

    async def _post(self, url: str, headers: dict, payload: dict) -> httpx.Response:
        """带重试的 POST: 暂时性错误指数退避重试, 4xx 直接抛出。"""
        last_exc: Exception | None = None
        last_status = 0
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                # 超时放宽到 180s: 部分模型(如 qwen)带长上下文时响应可能超过 60s
                async with httpx.AsyncClient(timeout=180) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code < 400:
                    return resp
                last_status = resp.status_code
                if not _is_retryable(None, resp.status_code):
                    # 4xx 参数/鉴权/上下文错误: 重试无意义
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
            except (httpx.TimeoutException, httpx.TransportError,
                    httpx.NetworkError, httpx.ConnectError,
                    httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_exc = e
            except RuntimeError:
                raise
            except Exception as e:  # noqa: BLE001
                last_exc = e
            if attempt < self.MAX_RETRIES:
                await asyncio.sleep(self.RETRY_BASE_DELAY * (2 ** attempt))
        if last_exc is not None:
            raise RuntimeError(f"请求失败(重试 {self.MAX_RETRIES} 次后): {last_exc}")
        raise RuntimeError(f"HTTP {last_status}: 服务端错误(重试 {self.MAX_RETRIES} 次后仍失败)")

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
        resp = await self._post(f"{self.api_base}/chat/completions", headers, payload)
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
        resp = await self._post(f"{self.api_base}/chat/completions", headers, payload)
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
