"""
社区 MCP 工具 — 真实 handler(配置驱动)。

安装到市场后即注册进工具注册表, Agent 可直接调用:
  sql_query       — 本地 SQLite 查询(真实执行)
  github_query    — GitHub API(需 GITHUB_TOKEN)
  slack_send      — Slack API(需 SLACK_TOKEN)
  jira_query      — JIRA API(需 JIRA_BASE/JIRA_EMAIL/JIRA_TOKEN)

未配置外部凭据时返回明确提示, 不伪装成功。
"""
import json
import os
import sqlite3

import httpx

# 市场 id → 注册工具名
MCP_ID_TO_TOOL = {
    "sql-query": "sql_query",
    "github-tools": "github_query",
    "slack-connector": "slack_send",
    "jira-integration": "jira_query",
}
TOOL_TO_MCP_ID = {v: k for k, v in MCP_ID_TO_TOOL.items()}


# ── SQL 查询(本地 SQLite, 真实执行) ──
def sql_query(query: str = "", db_path: str = ""):
    """对本地 SQLite 数据库执行 SQL 查询, 返回结果行(最多20行)。db_path 默认 data/market_demo.db, 可用环境变量 SQLITE_PATH 指定。"""
    if not (query or "").strip():
        return "参数错误: query 必填"
    path = db_path or os.environ.get("SQLITE_PATH", "") or os.path.join("data", "market_demo.db")
    try:
        conn = sqlite3.connect(path)
    except Exception as e:  # noqa: BLE001
        return f"连接数据库失败: {e}"
    try:
        cur = conn.cursor()
        cur.execute(query)
        if cur.description:
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(20)
            return json.dumps({"columns": cols, "rows": rows}, ensure_ascii=False)
        conn.commit()
        return f"OK, 影响 {cur.rowcount} 行"
    except Exception as e:  # noqa: BLE001
        return f"SQL 执行错误: {e}"
    finally:
        conn.close()


# ── GitHub(配置驱动) ──
def github_query(query_type: str = "issues", repo: str = ""):
    """查询 GitHub 仓库 Issues 或当前用户仓库。需要环境变量 GITHUB_TOKEN。"""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return "未配置 GITHUB_TOKEN, 无法访问 GitHub API。请在环境变量设置后重试。"
    base = "https://api.github.com"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    if query_type == "issues" and repo:
        url = f"{base}/repos/{repo}/issues"
    elif query_type == "repos":
        url = f"{base}/user/repos"
    else:
        return "支持: issues(repo=owner/name) 或 repos"
    try:
        with httpx.Client(timeout=20) as c:
            r = c.get(url, headers=headers)
    except Exception as e:  # noqa: BLE001
        return f"GitHub 请求失败: {e}"
    if r.status_code != 200:
        return f"GitHub API 错误 {r.status_code}: {r.text[:200]}"
    items = r.json()
    if query_type == "repos":
        return json.dumps([{"name": i.get("full_name"), "language": i.get("language")} for i in items[:10]], ensure_ascii=False)
    return json.dumps([{"title": i.get("title"), "state": i.get("state"), "url": i.get("html_url")} for i in items[:10]], ensure_ascii=False)


# ── Slack(配置驱动) ──
def slack_send(message: str = "", channel: str = "general"):
    """向 Slack 频道发送消息。需要环境变量 SLACK_TOKEN。"""
    if not (message or "").strip():
        return "参数错误: message 必填"
    token = os.environ.get("SLACK_TOKEN", "")
    if not token:
        return "未配置 SLACK_TOKEN, 无法发送 Slack 消息。请配置后重试。"
    try:
        with httpx.Client(timeout=20) as c:
            r = c.post("https://slack.com/api/chat.postMessage",
                       headers={"Authorization": f"Bearer {token}"},
                       json={"channel": channel, "text": message})
        d = r.json()
    except Exception as e:  # noqa: BLE001
        return f"Slack 请求失败: {e}"
    return "Slack 消息发送成功" if d.get("ok") else f"Slack 错误: {d.get('error', r.text[:100])}"


# ── JIRA(配置驱动) ──
def jira_query(project: str = "", max_results: int = 10):
    """查询 JIRA 项目工单。需要环境变量 JIRA_BASE/JIRA_EMAIL/JIRA_TOKEN。"""
    base = os.environ.get("JIRA_BASE", "").rstrip("/")
    email = os.environ.get("JIRA_EMAIL", "")
    token = os.environ.get("JIRA_TOKEN", "")
    if not (base and email and token):
        return "未配置 JIRA_BASE/JIRA_EMAIL/JIRA_TOKEN, 无法访问 JIRA。请配置后重试。"
    jql = f"project={project}" if project else "ORDER BY created DESC"
    try:
        with httpx.Client(timeout=20) as c:
            r = c.get(f"{base}/rest/api/2/search",
                      params={"jql": jql, "maxResults": max_results},
                      auth=(email, token), headers={"Accept": "application/json"})
    except Exception as e:  # noqa: BLE001
        return f"JIRA 请求失败: {e}"
    if r.status_code != 200:
        return f"JIRA 错误 {r.status_code}: {r.text[:200]}"
    return json.dumps([{"key": i.get("key"), "summary": i.get("fields", {}).get("summary")}
                       for i in r.json().get("issues", [])], ensure_ascii=False)


# ── 注册/反注册 ──
_COMMUNITY_TOOLS = {
    "sql_query": sql_query,
    "github_query": github_query,
    "slack_send": slack_send,
    "jira_query": jira_query,
}


def register_community_mcp(mcp_id: str):
    """按市场 id 注册对应工具到注册表。"""
    from agent.tools.registry import register_tool
    tool_name = MCP_ID_TO_TOOL.get(mcp_id)
    if not tool_name or tool_name not in _COMMUNITY_TOOLS:
        return False
    register_tool(name=tool_name,
                  description=_COMMUNITY_TOOLS[tool_name].__doc__ or tool_name,
                  parameters=_schema_for(tool_name),
                  handler=_COMMUNITY_TOOLS[tool_name],
                  category="mcp")
    return True


def unregister_community_mcp(mcp_id: str):
    """按市场 id 反注册对应工具。"""
    from agent.tools.registry import unregister_tool
    tool_name = MCP_ID_TO_TOOL.get(mcp_id)
    if tool_name:
        unregister_tool(tool_name)
        return True
    return False


def _schema_for(tool_name: str) -> dict:
    import inspect
    fn = _COMMUNITY_TOOLS[tool_name]
    props, required = {}, []
    for name, param in inspect.signature(fn).parameters.items():
        type_map = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}
        t = getattr(param.annotation, "__name__", "str")
        props[name] = {"type": type_map.get(t, "string"), "description": f"参数 {name}"}
        if param.default == inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}
