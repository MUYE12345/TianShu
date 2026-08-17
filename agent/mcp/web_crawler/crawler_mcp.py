"""
网页爬取MCP
"""
import json
from bs4 import BeautifulSoup
import requests
from agent.mcp.web_crawler.blacklist import is_blacklisted
from agent.crawlers.safety import validate_url


def crawl_handler(url: str) -> str:
    """抓取网页内容(黑名单 + SSRF 防护: 仅 http/https, 拒绝内网/回环/元数据地址)"""
    if is_blacklisted(url):
        return json.dumps({"error": "该网站已被列入黑名单, 禁止爬取"}, ensure_ascii=False)
    err = validate_url(url)
    if err:
        return json.dumps({"error": f"爬取被安全策略拒绝: {err}"}, ensure_ascii=False)

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        # 重定向后的最终地址同样过安全校验(防 302 → 内网/元数据)
        final_err = validate_url(resp.url)
        if final_err:
            return json.dumps({"error": f"重定向目标被安全策略拒绝: {final_err}"}, ensure_ascii=False)
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
