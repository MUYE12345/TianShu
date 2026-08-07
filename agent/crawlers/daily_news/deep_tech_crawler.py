"""深科技爬虫 — 网易号 Selenium渲染 + 滚动加载"""
import logging
from typing import List
from agent.crawlers.base_crawler import BaseCrawler, NewsItem
from agent.crawlers.js_crawler import try_selenium_then_bing

logger = logging.getLogger(__name__)


class DeepTechCrawler(BaseCrawler):
    _consecutive_failures = 0

    @property
    def source(self) -> str: return "deep_tech"
    @property
    def source_name(self) -> str: return "深科技"
    @property
    def list_url(self) -> str:
        return "https://www.163.com/dy/media/T1460535614076.html"

    def crawl(self) -> List[NewsItem]:
        if self._consecutive_failures >= 3:
            logger.warning(
                f"[爬虫] {self.source} 连续{self._consecutive_failures}次失败, 跳过本次爬取"
            )
            return []

        try:
            items = try_selenium_then_bing(
                url=self.list_url,
                source_name=self.source_name,
                source_type=self.source,
                search_query="DeepTech深科技 网易",
                scroll=True,
                scroll_times=8,
                url_pattern="/dy/article/",
            )
        except Exception as e:
            self._consecutive_failures += 1
            logger.error(
                f"[爬虫] {self.source} 爬取异常 (连续{self._consecutive_failures}次): {e}"
            )
            return []

        # 二次过滤: 只保留包含 /dy/article/ 的真实文章
        result = [it for it in items if "/dy/article/" in it.url][:20]

        if not result:
            self._consecutive_failures += 1
            logger.warning(
                f"[爬虫] {self.source} 结果为空 (连续{self._consecutive_failures}次)"
            )
        else:
            self._consecutive_failures = 0

        return result

    def parse_list(self, html: str) -> List[dict]:
        return []
