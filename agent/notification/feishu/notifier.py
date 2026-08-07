"""飞书Webhook推送 — 支持新闻+天气"""
import requests
from backend.core.logger import log
from agent.notification.notifier_base import NotifierBase, NotifyContent
from backend.config import settings


class FeishuNotifier(NotifierBase):
    def send(self, content: NotifyContent) -> bool:
        webhook = settings.FEISHU_WEBHOOK_URL
        if not webhook:
            return False
        try:
            elements = []

            # 天气卡片（早间推送时显示）
            weather = content.weather
            if weather and weather.get("text"):
                weather_block = (
                    f"🌤 **{weather.get('city', '')}天气**\n"
                    f"当前：{weather.get('text', '')} {weather.get('temp', '')}\n"
                )
                suggestion = weather.get("suggestion", {})
                if suggestion.get("umbrella"):
                    weather_block += f"☂️ {suggestion['umbrella']}\n"
                if suggestion.get("dressing"):
                    weather_block += f"👔 {suggestion['dressing']}"
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": weather_block.strip()},
                })
                elements.append({"tag": "hr"})

            # 摘要
            if content.summary:
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": content.summary},
                })
                elements.append({"tag": "hr"})

            # 新闻列表
            if content.articles:
                articles_text = "\n".join(
                    [f'[{a["title"]}]({a["url"]})' for a in content.articles[:10]]
                )
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": articles_text},
                })

            payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {"title": {"tag": "plain_text", "content": content.title}},
                    "elements": elements,
                },
            }
            resp = requests.post(webhook, json=payload, timeout=10)
            return resp.ok
        except Exception as e:
            log.warning("飞书推送失败: %s", e)
            return False

    def validate_config(self) -> tuple:
        if not settings.FEISHU_WEBHOOK_URL:
            return False, "飞书Webhook未配置"
        return True, "有效"
