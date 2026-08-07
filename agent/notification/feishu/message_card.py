"""飞书消息卡片构建器"""
import json


def build_news_card(title: str, summary: str, articles: list) -> dict:
    """构建新闻推送卡片"""
    articles_text = "\n".join([f'[{a.get("title","")}]({a.get("url","")})' for a in articles[:10]])
    return {
        "header": {"title": {"tag": "plain_text", "content": title}},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": summary}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": articles_text or "暂无"}},
            {"tag": "hr"},
            {"tag": "note", "element": {"tag": "plain_text", "content": "天枢 自动推送"}},
        ]
    }
