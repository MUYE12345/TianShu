"""量子位爬虫 — Selenium渲染 + 滚动加载"""
from typing import List
from agent.crawlers.base_crawler import BaseCrawler, NewsItem
from agent.crawlers.js_crawler import try_selenium_then_bing


class QbitaiCrawler(BaseCrawler):
    @property
    def source(self) -> str: return "qbitai"
    @property
    def source_name(self) -> str: return "量子位"
    @property
    def list_url(self) -> str:
        return "https://www.qbitai.com/category/%E8%B5%84%E8%AE%AF"

    def crawl(self) -> List[NewsItem]:
        return try_selenium_then_bing(
            url=self.list_url,
            source_name=self.source_name,
            source_type=self.source,
            search_query="量子位 人工智能 科技",
            scroll=True, scroll_times=5,
        )

    def parse_list(self, html: str) -> List[dict]:
        return []
