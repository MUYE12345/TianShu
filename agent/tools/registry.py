"""
工具注册表 — 纯Python实现, 无LangChain依赖

每个工具模块在导入时调用 register_tool() 自我注册
discover_tools() 在启动时遍历所有工具模块触发注册
"""
import concurrent.futures
import threading
import time
from typing import List, Dict, Callable, Optional

# 全局注册表
_TOOL_REGISTRY: Dict[str, dict] = {}
_REGISTRY_LOCK = threading.Lock()


def _is_transient_error(exc: Exception) -> bool:
    """判断是否是暂时性错误（网络超时、连接错误等），可重试一次。"""
    try:
        from backend.core.error_classifier import classify_error, is_retryable
        return is_retryable(classify_error(exc))
    except ImportError:
        # 降级：基于关键词简单判断
        msg = str(exc).lower()
        transient_keywords = (
            "timeout", "timed out", "connection", "network",
            "econnrefused", "econnreset", "temporary",
            "rate limit", "too many", "503", "502", "504",
        )
        return any(kw in msg for kw in transient_keywords)


class SimpleTool:
    """简易工具包装(替代LangChain StructuredTool)"""

    def __init__(self, name: str, description: str, fn: Callable):
        self.name = name
        self.description = description
        self._run = fn

    def invoke(self, kwargs: dict = None) -> str:
        """执行工具（带30秒超时、一次重试、日志与耗时统计）"""
        kwargs = kwargs or {}
        start_time = time.time()
        tool_name = self.name

        # 懒加载 logger 以避免循环导入
        try:
            from backend.core.logger import log
        except ImportError:
            log = None

        if log:
            log.info("工具调用开始 [%s] args=%s", tool_name, kwargs)

        def _run_in_thread() -> str:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self._run, **kwargs)
                return future.result(timeout=30)

        try:
            result = _run_in_thread()
        except concurrent.futures.TimeoutError:
            elapsed = time.time() - start_time
            if log:
                log.warning("工具执行超时 [%s] %.2fs > 30s", tool_name, elapsed)
            return f"[工具执行超时: {tool_name} > 30s]"
        except TypeError as e:
            elapsed = time.time() - start_time
            if log:
                log.warning("工具参数错误 [%s] %.2fs: %s", tool_name, elapsed, e)
            return f"参数错误: {e}"
        except Exception as e:
            elapsed = time.time() - start_time
            # Fix 2: 对暂时性错误尝试重试一次
            # 但不重试 "工具不存在" 或 "参数错误"（已被上面的 TypeError 捕获）
            if _is_transient_error(e):
                if log:
                    log.info("工具暂时性错误，重试一次 [%s] %.2fs: %s", tool_name, elapsed, e)
                try:
                    result = _run_in_thread()
                    elapsed = time.time() - start_time
                    if log:
                        log.info("工具重试成功 [%s] %.2fs", tool_name, elapsed)
                    return str(result)
                except concurrent.futures.TimeoutError:
                    elapsed = time.time() - start_time
                    if log:
                        log.warning("工具重试也超时 [%s] %.2fs > 30s", tool_name, elapsed)
                    return f"[工具执行超时: {tool_name} > 30s]"
                except Exception as retry_e:
                    elapsed = time.time() - start_time
                    if log:
                        log.error("工具重试也失败 [%s] %.2fs: %s", tool_name, elapsed, retry_e)
                    return f"执行错误: {retry_e}"

            if log:
                log.error("工具执行失败 [%s] %.2fs: %s", tool_name, elapsed, e)
            return f"执行错误: {e}"

        # Fix 3: 记录耗时，标记慢工具(>5s)
        elapsed = time.time() - start_time
        if log:
            if elapsed > 5:
                log.warning("工具执行较慢 [%s] %.2fs > 5s", tool_name, elapsed)
            else:
                log.info("工具调用完成 [%s] %.2fs", tool_name, elapsed)
        return str(result)


def register_tool(
    name: str,
    description: str,
    parameters: dict,
    handler: Callable,
    category: str = "general",
    enabled: bool = True,
):
    """注册一个工具到全局注册表"""
    with _REGISTRY_LOCK:
        _TOOL_REGISTRY[name] = {
        "name": name,
        "description": description,
        "parameters": parameters,
        "handler": handler,
        "category": category,
        "enabled": enabled,
    }


def unregister_tool(name: str):
    """卸载工具"""
    with _REGISTRY_LOCK:
        _TOOL_REGISTRY.pop(name, None)


def get_tool(name: str) -> Optional[dict]:
    """获取工具信息"""
    with _REGISTRY_LOCK:
        return _TOOL_REGISTRY.get(name)


def list_tools(category: str = None, enabled_only: bool = True) -> List[dict]:
    """列出工具"""
    with _REGISTRY_LOCK:
        tools = list(_TOOL_REGISTRY.values())
    if category:
        tools = [t for t in tools if t["category"] == category]
    if enabled_only:
        tools = [t for t in tools if t["enabled"]]
    return tools


def get_simple_tools(enabled_only: bool = True) -> List[SimpleTool]:
    """获取SimpleTool列表(供Agent调用)"""
    with _REGISTRY_LOCK:
        values = list(_TOOL_REGISTRY.values())
    tools = []
    for info in values:
        if enabled_only and not info["enabled"]:
            continue
        tools.append(SimpleTool(
            name=info["name"],
            description=info["description"],
            fn=info["handler"],
        ))
    return tools


def get_tool_descriptions(enabled_only: bool = True) -> str:
    """获取工具描述的文本(供LLM提示词使用)"""
    with _REGISTRY_LOCK:
        values = list(_TOOL_REGISTRY.values())
    lines = []
    for info in values:
        if enabled_only and not info["enabled"]:
            continue
        params = info.get("parameters", {}).get("properties", {})
        param_desc = ", ".join(f"{k}" for k in params.keys())
        lines.append(f"- {info['name']}({param_desc}): {info['description'][:80]}")
    return "\n".join(lines)


def discover_tools():
    """自动发现并导入所有工具模块"""
    import importlib
    import pkgutil
    import agent.tools as tools_pkg
    from backend.core.logger import log

    for importer, modname, ispkg in pkgutil.walk_packages(
        tools_pkg.__path__, f"{tools_pkg.__name__}."
    ):
        if not ispkg:
            try:
                importlib.import_module(modname)
            except Exception as e:
                log.warning("工具加载失败 %s: %s", modname, e)
