"""arXiv API客户端 — 搜索论文"""
from typing import List, Optional
import urllib.parse
import requests
import feedparser


class ArxivPaper:
    def __init__(self, entry_id="", title="", authors=None, summary="",
                 published="", pdf_url="", categories=None):
        self.entry_id = entry_id
        self.title = title
        self.authors = authors or []
        self.summary = summary
        self.published = published
        self.pdf_url = pdf_url
        self.categories = categories or []


class ArxivClient:
    """arXiv API客户端"""

    BASE_URL = "http://export.arxiv.org/api/query"

    def search(self, query: str, max_results: int = 10) -> List[ArxivPaper]:
        """按关键词搜索"""
        params = {
            "search_query": f"all:{urllib.parse.quote(query)}",
            "start": 0, "max_results": max_results,
            "sortBy": "relevance", "sortOrder": "descending",
        }
        return self._query(params)

    def search_by_author(self, author: str, max_results: int = 10) -> List[ArxivPaper]:
        """按作者搜索"""
        params = {
            "search_query": f"au:{urllib.parse.quote(author)}",
            "start": 0, "max_results": max_results,
        }
        return self._query(params)

    def _query(self, params: dict) -> List[ArxivPaper]:
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
            papers = []
            for entry in feed.entries:
                papers.append(ArxivPaper(
                    entry_id=entry.id,
                    title=entry.title.replace("\n", " ").strip(),
                    authors=[a.name for a in entry.authors],
                    summary=entry.summary.replace("\n", " ").strip(),
                    published=entry.published,
                    pdf_url=entry.links[0].href if entry.links else "",
                ))
            return papers
        except Exception as e:
            print(f"[arXiv] 查询失败: {e}")
            return []
