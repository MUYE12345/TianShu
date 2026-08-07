"""
重试工具 — 指数退避 + 随机抖动

仅对 classify_error 标记为 retryable 的错误进行重试（RATE_LIMIT / TIMEOUT），
避免对认证失败、模型拒绝等不可重试的错误浪费资源。

用法:
  from backend.core.retry_utils import retry_with_backoff, async_retry

  @retry_with_backoff(max_retries=3, base_delay=1.0)
  def call_llm(prompt: str) -> str:
      ...

  @async_retry(max_retries=5, base_delay=0.5)
  async def call_tool(name: str, args: dict) -> dict:
      ...
"""
import asyncio
import functools
import random
import time
from typing import Any, Callable, Optional, TypeVar

from backend.core.error_classifier import (
    AgentError,
    classify_error,
    is_retryable,
    AgentErrorType,
)
from backend.core.logger import log

# ---------------------------------------------------------------------------
# 类型变量
# ---------------------------------------------------------------------------

F = TypeVar("F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# 重试装饰器工厂
# ---------------------------------------------------------------------------

def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    on_retry: Optional[Callable[[int, float, BaseException], None]] = None,
) -> Callable[[F], F]:
    """同步函数的重试装饰器（指数退避 + 可选抖动）。

    参数:
        max_retries: 最大重试次数（默认 3）。
        base_delay: 基础延迟秒数（默认 1.0）。
        max_delay: 最大延迟秒数（默认 60.0），退避后的延迟不会超过此值。
        backoff_factor: 退避倍数（默认 2.0）。
        jitter: 是否添加随机抖动（默认 True）。
        on_retry: 每次重试前的回调，参数为 (attempt, delay, exception)。
                  可用于监控、打点、日志等。
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[BaseException] = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    error_type = classify_error(exc)

                    # 最后一次尝试：不重试，直接抛出
                    if attempt >= max_retries:
                        log.warning(
                            "重试耗尽 [%s] %s (已尝试 %d 次): %s",
                            error_type.value,
                            func.__qualname__,
                            attempt,
                            exc,
                        )
                        raise

                    # 检查是否可重试
                    if not is_retryable(error_type):
                        log.info(
                            "不可重试的错误 [%s] %s，直接抛出: %s",
                            error_type.value,
                            func.__qualname__,
                            exc,
                        )
                        raise

                    # 计算退避延迟
                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    if jitter:
                        # 随机抖动：延迟的 [0, delay) 范围内的随机值
                        delay = random.uniform(0, delay)

                    # 回调通知
                    if on_retry is not None:
                        on_retry(attempt + 1, delay, exc)

                    log.info(
                        "重试 [%s] %s (第 %d/%d 次, 延迟 %.2fs): %s",
                        error_type.value,
                        func.__qualname__,
                        attempt + 1,
                        max_retries,
                        delay,
                        exc,
                    )

                    time.sleep(delay)

            # 理论上不会到这里，但类型检查要求有 return
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]
    return decorator


def async_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    on_retry: Optional[Callable[[int, float, BaseException], None]] = None,
) -> Callable[[F], F]:
    """异步函数的重试装饰器（指数退避 + 可选抖动）。

    用法与 retry_with_backoff 完全一致，区别在于内部使用 asyncio.sleep
    以避免阻塞事件循环。

    参数:
        max_retries: 最大重试次数（默认 3）。
        base_delay: 基础延迟秒数（默认 1.0）。
        max_delay: 最大延迟秒数（默认 60.0）。
        backoff_factor: 退避倍数（默认 2.0）。
        jitter: 是否添加随机抖动（默认 True）。
        on_retry: 每次重试前的回调，参数为 (attempt, delay, exception)。
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[BaseException] = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    error_type = classify_error(exc)

                    if attempt >= max_retries:
                        log.warning(
                            "异步重试耗尽 [%s] %s (已尝试 %d 次): %s",
                            error_type.value,
                            func.__qualname__,
                            attempt,
                            exc,
                        )
                        raise

                    if not is_retryable(error_type):
                        log.info(
                            "不可重试的异步错误 [%s] %s，直接抛出: %s",
                            error_type.value,
                            func.__qualname__,
                            exc,
                        )
                        raise

                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    if jitter:
                        delay = random.uniform(0, delay)

                    if on_retry is not None:
                        on_retry(attempt + 1, delay, exc)

                    log.info(
                        "异步重试 [%s] %s (第 %d/%d 次, 延迟 %.2fs): %s",
                        error_type.value,
                        func.__qualname__,
                        attempt + 1,
                        max_retries,
                        delay,
                        exc,
                    )

                    await asyncio.sleep(delay)

            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]
    return decorator


__all__ = [
    "retry_with_backoff",
    "async_retry",
]
