"""机器之心爬虫 — Selenium渲染 + 滚动加载"""
from typing import List
from agent.crawlers.base_crawler import BaseCrawler, NewsItem
from agent.crawlers.js_crawler import try_selenium_then_bing


class MachineHeartCrawler(BaseCrawler):
    @property
    def source(self) -> str: return "machine_heart"
    @property
    def source_name(self) -> str: return "机器之心"
    @property
    def list_url(self) -> str:
        return "https://jigou.jiqizhixin.com/industry"

    def crawl(self) -> List[NewsItem]:
        return try_selenium_then_bing(
            url=self.list_url,
            source_name=self.source_name,
            source_type=self.source,
            search_query="机器之心 人工智能 深度学习",
            scroll=True, scroll_times=8,
        )

    def parse_list(self, html: str) -> List[dict]:
        return []
