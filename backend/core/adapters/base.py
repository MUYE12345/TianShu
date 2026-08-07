"""Abstract base class for LLM adapters."""
import asyncio
import threading
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, List, Dict


class LLMResponse(str):
    """LLM 返回对象: 兼容字符串用法, 同时支持 LangChain 风格的 .content 访问。

    代码库中调用点写法不统一——有的取 result.content, 有的直接当字符串
    (result.strip() / json.loads(result) / f-string)。用 str 子类 + content 属性
    可同时兼容两种写法。
    """

    @property
    def content(self) -> str:
        return str(self)


class BaseLLMAdapter(ABC):
    """所有 LLM 适配器必须实现的抽象基类。"""

    # 默认模型名, 由 ModelManager._build_adapter 注入
    default_model: str = ""

    @abstractmethod
    async def chat(self, messages: list, model: str, **kwargs: Any) -> str:
        """非流式对话，返回完整文本。"""
        ...

    @abstractmethod
    async def chat_stream(
        self, messages: list, model: str, **kwargs: Any
    ) -> AsyncIterator[str]:
        """流式对话，逐块产出文本片段。"""
        ...

    async def chat_with_thinking(
        self, messages: list, model: str, **kwargs: Any
    ) -> Dict[str, str]:
        """非流式对话（带思考过程），返回 {"thinking": "...", "content": "..."}。

        默认实现回退到 chat()，thinking 为空字符串。
        支持 thinking 的提供商（Anthropic/DeepSeek/Qwen）应覆写此方法。
        """
        content = await self.chat(messages, model, **kwargs)
        return {"thinking": "", "content": content}

    def invoke(self, messages, **kwargs: Any) -> LLMResponse:
        """同步对话（兼容 LangChain invoke 风格）。

        若在运行中的事件循环里被调用, 则另起线程跑新事件循环, 避免 asyncio.run 冲突。
        """
        try:
            asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            in_loop = False

        if not in_loop:
            return LLMResponse(asyncio.run(self.chat(messages, self.default_model, **kwargs)))

        holder: Dict[str, str] = {}

        def _run():
            loop = asyncio.new_event_loop()
            try:
                holder["r"] = loop.run_until_complete(
                    self.chat(messages, self.default_model, **kwargs)
                )
            finally:
                loop.close()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join()
        return LLMResponse(holder.get("r", ""))

    async def ainvoke(self, messages, **kwargs: Any) -> LLMResponse:
        """异步对话（兼容 LangChain ainvoke 风格）。"""
        result = await self.chat(messages, self.default_model, **kwargs)
        return LLMResponse(result)

    @abstractmethod
    def get_models(self) -> List[str]:
        """返回该提供商支持的模型列表（部分实现可返回静态列表）。"""
        ...
