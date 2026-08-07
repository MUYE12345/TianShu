"""MCP工具管理服务

- 内置 MCP 工具(web_search/weather/crawler/paper)启动即注册
- 外部 MCP 服务器(stdio/http/sse): register_server 连接并注册其工具, 配置持久化
"""
import asyncio
import concurrent.futures
import json
import threading
import time
from typing import Any

from backend.config import DATA_DIR
from backend.core.logger import log
from agent.mcp.mcp_integration import register_mcp_tools
from agent.tools.registry import list_tools, get_tool, register_tool, unregister_tool

_DEFAULT_MCP_TIMEOUT = 30.0
_SERVERS_FILE = DATA_DIR / "mcp_servers.json"


class MCPService:
    def __init__(self):
        self._initialized = False
        self._servers: dict[str, dict] = {}   # name -> {type, command/url, args, env, enabled}
        self._sessions: dict[str, dict] = {}  # name -> {"loop", "session", "tools": [注册的工具名]}
        self._load_servers()

    # ── 持久化 ──
    def _load_servers(self):
        try:
            if _SERVERS_FILE.exists():
                self._servers = json.loads(_SERVERS_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            self._servers = {}

    def _save_servers(self):
        try:
            _SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _SERVERS_FILE.write_text(json.dumps(self._servers, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    def initialize(self):
        if self._initialized:
            return
        register_mcp_tools()
        self._initialized = True
        mcp_tools = list_tools(category="mcp")
        log.info("已注册 %d 个MCP工具", len(mcp_tools))
        # 恢复持久化的外部 MCP 服务器(后台连接, 失败不阻塞启动)
        for name, entry in list(self._servers.items()):
            if entry.get("enabled", True):
                self.register_server(name, entry)

    def get_mcp_tools(self) -> list:
        self.initialize()
        return list_tools(category="mcp")

    def get_servers(self) -> dict:
        """已注册的外部 MCP 服务器配置(供市场展示/管理)。"""
        return dict(self._servers)

    # ── 外部 MCP 服务器 ──
    def register_server(self, name: str, entry: dict) -> bool:
        """注册外部 MCP 服务器: 持久化配置 + 后台连接注册其工具。失败不阻塞返回。"""
        name = (name or "").strip()
        if not name:
            return False
        self._servers[name] = entry
        self._save_servers()
        threading.Thread(target=self._connect_server, args=(name, entry), daemon=True).start()
        return True

    def remove_server(self, name: str) -> bool:
        """移除外部 MCP 服务器: 反注册其工具 + 删除配置。不存在返回 False。"""
        removed = False
        if name in self._servers:
            del self._servers[name]
            self._save_servers()
            removed = True
        info = self._sessions.pop(name, None)
        if info:
            for tool_name in info.get("tools", []):
                try:
                    unregister_tool(tool_name)
                except Exception:  # noqa: BLE001
                    pass
            removed = True
        return removed

    def _connect_server(self, name: str, entry: dict):
        try:
            asyncio.run(self._connect_async(name, entry))
        except Exception as e:  # noqa: BLE001
            log.warning("MCP 服务器 %s 连接失败: %s", name, e)

    async def _connect_async(self, name: str, entry: dict):
        from mcp import ClientSession, StdioServerParameters
        loop = asyncio.get_running_loop()

        async def _session_loop(read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                registered = []
                for t in tools.tools:
                    tn = self._register_server_tool(name, t, session, loop)
                    if tn:
                        registered.append(tn)
                self._sessions[name] = {"loop": loop, "session": session, "tools": registered}
                log.info("MCP 服务器 %s 已连接, 注册 %d 个工具", name, len(registered))
                # 保持会话存活
                await asyncio.Event().wait()

        if entry.get("type") == "stdio":
            from mcp.client.stdio import stdio_client
            params = StdioServerParameters(
                command=entry.get("command", ""),
                args=entry.get("args", []),
                env=entry.get("env") or None,
            )
            async with stdio_client(params) as (read, write):
                await _session_loop(read, write)
        else:  # http / sse
            from mcp.client.sse import sse_client
            url = entry.get("url", "")
            async with sse_client(url) as (read, write):
                await _session_loop(read, write)

    def _register_server_tool(self, server_name: str, tool, session, loop) -> str:
        """把外部 MCP 工具注册为可调用的 SimpleTool(线程安全调用回服务器事件循环)。"""
        tool_name = f"{server_name}_{tool.name}"
        t = tool

        def handler(**kwargs):
            try:
                future = asyncio.run_coroutine_threadsafe(
                    session.call_tool(t.name, arguments=kwargs), loop)
                result = future.result(timeout=_DEFAULT_MCP_TIMEOUT)
                parts = []
                for c in (result.content or []):
                    ctype = getattr(c, "type", "")
                    if ctype == "text":
                        parts.append(getattr(c, "text", ""))
                    elif ctype == "image":
                        parts.append("[图片]")
                    else:
                        parts.append(str(c))
                return "\n".join(parts) if parts else "(无内容)"
            except Exception as e:  # noqa: BLE001
                return f"MCP 调用失败: {e}"

        register_tool(name=tool_name,
                      description=(t.description or tool_name)[:200],
                      parameters={"type": "object", "properties": {}, "required": []},
                      handler=handler,
                      category="mcp")
        return tool_name

    def execute_tool(self, name: str, timeout: float = _DEFAULT_MCP_TIMEOUT, **kwargs: Any) -> dict:
        """执行MCP工具，带超时控制和结构化错误处理。"""
        tool = get_tool(name)
        if not tool:
            return {"success": False, "error": f"工具不存在: {name}", "tool": name, "timeout": timeout}
        if not tool.get("enabled", True):
            return {"success": False, "error": f"工具已禁用: {name}", "tool": name, "timeout": timeout}
        handler = tool["handler"]
        start = time.time()
        log.info("MCP工具调用 [%s] args=%s timeout=%.0fs", name, kwargs, timeout)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(handler, **kwargs)
                raw = future.result(timeout=timeout)
            elapsed = round(time.time() - start, 2)
            log.info("MCP工具完成 [%s] %.2fs", name, elapsed)
            return {"success": True, "result": str(raw), "tool": name, "timeout": timeout, "elapsed": elapsed}
        except concurrent.futures.TimeoutError:
            return {"success": False, "error": f"工具执行超时: {name} 超过 {timeout:.0f} 秒", "tool": name, "timeout": timeout}
        except Exception as exc:
            return {"success": False, "error": f"执行错误: {exc}", "tool": name, "timeout": timeout}


mcp_service = MCPService()
