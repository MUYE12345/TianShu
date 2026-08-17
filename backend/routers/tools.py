"""工具管理路由"""
from fastapi import APIRouter, Depends
from agent.tools.registry import list_tools
from backend.core.security import get_current_user

router = APIRouter()


@router.get("")
def get_tools():
    """列出所有已注册的工具"""
    return {"items": list_tools(enabled_only=False)}


@router.put("/{name}/enable")
def enable_tool(name: str, current_user = Depends(get_current_user), body: dict = None):
    """启用/禁用工具"""
    from agent.tools.registry import _TOOL_REGISTRY
    tool = _TOOL_REGISTRY.get(name)
    if not tool:
        return {"error": "工具不存在"}
    tool["enabled"] = body.get("enabled", True)
    return {"success": True, "name": name, "enabled": tool["enabled"]}

