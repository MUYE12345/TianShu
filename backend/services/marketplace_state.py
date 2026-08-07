"""
市场持久化状态应用 — 启动时恢复工具启用/禁用、注册已安装社区 MCP、应用技能启用状态。
"""
from backend.core.logger import log


def apply_marketplace_state():
    """启动时应用 data/marketplace.json 中持久化的市场状态。失败不影响启动。"""
    try:
        from agent.tools.registry import _TOOL_REGISTRY
        from backend.services.marketplace_store import (
            marketplace_store, MCP_MARKETPLACE, SKILL_BUILTIN_MARKET, SKILL_COMMUNITY_IDS,
        )

        # 1. 工具: 恢复启用/禁用
        for name, info in list(_TOOL_REGISTRY.items()):
            if not marketplace_store.tool_enabled(name):
                info["enabled"] = False

        # 2. MCP: 注册已安装的社区工具
        from agent.mcp.community_mcp import register_community_mcp
        for item in MCP_MARKETPLACE:
            if not item["builtin"] and marketplace_store.mcp_installed(item["id"]):
                register_community_mcp(item["id"])

        # 3. SKILL: 恢复启用状态
        from agent.skills.skill_manager import skill_manager
        for sid in SKILL_COMMUNITY_IDS + list(SKILL_BUILTIN_MARKET.keys()):
            real = SKILL_BUILTIN_MARKET.get(sid, sid)
            skill = skill_manager.get_skill(real)
            if skill and not marketplace_store.skill_enabled(sid):
                skill.enabled = False

        log.info("[市场] 已恢复持久化安装状态")
    except Exception as e:  # noqa: BLE001
        log.warning("[市场] 恢复状态失败(忽略): %s", e)
