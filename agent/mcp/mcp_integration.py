"""
MCP工具集成器 — 将MCP Server工具注册到Agent工具注册表
"""
from agent.tools.registry import register_tool
from agent.mcp.web_search.search_mcp import web_search_handler
from agent.mcp.weather.weather_mcp import weather_handler
from agent.mcp.web_crawler.crawler_mcp import crawl_handler


def create_mcp_tool(name: str, description: str, parameters: dict, handler) -> None:
    """将MCP工具注册到内部工具注册表"""
    register_tool(
        name=name,
        description=description,
        parameters=parameters,
        handler=handler,
        category="mcp",
    )


def _register_paper_search():
    """注册论文搜索工具 (通过paper_mcp模块导入触发register_tool)"""
    from backend.core.logger import log
    try:
        import agent.mcp.paper_search.paper_mcp  # noqa: F401
    except Exception as e:
        log.warning("论文搜索注册失败: %s", e)


def register_mcp_tools():
    """注册所有可用的MCP工具到注册表"""
    _register_web_search()
    _register_weather()
    _register_web_crawler()
    _register_paper_search()


def _register_web_search():
    """注册搜索引擎工具"""
    create_mcp_tool(
        name="web_search",
        description="搜索互联网, 支持百度/必应/Google。可用于查找最新信息、新闻、资料等。",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "engine": {"type": "string", "enum": ["auto", "baidu", "bing", "google"], "default": "auto"},
                "count": {"type": "integer", "default": 10},
            },
            "required": ["query"]
        },
        handler=web_search_handler,
    )


def _register_weather():
    """注册天气预报工具"""
    create_mcp_tool(
        name="get_weather",
        description="获取天气预报和天气建议(带伞/穿衣/防晒)",
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名，如北京、上海"},
            },
            "required": ["city"]
        },
        handler=weather_handler,
    )


def _register_web_crawler():
    """注册网页抓取工具"""
    create_mcp_tool(
        name="crawl_webpage",
        description="抓取网页内容并提取正文文本",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要抓取的网页URL"},
            },
            "required": ["url"]
        },
        handler=crawl_handler,
    )


class MCPToolWrapper:
    """MCP工具包装器"""
    pass
