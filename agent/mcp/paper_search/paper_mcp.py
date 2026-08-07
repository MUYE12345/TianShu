"""
arXiv论文搜索MCP Server
"""
from agent.crawlers.arxiv.arxiv_client import ArxivClient
from agent.tools.registry import register_tool

client = ArxivClient()


def search_papers_handler(query: str, max_results: int = 10) -> str:
    """搜索学术论文"""
    import json
    papers = client.search(query, max_results=max_results)
    return json.dumps([{
        "title": p.title, "authors": p.authors[:3],
        "summary": p.summary[:300] + "...",
        "published": p.published, "pdf_url": p.pdf_url,
    } for p in papers], ensure_ascii=False)


def search_by_author_handler(author: str, max_results: int = 10) -> str:
    """按作者搜索"""
    import json
    papers = client.search_by_author(author, max_results)
    return json.dumps([{
        "title": p.title, "published": p.published, "pdf_url": p.pdf_url,
    } for p in papers], ensure_ascii=False)


# 注册为工具
register_tool(
    name="search_papers",
    description="搜索学术论文(arXiv), 按标题或关键词搜索",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "max_results": {"type": "integer", "default": 10},
        },
        "required": ["query"]
    },
    handler=search_papers_handler,
    category="mcp",
)

register_tool(
    name="search_papers_by_author",
    description="按作者搜索学术论文",
    parameters={
        "type": "object",
        "properties": {
            "author": {"type": "string", "description": "作者名"},
            "max_results": {"type": "integer", "default": 10},
        },
        "required": ["author"]
    },
    handler=search_by_author_handler,
    category="mcp",
)
