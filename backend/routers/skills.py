"""SKILL管理路由 + 市场(真实安装/启用 + 持久化)

- 市场目录 = 真实 skill_manager 技能 + 社区技能(安装时创建真实 SKILL.md)
- install   → 创建/确保 SKILL.md 并重载 skill_manager
- enable    → 真实切换技能启用状态
- 状态持久化到 data/marketplace.json
"""
from fastapi import APIRouter, HTTPException, Depends

from backend.services.marketplace_store import (
    marketplace_store, SKILL_BUILTIN_MARKET, SKILL_COMMUNITY_IDS,
)
from backend.core.security import get_current_user

router = APIRouter()

BUILTIN_MARKET = SKILL_BUILTIN_MARKET
COMMUNITY_IDS = SKILL_COMMUNITY_IDS


def _skill_manager():
    from agent.skills.skill_manager import skill_manager
    return skill_manager


def _apply_persisted():
    """把持久化的技能启用状态应用到 skill_manager。"""
    sm = _skill_manager()
    for sid in COMMUNITY_IDS + list(BUILTIN_MARKET.keys()):
        real = BUILTIN_MARKET.get(sid, sid)
        if sm.get_skill(real) and not marketplace_store.skill_enabled(sid):
            sm.set_enabled(real, False)


@router.get("")
def list_skills():
    """列出所有已安装的SKILL(真实 skill_manager, 不含缓存目录)"""
    _apply_persisted()
    sm = _skill_manager()
    return {"items": sm.list_skills()}


@router.get("/marketplace")
def list_skill_marketplace():
    """列出技能市场: 真实技能 + 社区技能, 含真实安装/启用状态"""
    _apply_persisted()
    sm = _skill_manager()
    items = []
    for sid, real in BUILTIN_MARKET.items():
        skill = sm.get_skill(real)
        if skill:
            items.append({
                "id": sid, "name": real, "title": skill.description[:30] or sid,
                "description": skill.description, "author": "Tianzhi",
                "version": getattr(skill, "version", "1.0.0"), "tags": [],
                "installed": True, "enabled": skill.enabled,
                "deletable": False,
            })
    from agent.skills.community_skills import COMMUNITY_SKILLS
    for cid in COMMUNITY_IDS:
        # 从 SKILL.md frontmatter 读真实描述
        desc = COMMUNITY_SKILLS.get(cid, "")
        name_line = next((l for l in desc.splitlines() if l.startswith("description:")), "")
        desc_text = name_line.split(":", 1)[1].strip() if name_line else cid
        real = sm.get_skill(cid)
        items.append({
            "id": cid, "name": cid, "title": cid.replace("-", " ").title(),
            "description": desc_text, "author": "Community",
            "version": "1.0.0", "tags": [],
            "installed": marketplace_store.skill_installed(cid),
            "enabled": marketplace_store.skill_enabled(cid),
            "deletable": True,
        })
    return {"items": items}


def _find(skill_id: str):
    if skill_id in BUILTIN_MARKET:
        return BUILTIN_MARKET[skill_id]
    if skill_id in COMMUNITY_IDS:
        return skill_id
    return None


@router.post("/install")
def install_skill(current_user = Depends(get_current_user), body: dict = None):
    """安装技能: 社区技能创建真实 SKILL.md + 重载; 内置确认存在"""
    skill_id = (body.get("id") or body.get("name", "")).strip()
    real = _find(skill_id)
    if not real:
        raise HTTPException(404, detail=f"未找到技能: {skill_id}")
    if skill_id in COMMUNITY_IDS:
        from agent.skills.community_skills import install_community_skill
        if not install_community_skill(skill_id):
            raise HTTPException(500, detail=f"技能创建失败: {skill_id}")
        _skill_manager().reload()
    marketplace_store.set_skill(skill_id, installed=True, enabled=True)
    return {"message": f"安装成功: {skill_id}", "success": True, "name": real}


@router.post("/{skill_id}/install")
def install_skill_by_id(skill_id: str, current_user = Depends(get_current_user)):
    """安装技能(前端用 /{id}/install 路径)"""
    return install_skill({"id": skill_id})


@router.post("/{skill_id}/uninstall")
def uninstall_skill_by_id(skill_id: str, current_user = Depends(get_current_user)):
    """卸载技能(前端用 /{id}/uninstall 路径)"""
    return uninstall_skill({"id": skill_id})


@router.post("/uninstall")
def uninstall_skill(current_user = Depends(get_current_user), body: dict = None):
    """卸载技能: 社区技能删除 SKILL.md + 重载; 持久化"""
    skill_id = (body.get("id") or body.get("name", "")).strip()
    if skill_id not in COMMUNITY_IDS:
        return {"message": "内置技能不可卸载(可禁用)", "success": False}, 400
    from agent.skills.community_skills import uninstall_community_skill
    uninstall_community_skill(skill_id)
    _skill_manager().reload()
    marketplace_store.set_skill(skill_id, installed=False, enabled=False)
    return {"message": f"已卸载: {skill_id}", "success": True}


@router.post("/{name}/enable")
def toggle_skill(name: str, current_user = Depends(get_current_user), body: dict = None):
    """启用/禁用SKILL(真实切换, 持久化)"""
    body = body or {}
    enabled = body.get("enabled", True)
    sm = _skill_manager()
    real = _find(name) or name
    if not sm.set_enabled(real, enabled):
        raise HTTPException(404, detail=f"技能不存在: {name}")
    marketplace_store.set_skill(name, enabled=enabled)
    return {"message": f"{'启用' if enabled else '禁用'}成功: {name}", "success": True, "enabled": enabled}
