"""MCP工具管理路由 + 市场(真实安装/卸载 + 持久化)

- 内置工具(web-search/weather/web-crawler/arxiv)启动即注册真实 handler
- 社区工具(github/slack/jira/sql)安装时注册真实 handler(配置驱动), 卸载反注册
- 安装状态持久化到 data/marketplace.json, 重启保留
"""
from fastapi import APIRouter, HTTPException, Depends

from agent.mcp_service import mcp_service
from agent.mcp.community_mcp import register_community_mcp, unregister_community_mcp, MCP_ID_TO_TOOL
from backend.services.marketplace_store import marketplace_store, MCP_MARKETPLACE
from backend.core.security import get_current_user

router = APIRouter()


def _apply_persisted():
    """把持久化的社区工具安装状态应用到注册表(幂等)。"""
    for item in MCP_MARKETPLACE:
        if item["builtin"]:
            continue
        if marketplace_store.mcp_installed(item["id"]):
            register_community_mcp(item["id"])


def _installed(mcp_id: str, builtin: bool) -> bool:
    """内置默认已装; 社区读持久化状态。"""
    if builtin:
        return True
    return marketplace_store.mcp_installed(mcp_id)


@router.get("")
def list_mcp_tools():
    """列出所有已安装的MCP工具(真实注册表)"""
    _apply_persisted()
    return mcp_service.get_mcp_tools()


@router.get("/marketplace")
def list_mcp_marketplace():
    """列出MCP市场中的工具(含真实安装状态)"""
    _apply_persisted()
    items = []
    for it in MCP_MARKETPLACE:
        items.append({**it, "installed": _installed(it["id"], it["builtin"]),
                      "deletable": False})
    # 已注册的外部 MCP 服务器: 可删除/重传(已安装, 不参与 安装/卸载)
    for sname, sentry in mcp_service.get_servers().items():
        items.append({
            "id": sname, "name": sname, "title": sname,
            "description": f"外部 MCP 服务器({sentry.get('type', 'stdio')})",
            "author": "custom", "version": "", "tags": [],
            "installed": True, "deletable": True, "installable": False,
        })
    return {"items": items}


def _find(tool_id: str):
    return next((it for it in MCP_MARKETPLACE if it["id"] == tool_id), None)


@router.post("/install")
def install_mcp_tool(current_user = Depends(get_current_user), body: dict = None):
    """安装MCP工具: 注册真实 handler + 持久化"""
    tool_id = (body.get("id") or body.get("name", "")).strip()
    item = _find(tool_id)
    if not item:
        raise HTTPException(404, detail=f"未找到工具: {tool_id}")
    if not item["builtin"]:
        if not register_community_mcp(item["id"]):
            raise HTTPException(500, detail=f"工具注册失败: {tool_id}")
    marketplace_store.set_mcp(item["id"], True)
    return {"message": f"安装成功: {item['title']}", "success": True, "tool": item["name"]}


@router.post("/{tool_id}/install")
def install_mcp_tool_by_id(tool_id: str, current_user = Depends(get_current_user)):
    """安装MCP工具(前端用 /{id}/install 路径)"""
    return install_mcp_tool({"id": tool_id})


@router.post("/{tool_id}/uninstall")
def uninstall_mcp_tool_by_id(tool_id: str, current_user = Depends(get_current_user)):
    """卸载MCP工具(前端用 /{id}/uninstall 路径)"""
    return uninstall_mcp_tool({"id": tool_id})


@router.post("/uninstall")
def uninstall_mcp_tool(current_user = Depends(get_current_user), body: dict = None):
    """卸载MCP工具: 反注册真实 handler + 持久化"""
    tool_id = (body.get("id") or body.get("name", "")).strip()
    item = _find(tool_id)
    if not item:
        raise HTTPException(404, detail=f"未找到工具: {tool_id}")
    if not item["builtin"]:
        unregister_community_mcp(item["id"])
    else:
        # 内置也允许卸载: 从注册表移除, 重装时由启动逻辑恢复
        try:
            from agent.tools.registry import unregister_tool
            unregister_tool(item["name"])
        except Exception:  # noqa: BLE001
            pass
    marketplace_store.set_mcp(item["id"], False)
    return {"message": f"卸载成功: {item['title']}", "success": True}


@router.delete("/{name}")
def uninstall_mcp_tool_by_name(name: str, current_user = Depends(get_current_user)):
    """卸载MCP工具(通过 id 或 注册名)"""
    tool_id = name
    if name in MCP_ID_TO_TOOL.values():
        tool_id = next((k for k, v in MCP_ID_TO_TOOL.items() if v == name), name)
    item = _find(tool_id)
    if not item:
        raise HTTPException(404, detail="not found")
    if not item["builtin"]:
        unregister_community_mcp(item["id"])
    else:
        try:
            from agent.tools.registry import unregister_tool
            unregister_tool(item["name"])
        except Exception:  # noqa: BLE001
            pass
    marketplace_store.set_mcp(item["id"], False)
    return {"message": f"已卸载: {item['title']}", "success": True}
