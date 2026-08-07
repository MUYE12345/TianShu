"""知识学习提醒规则 — 从新闻/论文中提取新知识点提醒学习, 支持上下文感知"""
from datetime import datetime
from typing import List
from backend.companion.rules.base_rule import BaseRule
from backend.core.logger import log


class KnowledgeRule(BaseRule):
    """知识学习提醒: 检查今日新闻中是否有值得学习的知识点"""

    def check(self, user_id: int, context: dict = None) -> List[dict]:
        context = context or {}
        reminders = []
        time_of_day = context.get("time_of_day", "")
        pending_tasks = context.get("pending_tasks", [])
        overdue_tasks = context.get("overdue_tasks", [])

        # 上下文感知: 如果用户还有大量待办任务, 降低知识提醒的优先级
        busy_score = len(pending_tasks) * 2 + len(overdue_tasks) * 3
        is_busy = busy_score >= 5

        # 深夜不推荐知识学习
        if time_of_day == "night":
            return reminders

        # 1. 检查今日新闻
        try:
            from agent.news_service import news_service
            from backend.database import SessionLocal
            db = SessionLocal()
            news_list = news_service.get_daily_news(db, page=1, size=10)
            db.close()

            if news_list:
                top = news_list[0]
                summary = top.ai_summary or top.summary or ""
                content = f"推荐阅读: {top.title}"
                if summary:
                    content += f"\n摘要: {summary[:100]}..."

                # 上下文感知: 根据时间段和忙闲程度调整优先级
                base_priority = 3
                if is_busy:
                    base_priority = 2  # 忙时降级
                elif time_of_day == "morning":
                    base_priority = 4  # 早上大脑清醒, 适合学习

                reminders.append({
                    "type": "knowledge", "title": "今日新知",
                    "content": content, "priority": base_priority,
                    "action": "learn", "url": top.url,
                })

                # 第二条新闻: 忙时不推荐第二条
                if len(news_list) > 1 and not is_busy:
                    second = news_list[1]
                    reminders.append({
                        "type": "knowledge", "title": "延伸阅读",
                        "content": f"另有一篇: {second.title}",
                        "priority": base_priority - 1, "action": "learn", "url": second.url,
                    })
        except Exception as e:
            log.warning("知识提醒规则异常: %s", e)

        return reminders
