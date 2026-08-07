"""新闻聚合器: 调用爬虫→去重→排序→LLM摘要"""
from typing import List, Optional
from datetime import datetime
from agent.crawlers.base_crawler import NewsItem
from agent.crawlers.daily_news.deep_tech_crawler import DeepTechCrawler
from agent.crawlers.daily_news.machine_heart_crawler import MachineHeartCrawler
from agent.crawlers.daily_news.qbitai_crawler import QbitaiCrawler
from agent.crawlers.daily_news.aiera_crawler import AieraCrawler
from agent.crawlers.current_news.bjnews_crawler import BJNewsCrawler


class NewsAggregator:
    def __init__(self):
        self.daily_crawlers = [
            DeepTechCrawler(), MachineHeartCrawler(),
            QbitaiCrawler(), AieraCrawler(),
        ]
        self.current_crawlers = [BJNewsCrawler()]

    def aggregate_daily(self) -> List[NewsItem]:
        all_news = []
        for crawler in self.daily_crawlers:
            try:
                items = crawler.crawl()
                all_news.extend(items)
                print(f"[聚合] {crawler.source_name}: {len(items)}条")
            except Exception as e:
                print(f"[聚合] {crawler.source_name} 失败: {e}")
        # 去重
        seen = set()
        unique = []
        for item in all_news:
            key = item.url or item.title
            if key not in seen:
                seen.add(key)
                unique.append(item)
        unique.sort(key=lambda x: x.published_at or "", reverse=True)
        return unique

    def generate_summary(self, news_list: List[NewsItem], llm=None) -> str:
        """LLM摘要"""
        if not news_list or not llm:
            return ""
        titles = "\n".join([f"- {n.title} ({n.source})" for n in news_list[:15]])
        try:
            result = llm.invoke(f"请为以下新闻生成30字以内的摘要:\n{titles}")
            return result.content.strip()
        except Exception:
            return "(摘要生成失败)"

    def aggregate_current(self, section: str = None) -> List[NewsItem]:
        results = []
        for crawler in self.current_crawlers:
            try:
                results.extend(crawler.crawl(section=section))
            except Exception as e:
                print(f"[聚合] {crawler.source_name} 失败: {e}")
        return results
