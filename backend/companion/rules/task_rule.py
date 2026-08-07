"""任务提醒规则 — 检查今日未完成/逾期任务, 支持上下文感知"""
from datetime import date, datetime
from typing import List
from backend.companion.rules.base_rule import BaseRule
from backend.core.logger import log


_URGENT_HOUR = 16  # 下午4点后标记为紧急


class TaskRule(BaseRule):
    """任务提醒: 检查今日未完成任务+逾期任务"""

    def check(self, user_id: int, context: dict = None) -> List[dict]:
        context = context or {}
        now = datetime.now()
        current_hour = now.hour
        time_of_day = context.get("time_of_day", "")
        weather = context.get("weather")

        # 优先使用上下文中的数据, 避免重复查询
        pending_tasks = context.get("pending_tasks", [])
        overdue_tasks = context.get("overdue_tasks", [])

        reminders = []

        # 如果上下文没有提供任务数据, 回退到自行查询
        if not pending_tasks:
            try:
                from backend.services.plan_service import plan_service
                from backend.database import SessionLocal
                db = SessionLocal()
                try:
                    today_plan = plan_service.get_today(db, user_id)
                    if today_plan and today_plan.get("items"):
                        items = today_plan["items"]
                        pending_tasks = [item for item in items if not item.get("done")]
                finally:
                    db.close()
            except Exception as e:
                log.warning("任务提醒规则-自行查询失败: %s", e)

        if not overdue_tasks and current_hour < 12:
            try:
                from backend.services.plan_service import plan_service
                from backend.database import SessionLocal
                from datetime import timedelta
                db = SessionLocal()
                try:
                    yesterday = date.today() - timedelta(days=1)
                    yesterday_plan = plan_service.get_by_date(db, yesterday, user_id)
                    if yesterday_plan and yesterday_plan.get("items"):
                        overdue_tasks = [i for i in yesterday_plan["items"] if not i.get("done")]
                finally:
                    db.close()
            except Exception as e:
                log.warning("任务提醒规则-逾期查询失败: %s", e)

        # 1. 今日待办提醒
        if pending_tasks:
            pending_tasks.sort(key=lambda x: x.get("priority", 1), reverse=True)
            count = len(pending_tasks)

            # 上下文感知: 根据时间段调整紧急程度
            is_urgent = current_hour >= _URGENT_HOUR
            priority = 5 if is_urgent else (4 if current_hour >= 12 else 3)

            # 构建提醒内容
            content_lines = []
            for item in pending_tasks[:5]:
                icon = "HIGH" if item.get("priority", 1) >= 3 else "LOW"
                content_lines.append(f"[{icon}] {item.get('content', '')}")
            content = "\n".join(content_lines)

            # 时间段相关的标题
            if is_urgent:
                title = f"下班前还有{count}项任务待完成!"
            elif current_hour >= 12:
                title = f"下午好, 还有{count}项任务待完成"
            else:
                title = f"早上好, 今日有{count}项任务等着你"

            # 天气感知: 如果今天有雨, 提醒带伞出门办事
            extra = ""
            if weather and "雨" in weather.get("text", ""):
                extra = "\n提示: 今天有雨, 如有外出任务请带伞。"
            if extra:
                content += extra

            reminders.append({
                "type": "task", "title": title,
                "content": content, "priority": priority,
                "action": "task",
            })

        # 2. 逾期任务 (仅上午提醒)
        if overdue_tasks and current_hour < 12:
            reminders.append({
                "type": "task", "title": "昨日有未完成任务",
                "content": f"昨日的 {len(overdue_tasks)} 项任务还未完成, 建议优先处理。",
                "priority": 4, "action": "task",
            })

        return reminders
