"""新京报爬虫 — 全板块采集（Selenium渲染 + 滚动加载）"""
from typing import List, Optional
from bs4 import BeautifulSoup
from agent.crawlers.base_crawler import BaseCrawler, NewsItem


class BJNewsCrawler(BaseCrawler):
    SECTIONS = {
        "diyikandian": "https://www.bjnews.com.cn/diyikandian",
        "guoji":       "https://www.bjnews.com.cn/guoji",
        "technology":  "https://www.bjnews.com.cn/technology",
        "zhengshi":    "https://www.bjnews.com.cn/zhengshi",
    }

    @property
    def source(self) -> str: return "bjnews"
    @property
    def source_name(self) -> str: return "新京报"

    def crawl(self, section: str = None) -> List[NewsItem]:
        results = []
        sections = {section: self.SECTIONS[section]} if section else self.SECTIONS
        for sec_name, sec_url in sections.items():
            try:
                items = self._crawl_section(sec_url, sec_name)
                results.extend(items)
            except Exception as e:
                print(f"[新京报] {sec_name} 失败: {e}")
        return results

    def _crawl_section(self, url: str, section: str) -> List[NewsItem]:
        """抓取单个板块"""
        seen = set()
        items = []

        # 方案1: Selenium渲染(可加载更多内容)
        try:
            from agent.crawlers.browser_crawler import get_browser_crawler
            bc = get_browser_crawler()
            soup, html = bc.fetch_and_parse(url, wait_seconds=2, scroll=True, scroll_times=8)
            if soup:
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    text = a.get_text(strip=True)
                    if "bjnews.com.cn/detail/" in href and len(text) > 8:
                        if href not in seen:
                            seen.add(href)
                            items.append(NewsItem(title=text, url=href,
                                                  source=self.source_name, source_type=section))
                if items:
                    return items
        except Exception: pass

        # 方案2: 直接requests抓取(降级)
        html = self.fetch(url)
        if not html:
            return items
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if "bjnews.com.cn/detail/" in href and len(text) > 8:
                if href not in seen:
                    seen.add(href)
                    items.append(NewsItem(title=text, url=href,
                                          source=self.source_name, source_type=section))
        return items

    def parse_list(self, html: str) -> List[dict]:
        return []
