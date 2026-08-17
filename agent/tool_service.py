"""
工具管理服务 — 负责工具的加载/启用/禁用/查询
"""
from typing import List
from backend.core.logger import log
from agent.tools.registry import (
    _TOOL_REGISTRY, list_tools, get_tool,
    get_simple_tools, get_tool_descriptions, discover_tools
)


class ToolService:
    """工具管理服务"""

    def __init__(self):
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return
        discover_tools()
        self._initialized = True
        log.info("已加载 %d 个工具", len(_TOOL_REGISTRY))

    def get_all_tools(self) -> List[dict]:
        self.initialize()
        return list_tools(enabled_only=False)

    def get_enabled_tools(self) -> List[dict]:
        self.initialize()
        return list_tools(enabled_only=True)

    def get_simple_tools(self):
        self.initialize()
        return get_simple_tools()

    def get_tool_descriptions(self) -> str:
        self.initialize()
        return get_tool_descriptions()

    def enable_tool(self, name: str):
        tool = _TOOL_REGISTRY.get(name)
        if tool:
            tool["enabled"] = True

    def disable_tool(self, name: str):
        tool = _TOOL_REGISTRY.get(name)
        if tool:
            tool["enabled"] = False

    def execute_tool(self, name: str, **kwargs) -> str:
        tool = _TOOL_REGISTRY.get(name)
        if not tool:
            return f"工具不存在: {name}"
        if not tool["enabled"]:
            return f"工具已禁用: {name}"
        # 安全围栏: 直连执行也走校验与审计
        try:
            from agent.harness.harness import tool_harness
            allowed, reason = tool_harness.check(name, kwargs, tool.get("category", "general"))
            if not allowed:
                tool_harness.record(name, kwargs, False, reason)
                return f"[安全围栏拦截] {reason}"
            result = tool["handler"](**kwargs)
            tool_harness.record(name, kwargs, True, result=str(result))
            return result
        except Exception:
            pass
        return tool["handler"](**kwargs)


tool_service = ToolService()
