"""
JS渲染页面爬虫辅助 — 先试Selenium, 失败用Bing降级
"""
from typing import List, Optional
from urllib.parse import urljoin
from agent.crawlers.base_crawler import NewsItem


def try_selenium_then_bing(
    url: str,
    source_name: str,
    source_type: str,
    search_query: str,
    wait_seconds: float = 4.0,
    min_articles: int = 3,
    scroll: bool = True,
    scroll_times: int = 5,
    url_pattern: str = "",
) -> List[NewsItem]:
    """
    尝试用Selenium渲染页面抓取(支持滚动懒加载), 结果太少则用Bing搜索降级

    Args:
        url: 目标页面URL
        source_name: 来源中文名
        source_type: 来源英文标识
        search_query: Bing搜索查询词(降级用)
        wait_seconds: Selenium等待秒数
        min_articles: 最低文章数
        scroll: 是否滚动到底部触发懒加载
        scroll_times: 最大滚动次数
        url_pattern: URL过滤关键词(如"/dy/article/"), 仅保留包含此模式的链接

    Returns:
        NewsItem列表
    """
    selenium_items = _selenium_crawl(url, source_name, source_type, wait_seconds,
                                     scroll=scroll, scroll_times=scroll_times,
                                     url_pattern=url_pattern)
    if len(selenium_items) >= min_articles:
        return selenium_items

    # 方案2: Bing搜索降级
    bing_items = _bing_fallback(search_query, source_name, source_type)
    if bing_items:
        return bing_items

    # 如果selenium有少量结果但不够, 合并返回
    return selenium_items


def _resolve_url(base_url: str, href: str) -> str:
    """将相对URL解析为绝对URL"""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("//"):
        return f"https:{href}"
    return urljoin(base_url, href)


def _selenium_crawl(url: str, source_name: str, source_type: str, wait: float,
                    scroll: bool = False, scroll_times: int = 5,
                    url_pattern: str = "") -> List[NewsItem]:
    """使用Selenium渲染页面并提取文章"""
    try:
        from agent.crawlers.browser_crawler import get_browser_crawler
        bc = get_browser_crawler()
        soup, html = bc.fetch_and_parse(url, wait_seconds=wait, scroll=scroll, scroll_times=scroll_times)
        if not soup:
            return []

        items = []
        seen = set()

        def should_include(href: str, text: str) -> bool:
            if not href or href.startswith("javascript") or href == "#":
                return False
            if len(text) <= 8:
                return False
            if href in seen:
                return False
            if url_pattern and url_pattern not in href:
                return False
            return True

        # 优先匹配: 有url_pattern时只取URL匹配的链接
        if url_pattern:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                resolved = _resolve_url(url, href)
                if not should_include(href, text):
                    continue
                if url_pattern not in resolved:
                    continue
                seen.add(href)
                items.append(NewsItem(title=text, url=resolved,
                                      source=source_name, source_type=source_type))
            return items[:25]

        # 策略1: article标签
        for article in soup.select("article"):
            a = article.select_one("a[href]")
            if not a:
                continue
            title = a.get("title") or a.get_text(strip=True)
            href = a["href"]
            if title and len(title) > 5 and href not in seen:
                seen.add(href)
                items.append(NewsItem(title=title, url=_resolve_url(url, href),
                                      source=source_name, source_type=source_type))

        # 策略2: 所有带标题的链接(如果策略1没找到)
        if not items:
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                href = a["href"]
                if len(text) > 10 and href not in seen and not href.startswith("javascript"):
                    seen.add(href)
                    items.append(NewsItem(title=text, url=_resolve_url(url, href),
                                          source=source_name, source_type=source_type))

        # 策略3: h2/h3下的链接
        if not items:
            for heading in soup.select("h2 a, h3 a, h4 a"):
                text = heading.get_text(strip=True)
                href = heading.get("href", "")
                if text and href and href not in seen:
                    seen.add(href)
                    items.append(NewsItem(title=text, url=href,
                                          source=source_name, source_type=source_type))

        return items[:20]
    except Exception as e:
        print(f"[Selenium] {source_name} 抓取失败: {e}")
        return []


def _bing_fallback(query: str, source_name: str, source_type: str) -> List[NewsItem]:
    """Bing搜索降级"""
    try:
        from agent.mcp.web_search.search_mcp import _search_bing
        results = _search_bing(query, count=15)
        return [NewsItem(
            title=r.get("title", ""), url=r.get("url", ""),
            summary=r.get("snippet", ""),
            source=source_name, source_type=source_type,
        ) for r in results if r.get("title")]
    except Exception as e:
        print(f"[Bing] {source_name} 搜索失败: {e}")
        return []
