"""
搜索引擎MCP — 统一搜索入口(百度/必应/Google)
"""
import re
import json

def web_search_handler(query: str, engine: str = "auto", count: int = 10) -> str:
    """统一搜索入口"""
    if engine == "auto":
        engine = "bing" if re.search(r'[一-鿿]', query) else "google"

    engines = {
        "baidu": _search_baidu,
        "bing": _search_bing,
        "google": _search_google,
    }
    searcher = engines.get(engine, _search_bing)
    results = searcher(query, count)
    return json.dumps(results, ensure_ascii=False, indent=2)


def _search_baidu(query: str, count: int = 10) -> list:
    """百度搜索(页面解析)"""
    import requests
    from bs4 import BeautifulSoup
    url = f"https://www.baidu.com/s?wd={query}&rn={count}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        for item in soup.select(".result")[:count]:
            title_el = item.select_one("h3 a")
            if not title_el:
                continue
            results.append({
                "title": title_el.get_text(strip=True),
                "url": title_el.get("href", ""),
                "snippet": item.select_one(".c-abstract").get_text(strip=True) if item.select_one(".c-abstract") else "",
                "source": "baidu",
            })
        return results
    except Exception as e:
        return [{"error": f"百度搜索失败: {e}"}]


def _search_bing(query: str, count: int = 10) -> list:
    """必应搜索(页面解析)"""
    import requests
    from bs4 import BeautifulSoup
    url = f"https://cn.bing.com/search?q={query}&count={count}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
               "Accept-Language": "zh-CN,zh;q=0.9"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        for item in soup.select(".b_algo")[:count]:
            title_el = item.select_one("h2 a")
            if not title_el:
                continue
            results.append({
                "title": title_el.get_text(strip=True),
                "url": title_el.get("href", ""),
                "snippet": item.select_one(".b_caption p").get_text(strip=True) if item.select_one(".b_caption p") else "",
                "source": "bing",
            })
        return results
    except Exception as e:
        return [{"error": f"必应搜索失败: {e}"}]


def _search_google(query: str, count: int = 10) -> list:
    """Google搜索(需API Key)"""
    from backend.config import settings
    import requests

    api_key = settings.GOOGLE_API_KEY
    cx = settings.GOOGLE_SEARCH_ENGINE_ID
    if not api_key or not cx:
        return [{"error": "Google API未配置, 请在.env中设置GOOGLE_API_KEY和GOOGLE_SEARCH_ENGINE_ID"}]

    try:
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": api_key, "cx": cx, "q": query, "num": min(count, 10)},
            timeout=10,
        )
        data = resp.json()
        return [{
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "source": "google",
        } for item in data.get("items", [])]
    except Exception as e:
        return [{"error": f"Google搜索失败: {e}"}]
