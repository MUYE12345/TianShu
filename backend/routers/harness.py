"""
安全围栏管理路由 — 查看/控制 Agent 工具执行策略与审计

用途: 危险工具默认被禁止(safe_mode), 可在此查看被拦截记录/一键熔断/调整策略。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.core.security import get_current_user
from agent.harness.harness import tool_harness

router = APIRouter()


class _ToggleBody(BaseModel):
    enabled: bool = True


class _BlockToolBody(BaseModel):
    name: str
    blocked: bool = True


@router.get("/status")
def get_status(current_user = Depends(get_current_user)):
    """围栏策略与统计"""
    return tool_harness.status()


@router.get("/audit")
def get_audit(n: int = 50, current_user = Depends(get_current_user)):
    """最近工具调用审计(含被拦截记录)"""
    n = max(1, min(n, 500))
    return {"items": tool_harness.recent_audit(n)}


@router.post("/safe-mode")
def set_safe_mode(body: _ToggleBody, current_user = Depends(get_current_user)):
    """开关安全模式: 开启后禁止危险工具(任意命令/代码执行)"""
    tool_harness.set_safe_mode(body.enabled)
    return {"safe_mode": body.enabled}


@router.post("/emergency-stop")
def set_emergency_stop(body: _ToggleBody, current_user = Depends(get_current_user)):
    """紧急熔断: 一键暂停全部工具执行"""
    tool_harness.set_emergency_stop(body.enabled)
    return {"emergency_stop": body.enabled}


@router.post("/path-fence")
def set_path_fence(body: _ToggleBody, current_user = Depends(get_current_user)):
    """开关路径围栏: 写文件/工作目录限制在项目根内"""
    tool_harness.set_path_fence(body.enabled)
    return {"path_fence": body.enabled}


@router.post("/block-tool")
def block_tool(body: _BlockToolBody, current_user = Depends(get_current_user)):
    """单独禁用/放行某个工具"""
    tool_harness.block_tool(body.name, body.blocked)
    return {"blocked_tools": sorted(tool_harness.blocked_tools)}
