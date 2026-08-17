"""工具市场路由 — 基于真实注册表, 安装/卸载 = 启用/禁用真实工具 + 持久化"""
from fastapi import APIRouter, HTTPException, Depends

from agent.tools.registry import list_tools, _TOOL_REGISTRY, discover_tools
from backend.services.marketplace_store import marketplace_store
from backend.core.security import get_current_user

router = APIRouter()


def _apply_persisted():
    """把持久化的启用/禁用状态应用到注册表(幂等, 覆盖默认全启用)。"""
    discover_tools()  # 确保全部内置工具已注册(懒加载)
    for name, info in list(_TOOL_REGISTRY.items()):
        if not marketplace_store.tool_enabled(name):
            info["enabled"] = False


@router.get("")
def list_marketplace(kind: str = "all"):
    """列出工具市场: 真实注册表工具(按类别筛选), installed=当前启用状态"""
    _apply_persisted()
    cat_map = {"builtin": "general", "file": "file", "mcp": "mcp", "system": "general",
               "user": "user_uploaded"}
    cat = cat_map.get(kind, kind) if kind != "all" else None
    items = []
    # 1) 核心/内置工具(不含 user_uploaded 的单个函数, 那些按包聚合)
    for info in list_tools(enabled_only=False):
        if info["category"] == "user_uploaded":
            continue
        if cat and info["category"] != cat:
            continue
        items.append({
            "id": info["name"],
            "name": info["name"],
            "title": info["name"].replace("_", " ").title(),
            "description": info["description"],
            "category": info["category"],
            "installed": bool(info.get("enabled", True)),
            "deletable": False,
        })
    # 2) 用户上传的工具包(按上传目录聚合为一张卡, 可删除/重传)
    from backend.config import DATA_DIR
    tools_dir = DATA_DIR / "uploads" / "tools"
    uploaded_names = set()
    if tools_dir.is_dir():
        for d in tools_dir.iterdir():
            if d.is_dir():
                uploaded_names.add(d.name)
    for pkg in sorted(uploaded_names):
        # 只有包里确实注册了工具才展示
        if not any(k.startswith(f"{pkg}_") for k in list(_TOOL_REGISTRY.keys())):
            continue
        items.append({
            "id": pkg, "name": pkg, "title": pkg,
            "description": f"用户上传工具包: {pkg}_*",
            "category": "user_uploaded",
            "installed": True,
            "deletable": True,
            "installable": False,
        })
    return {"items": items, "total": len(items)}


def _set_tool(tool_id: str, enabled: bool):
    info = _TOOL_REGISTRY.get(tool_id)
    if not info:
        return False
    info["enabled"] = enabled
    marketplace_store.set_tool(tool_id, enabled)
    return True


@router.post("/{tool_id}/install")
def install_tool(tool_id: str, current_user = Depends(get_current_user)):
    """安装(启用)工具"""
    if not _set_tool(tool_id, True):
        raise HTTPException(404, detail=f"未找到工具: {tool_id}")
    return {"message": f"安装成功: {tool_id}", "success": True}


@router.post("/{tool_id}/uninstall")
def uninstall_tool(tool_id: str, current_user = Depends(get_current_user)):
    """卸载(禁用)工具"""
    if not _set_tool(tool_id, False):
        raise HTTPException(404, detail=f"未找到工具: {tool_id}")
    return {"message": f"卸载成功: {tool_id}", "success": True}
