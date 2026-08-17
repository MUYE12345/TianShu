"""
浏览器爬虫 — 使用Selenium渲染JS + 自动滚动加载
统一所有爬虫使用, 解决JS动态渲染和懒加载问题
"""
import time
import os
from typing import Optional
from bs4 import BeautifulSoup


class BrowserCrawler:
    """浏览器爬虫: headless Chrome渲染JS + 自动滚动"""

    def __init__(self):
        self.driver = None

    def _ensure_driver(self):
        if self.driver is not None:
            return True
        if not self._check_chrome():
            return False
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            import concurrent.futures

            cd_path = self._find_chromedriver()
            if not cd_path:
                print("[浏览器爬虫] 未找到 chromedriver，使用 Bing 降级")
                return False

            options = Options()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0")
            options.add_argument("--window-size=1920,1080")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            # 显式指定本地 chromedriver，避免 Selenium Manager 联网下载(国内访问被墙会挂起)
            service = Service(executable_path=cd_path)

            def _launch():
                return webdriver.Chrome(options=options, service=service)

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_launch)
                try:
                    self.driver = future.result(timeout=20)
                except concurrent.futures.TimeoutError:
                    print("[浏览器爬虫] Chrome 启动超时(20s)，使用 Bing 降级")
                    return False

            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
            # 设置隐式等待
            self.driver.implicitly_wait(5)
            print("[浏览器爬虫] Chrome启动成功")
            return True
        except Exception as e:
            print(f"[浏览器爬虫] Chrome初始化失败(将使用Bing降级): {e}")
            return False

    @staticmethod
    def _find_chromedriver() -> Optional[str]:
        """查找本地 chromedriver，找不到返回 None。"""
        import shutil
        p = shutil.which("chromedriver")
        if p:
            return p
        candidates = [
            r"D:\chromedriver\chromedriver-win64\chromedriver.exe",
            r"C:\chromedriver\chromedriver.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\chromedriver\chromedriver.exe"),
            os.path.expandvars(r"%USERPROFILE%\chromedriver\chromedriver.exe"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
        return None

    @staticmethod
    def _check_chrome() -> bool:
        """快速检查Chrome是否可用"""
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        for p in chrome_paths:
            if os.path.isfile(p):
                return True
        return False

    def fetch(self, url: str, wait_seconds: float = 3.0, scroll_pause: float = 0.5) -> Optional[str]:
        """
        渲染页面 + 滚动到底部触发懒加载

        Args:
            url: 页面URL
            wait_seconds: 首次等待秒数(JS初始渲染)
            scroll_pause: 每次滚动后等待秒数
        """
        from agent.crawlers.safety import validate_url
        err = validate_url(url)
        if err:
            print(f"[浏览器爬虫] 安全策略拒绝 {url}: {err}")
            return None
        if not self._ensure_driver():
            return None
        try:
            self.driver.get(url)
            time.sleep(wait_seconds)
            return self.driver.page_source
        except Exception as e:
            print(f"[浏览器爬虫] 抓取失败 {url}: {e}")
            return None

    def fetch_with_scroll(self, url: str, wait_seconds: float = 2.0,
                          scroll_times: int = 5, scroll_pause: float = 0.8) -> Optional[str]:
        """
        渲染页面 + 多次滚动到底部(触发懒加载更多内容)

        Args:
            url: 页面URL
            wait_seconds: 首次等待秒数
            scroll_times: 滚动次数
            scroll_pause: 每次滚动后等待秒数
        """
        from agent.crawlers.safety import validate_url
        err = validate_url(url)
        if err:
            print(f"[浏览器爬虫] 安全策略拒绝 {url}: {err}")
            return None
        if not self._ensure_driver():
            return None
        try:
            self.driver.get(url)
            time.sleep(wait_seconds)

            for i in range(scroll_times):
                old_height = self.driver.execute_script("return document.body.scrollHeight")
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(scroll_pause)
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == old_height and i > 2:
                    break  # 高度不再变化, 停止滚动

            return self.driver.page_source
        except Exception as e:
            print(f"[浏览器爬虫] 滚动抓取失败 {url}: {e}")
            return None

    def fetch_and_parse(self, url: str, wait_seconds: float = 3.0,
                        scroll: bool = False, scroll_times: int = 5) -> tuple:
        """渲染页面并返回BeautifulSoup"""
        if scroll:
            html = self.fetch_with_scroll(url, wait_seconds, scroll_times=scroll_times)
        else:
            html = self.fetch(url, wait_seconds)
        if html:
            return BeautifulSoup(html, "lxml"), html
        return None, None

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception: pass  # fallback
            self.driver = None


_browser_crawler = BrowserCrawler()


def get_browser_crawler() -> BrowserCrawler:
    return _browser_crawler
