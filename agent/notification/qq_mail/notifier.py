"""QQ邮箱SMTP推送 — 支持新闻+天气"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from backend.core.logger import log
from agent.notification.notifier_base import NotifierBase, NotifyContent
from backend.config import settings


class QQMailNotifier(NotifierBase):
    def send(self, content: NotifyContent) -> bool:
        host, port, user, pwd = (settings.QQMAIL_SMTP_HOST, settings.QQMAIL_SMTP_PORT,
                                 settings.QQMAIL_USER, settings.QQMAIL_PASS)
        if not all([host, user, pwd]):
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = content.title
        msg["From"] = user
        msg["To"] = user

        # 构建 HTML
        html_parts = [f"<html><body><h2>{content.title}</h2>"]

        # 天气信息
        weather = content.weather
        if weather and weather.get("text"):
            html_parts.append('<div style="background:#e8f4fd;padding:12px;border-radius:8px;margin:12px 0">')
            html_parts.append(f'<h3 style="margin:0 0 8px">🌤 {weather.get("city", "")} 天气</h3>')
            html_parts.append(f'<p>当前：{weather.get("text", "")} {weather.get("temp", "")}</p>')
            suggestion = weather.get("suggestion", {})
            if suggestion.get("umbrella"):
                html_parts.append(f'<p>☂️ {suggestion["umbrella"]}</p>')
            if suggestion.get("dressing"):
                html_parts.append(f'<p>👔 {suggestion["dressing"]}</p>')
            html_parts.append('</div>')

        # 摘要
        if content.summary:
            html_parts.append(f"<p>{content.summary}</p>")

        # 新闻列表
        if content.articles:
            html_parts.append("<hr><ul>")
            for a in content.articles[:10]:
                html_parts.append(f'<li><a href="{a["url"]}">{a["title"]}</a></li>')
            html_parts.append("</ul>")

        html_parts.append(
            '<div style="color:#999;font-size:12px;text-align:center;margin-top:30px">'
            "天枢 · 自动推送</div>"
        )
        html_parts.append("</body></html>")
        html = "\n".join(html_parts)

        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            with smtplib.SMTP_SSL(host, port) as server:
                server.login(user, pwd)
                server.send_message(msg)
            return True
        except Exception as e:
            log.warning("QQ邮箱推送失败: %s", e)
            return False

    def validate_config(self) -> tuple:
        if not settings.QQMAIL_USER or not settings.QQMAIL_PASS:
            return False, "QQ邮箱未配置"
        return True, "有效"
