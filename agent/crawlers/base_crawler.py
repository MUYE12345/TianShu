"""
爬虫基类 — 所有爬虫继承此类
参考: baidu_search-mcp BaiduNewsSearcher (session复用, 随机UA, 重试)
"""
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from backend.config import settings

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]


@dataclass
class NewsItem:
    """统一的新闻条目"""
    title: str = ""
    url: str = ""
    summary: str = ""
    content: str = ""
    source: str = ""
    source_type: str = ""
    cover_image: str = ""
    published_at: str = ""
    keywords: List[str] = field(default_factory=list)


class BaseCrawler(ABC):
    """爬虫抽象基类"""

    def __init__(self, timeout: int = None, max_retries: int = None):
        self.timeout = timeout or settings.CRAWLER_TIMEOUT
        self.max_retries = max_retries or settings.CRAWLER_MAX_RETRIES
        self.session = requests.Session()
        self.session.trust_env = False  # 跳过系统代理
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        })

    @property
    @abstractmethod
    def source(self) -> str:
        """来源标识"""
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """来源中文名"""
        pass

    @abstractmethod
    def crawl(self) -> List[NewsItem]:
        """执行爬取"""
        pass

    @abstractmethod
    def parse_list(self, html: str) -> List[dict]:
        """解析列表页"""
        pass

    def _get_ua(self) -> str:
        return random.choice(USER_AGENTS)

    def fetch(self, url: str) -> Optional[str]:
        """带重试的HTTP请求(指数退避, 跳过系统代理, 超时日志)"""
        for attempt in range(self.max_retries):
            try:
                self.session.headers.update({"User-Agent": self._get_ua()})
                start = time.time()
                resp = self.session.get(url, timeout=self.timeout)
                elapsed = time.time() - start
                if elapsed > 5:
                    logger.warning(f"[爬虫] {self.source} 请求超时 {elapsed:.1f}s url={url}")
                resp.raise_for_status()
                resp.encoding = "utf-8"
                return resp.text
            except requests.RequestException as e:
                if attempt < self.max_retries - 1:
                    time.sleep((attempt + 1) * 2)
                else:
                    print(f"[爬虫] {self.source} 请求失败: {e}")
                    return None
        return None

    def parse_html(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")
