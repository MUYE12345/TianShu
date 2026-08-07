"""
网页爬取MCP
"""
import json
from bs4 import BeautifulSoup
import requests
from agent.mcp.web_crawler.blacklist import is_blacklisted

def crawl_handler(url: str) -> str:
    """抓取网页内容"""
    if is_blacklisted(url):
        return json.dumps({"error": "该网站已被列入黑名单, 禁止爬取"}, ensure_ascii=False)

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"

        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript"]):
            tag.decompose()

        title = ""
        title_tag = soup.select_one("h1") or soup.select_one("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        content = ""
        for selector in ["article", "main", '[role="main"]', ".content", "#content", "body"]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator="\n", strip=True)
                if len(text) > 100:
                    content = text
                    break
        if not content:
            content = soup.get_text(separator="\n", strip=True)

        content = "\n".join(line.strip() for line in content.split("\n") if line.strip())

        return json.dumps({
            "url": url,
            "title": title,
            "content": content[:8000],
            "text_length": len(content),
        }, ensure_ascii=False)

    except requests.HTTPError as e:
        return json.dumps({"error": f"HTTP错误: {e.response.status_code}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"爬取失败: {str(e)}"}, ensure_ascii=False)
