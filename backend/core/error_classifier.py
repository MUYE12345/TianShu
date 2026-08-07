"""
Agent 错误分类与处理

根据常见的 agent / LLM / 工具调用场景对异常进行分类，并提供
统一的 classify_error 入口和重试性判断。

用法:
  from backend.core.error_classifier import classify_error, is_retryable, AgentError

  try:
      result = await agent.run(task)
  except Exception as exc:
      err_type = classify_error(exc)
      if is_retryable(err_type):
          ...  # 重试逻辑
"""
import enum
import logging
import socket
from typing import Optional

from backend.core.logger import log

# ---------------------------------------------------------------------------
# 错误类型枚举
# ---------------------------------------------------------------------------

class AgentErrorType(enum.Enum):
    """Agent 执行过程中可能遇到的错误类型分类。"""
    RATE_LIMIT = "rate_limit"       # 频率限制 / 配额超限
    AUTH_ERROR = "auth_error"       # 认证 / 授权失败
    MODEL_ERROR = "model_error"     # 模型响应异常（空返回、格式异常、拒绝等）
    TOOL_ERROR = "tool_error"       # 工具 / MCP 调用失败
    TIMEOUT = "timeout"             # 网络 / 调用超时
    UNKNOWN = "unknown"             # 无法归类的错误

# ---------------------------------------------------------------------------
# 自定义异常
# ---------------------------------------------------------------------------

class AgentError(Exception):
    """Agent 层自定义异常的基类。

    属性:
        error_type: AgentErrorType 枚举，标识错误类别。
        message: 人类可读的错误描述。
        retryable: 该错误是否可以通过重试解决（仅作为快捷标记，
                   完整判断请使用 is_retryable() 函数）。
        cause: 原始异常（可选），用于异常链。
    """

    def __init__(
        self,
        error_type: AgentErrorType,
        message: str = "",
        retryable: bool = False,
        cause: Optional[BaseException] = None,
    ):
        self.error_type = error_type
        self.retryable = retryable
        self.cause = cause
        super().__init__(message)

    @property
    def message(self) -> str:
        return str(self.args[0]) if self.args else ""


# ---------------------------------------------------------------------------
# 分类规则（关键词 + 类型双匹配）
# ---------------------------------------------------------------------------

# 频率限制 / 429 相关信号
_RATE_LIMIT_SIGNALS: tuple = (
    "rate limit", "rate_limit", "too many requests",
    "429", "quota exceeded", "request limit",
    "retry after", "retry-after",
)

# 认证 / 授权相关信号
_AUTH_ERROR_SIGNALS: tuple = (
    "unauthorized", "unauthorised", "forbidden", "invalid key",
    "invalid api key", "invalid token", "token expired",
    "authentication failed", "auth failed",
    "permission denied", "access denied", "not authorized",
    "401", "403",
)

# 模型响应异常信号
_MODEL_ERROR_SIGNALS: tuple = (
    "model not found", "model error", "model overloaded",
    "empty response", "null response", "content filter",
    "safety", "refuse to answer", "context length",
    "max tokens", "tokens limit", "token limit",
    "bad gateway", "502", "503", "504",
    "internal server error", "server error",
)

# 工具调用失败信号
_TOOL_ERROR_SIGNALS: tuple = (
    "tool error", "tool call failed", "tool execution",
    "mcp error", "mcp timeout", "invalid tool",
    "tool not found", "tool input", "tool output",
)

# 超时信号
_TIMEOUT_SIGNALS: tuple = (
    "timeout", "timed out", "deadline exceeded",
    "connection timeout", "read timeout",
    "connect timeout", "write timeout",
)

# 重试性白名单：这些类型的错误通常可以通过重试解决
_RETRYABLE_TYPES: frozenset = frozenset({
    AgentErrorType.RATE_LIMIT,
    AgentErrorType.TIMEOUT,
})


def _match_signals(exc: BaseException, signals: tuple) -> bool:
    """检查异常消息中是否包含任意信号关键词（大小写不敏感）。"""
    msg = str(exc).lower()
    for signal in signals:
        if signal in msg:
            return True
    return False


def _classify_by_type(exc: BaseException) -> Optional[AgentErrorType]:
    """根据异常的类型 / 继承链进行快速分类。"""
    exc_full_name = f"{type(exc).__module__}.{type(exc).__qualname__}".lower()

    # --- 超时 ---
    if isinstance(exc, TimeoutError):
        return AgentErrorType.TIMEOUT
    # socket.timeout 在 Py3 中也是 TimeoutError 的子类，但兜底检查
    if isinstance(exc, socket.timeout):
        return AgentErrorType.TIMEOUT
    # httpx / requests 超时
    if "timeout" in exc_full_name:
        return AgentErrorType.TIMEOUT

    # --- 认证 ---
    if isinstance(exc, PermissionError):
        return AgentErrorType.AUTH_ERROR

    # --- 频率限制 ---
    if "rate" in exc_full_name or "throttle" in exc_full_name:
        return AgentErrorType.RATE_LIMIT

    return None


def classify_error(exc: BaseException) -> AgentErrorType:
    """将任意异常分类为 AgentErrorType 枚举值。

    匹配优先级: AgentError 直接标记 > 异常类型继承链 > 消息关键词匹配。
    """
    # 1. 如果已经是 AgentError，直接返回标记的类型
    if isinstance(exc, AgentError):
        return exc.error_type

    # 2. 按异常类型 / 继承链匹配
    type_result = _classify_by_type(exc)
    if type_result is not None:
        return type_result

    # 3. 按错误消息关键词匹配
    if _match_signals(exc, _TIMEOUT_SIGNALS):
        return AgentErrorType.TIMEOUT
    if _match_signals(exc, _RATE_LIMIT_SIGNALS):
        return AgentErrorType.RATE_LIMIT
    if _match_signals(exc, _AUTH_ERROR_SIGNALS):
        return AgentErrorType.AUTH_ERROR
    if _match_signals(exc, _MODEL_ERROR_SIGNALS):
        return AgentErrorType.MODEL_ERROR
    if _match_signals(exc, _TOOL_ERROR_SIGNALS):
        return AgentErrorType.TOOL_ERROR

    # 4. 兜底：记一条日志然后返回 UNKNOWN
    log.warning("无法分类的异常: %s: %s", type(exc).__qualname__, exc)
    return AgentErrorType.UNKNOWN


def is_retryable(error_type: AgentErrorType) -> bool:
    """判断某个错误类型是否可以通过重试解决。

    目前可重试的错误类型：
      - RATE_LIMIT（等待后重试通常可恢复）
      - TIMEOUT（偶发网络波动）

    其他类型（认证失败、模型拒绝、工具不存在等）不应盲目重试。
    """
    return error_type in _RETRYABLE_TYPES


__all__ = [
    "AgentErrorType",
    "AgentError",
    "classify_error",
    "is_retryable",
]
