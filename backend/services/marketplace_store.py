"""
市场状态持久化 — 工具/MCP/SKILL 三市场的安装/启用状态。

状态存 data/marketplace.json, 重启后保留:
  tools : { tool_id: {enabled: bool} }
  mcp   : { mcp_id: {installed: bool} }
  skills: { skill_id: {installed: bool, enabled: bool} }
"""
import json
from backend.config import DATA_DIR

STATE_FILE = DATA_DIR / "marketplace.json"


class MarketplaceStore:
    def __init__(self):
        self._state = {"tools": {}, "mcp": {}, "skills": {}}
        self._load()

    def _load(self):
        try:
            if STATE_FILE.exists():
                self._state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            self._state = {"tools": {}, "mcp": {}, "skills": {}}
        for k in ("tools", "mcp", "skills"):
            self._state.setdefault(k, {})

    def save(self):
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(self._state, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    # ── 工具 ──
    def tool_enabled(self, tool_id: str) -> bool:
        return self._state["tools"].get(tool_id, {}).get("enabled", True)

    def set_tool(self, tool_id: str, enabled: bool):
        self._state["tools"][tool_id] = {"enabled": enabled}
        self.save()

    # ── MCP ──
    def mcp_installed(self, mcp_id: str) -> bool:
        return self._state["mcp"].get(mcp_id, {}).get("installed", False)

    def set_mcp(self, mcp_id: str, installed: bool):
        self._state["mcp"][mcp_id] = {"installed": installed}
        self.save()

    # ── SKILL ──
    def skill_installed(self, skill_id: str) -> bool:
        return self._state["skills"].get(skill_id, {}).get("installed", False)

    def skill_enabled(self, skill_id: str) -> bool:
        return self._state["skills"].get(skill_id, {}).get("enabled", True)

    def set_skill(self, skill_id: str, installed: bool = None, enabled: bool = None):
        s = self._state["skills"].setdefault(skill_id, {})
        if installed is not None:
            s["installed"] = installed
        if enabled is not None:
            s["enabled"] = enabled
        self.save()

    def snapshot(self) -> dict:
        return json.loads(json.dumps(self._state))


marketplace_store = MarketplaceStore()


# ═══════════════ 三市场目录(供路由与启动状态应用共享) ═══════════════

# MCP 市场: 内置(启动注册真实 handler) + 社区(安装时注册, 配置驱动)
MCP_MARKETPLACE = [
    {"id": "web-search", "name": "web_search", "title": "网络搜索",
     "description": "集成百度、必应、Google 搜索引擎，让 Agent 具备实时检索能力",
     "author": "Tianzhi", "version": "1.0.0", "tags": ["搜索", "信息检索"], "builtin": True},
    {"id": "weather", "name": "get_weather", "title": "天气预报",
     "description": "查询今日天气详情，包括温度、湿度、风力、穿衣建议等",
     "author": "Tianzhi", "version": "1.0.0", "tags": ["天气", "生活"], "builtin": True},
    {"id": "web-crawler", "name": "crawl_webpage", "title": "网页爬取",
     "description": "根据指定 URL 爬取网页内容，支持动态渲染页面",
     "author": "Tianzhi", "version": "1.0.0", "tags": ["爬虫", "数据采集"], "builtin": True},
    {"id": "arxiv", "name": "search_papers", "title": "论文搜索",
     "description": "搜索 arXiv 学术论文，根据标题或作者查找",
     "author": "Tianzhi", "version": "1.0.0", "tags": ["学术", "论文"], "builtin": True},
    {"id": "github-tools", "name": "github_query", "title": "GitHub 工具集",
     "description": "查询 GitHub 仓库 Issues 与仓库列表(需 GITHUB_TOKEN)",
     "author": "Community", "version": "0.9.0", "tags": ["开发", "Git"], "builtin": False},
    {"id": "slack-connector", "name": "slack_send", "title": "Slack 连接器",
     "description": "向 Slack 频道发送消息(需 SLACK_TOKEN)",
     "author": "Community", "version": "1.2.0", "tags": ["通讯", "协作"], "builtin": False},
    {"id": "jira-integration", "name": "jira_query", "title": "JIRA 集成",
     "description": "查询 JIRA 项目工单(需 JIRA_BASE/JIRA_EMAIL/JIRA_TOKEN)",
     "author": "Community", "version": "0.8.0", "tags": ["项目管理", "工单"], "builtin": False},
    {"id": "sql-query", "name": "sql_query", "title": "SQL 查询器",
     "description": "对本地 SQLite 数据库执行 SQL 查询",
     "author": "Community", "version": "1.1.0", "tags": ["数据库", "分析"], "builtin": False},
]

# SKILL 市场: 内置(映射真实技能目录) + 社区(安装时创建 SKILL.md)
SKILL_BUILTIN_MARKET = {
    "news-digest": "daily-news",
    "paper-analysis": "paper-analyzer",
    "wiki-creator": "wiki-creator",
}
SKILL_COMMUNITY_IDS = ["code-review", "data-visualizer", "email-composer"]
