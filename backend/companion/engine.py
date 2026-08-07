"""提醒引擎 — 支持上下文感知、提醒去重(5分钟间隔)、重要性判断"""
import time
from typing import List
from datetime import datetime, timedelta, date
from backend.core.logger import log


class ReminderEngine:
    """提醒引擎: 规则注册 / 上下文收集 / 去重 + 重要性排序

    去重策略 (5 分钟间隔):
    - 相同 (type, title) 的提醒在 5 分钟内不会重复推送
    - 紧急提醒 (priority >= 5) 跳过此限制, 确保重要消息及时送达
    - 去重状态存储于内存 `_last_sent`, 进程重启后重置

    重要性判断:
    - 每条提醒包含 priority 字段 (1-5), 由各规则根据上下文动态赋值:
        - 5: 紧急/健康/安全 (深夜工作、带伞提醒、2小时长休)
        - 4: 高优先级 (下班前任务提醒、45分钟短休、雨天提醒)
        - 3: 中等 (普通知识学习、穿衣建议、午休提醒)
        - 2: 低 (用户忙时降级的知识推送)
        - 1: 最低 (延伸阅读、非紧急提醒)
    - 最终输出按 priority 降序排列, 前端优先展示高优先级提醒
    """

    def __init__(self):
        self.rules = []
        # 去重: { (type, title): last_send_timestamp }
        self._last_sent: dict = {}
        self._dedup_interval = 300  # 5 分钟 (秒)
        self._register_defaults()

    def _register_defaults(self):
        try:
            from backend.companion.rules.weather_rule import WeatherRule
            from backend.companion.rules.work_rest_rule import WorkRestRule
            from backend.companion.rules.knowledge_rule import KnowledgeRule
            from backend.companion.rules.task_rule import TaskRule
            self.register_rule(WeatherRule())
            self.register_rule(WorkRestRule())
            self.register_rule(KnowledgeRule())
            self.register_rule(TaskRule())
        except Exception as e:
            log.warning("[提醒] 注册规则失败: %s", e)

    def register_rule(self, rule):
        self.rules.append(rule)

    def get_context(self, user_id: int) -> dict:
        """收集用户上下文信息, 供提醒规则制定更智能的建议

        返回:
            time_of_day:      morning / afternoon / evening / night
            hour/minute/weekday:  当前时间分量
            weather:          {temp, text, dressing, umbrella, city} 或 None
            recent_conversations: 最近1小时对话 [{role, content}]
            pending_tasks:    今日未完成任务 [{content, priority}]
            overdue_tasks:    昨日逾期任务 [{content, priority}]
            user_city:        用户所在城市 (从设置读取)
        """
        now = datetime.now()
        hour = now.hour

        # 1. 时间段
        if hour < 6:
            time_of_day = "night"
        elif hour < 12:
            time_of_day = "morning"
        elif hour < 18:
            time_of_day = "afternoon"
        else:
            time_of_day = "evening"

        context = {
            "time_of_day": time_of_day,
            "hour": hour,
            "minute": now.minute,
            "weekday": now.weekday(),
            "weather": None,
            "recent_conversations": [],
            "pending_tasks": [],
            "overdue_tasks": [],
            "user_city": None,
        }

        db = None
        try:
            from backend.database import SessionLocal
            db = SessionLocal()

            # 2. 用户设置 → 城市偏好
            try:
                from backend.models.setting import Setting
                setting = db.query(Setting).filter(Setting.user_id == user_id).first()
                if setting and setting.settings_json:
                    context["user_city"] = setting.settings_json.get("city", "北京")
                else:
                    context["user_city"] = "北京"
            except Exception:
                context["user_city"] = "北京"

            # 3. 天气 (如果可用)
            try:
                city = context["user_city"] or "北京"
                from agent.mcp.weather.weather_mcp import weather_handler
                import json
                weather_data = json.loads(weather_handler(city))
                if "error" not in weather_data:
                    current = weather_data.get("current", {})
                    suggestion = weather_data.get("suggestion", {})
                    context["weather"] = {
                        "temp": current.get("temp", ""),
                        "text": current.get("text", ""),
                        "dressing": suggestion.get("dressing", ""),
                        "umbrella": suggestion.get("umbrella", ""),
                        "city": weather_data.get("city", city),
                    }
            except Exception as e:
                log.warning("[上下文] 获取天气失败: %s", e)

            # 4. 最近对话 (最近1小时, 最多10条)
            try:
                from backend.models.session import ChatSession, Message
                since = datetime.utcnow() - timedelta(hours=1)
                recent_sessions = db.query(ChatSession).filter(
                    ChatSession.user_id == user_id,
                    ChatSession.is_active == True,
                ).order_by(ChatSession.updated_at.desc()).limit(3).all()

                messages = []
                for session in recent_sessions:
                    recent_msgs = db.query(Message).filter(
                        Message.session_id == session.id,
                        Message.created_at >= since,
                    ).order_by(Message.id).limit(10).all()
                    for m in recent_msgs:
                        messages.append({
                            "role": m.role,
                            "content": m.content[:200],
                        })
                context["recent_conversations"] = messages[-10:]  # 最多保留10条
            except Exception as e:
                log.warning("[上下文] 获取最近对话失败: %s", e)

            # 5. 待办任务 & 逾期任务
            try:
                from backend.services.plan_service import plan_service

                today_plan = plan_service.get_today(db, user_id)
                if today_plan and today_plan.get("items"):
                    items = today_plan["items"]
                    context["pending_tasks"] = [
                        item for item in items if not item.get("done")
                    ]

                yesterday = date.today() - timedelta(days=1)
                yesterday_plan = plan_service.get_by_date(db, yesterday, user_id)
                if yesterday_plan and yesterday_plan.get("items"):
                    context["overdue_tasks"] = [
                        i for i in yesterday_plan["items"] if not i.get("done")
                    ]
            except Exception as e:
                log.warning("[上下文] 获取任务失败: %s", e)

        except Exception as e:
            log.warning("[上下文] 上下文收集异常: %s", e)
        finally:
            if db is not None:
                db.close()

        return context

    def check(self, user_id: int) -> List[dict]:
        """检查所有规则, 去重, 按重要性排序

        流程:
        1. 收集上下文 (天气 / 任务 / 对话 / 时间)
        2. 逐规则生成提醒
        3. 时间窗口去重 (5 分钟内相同 type+title 不重复推送)
        4. 紧急提醒 (priority >= 5) 跳过去重限制
        5. 按 priority 降序排列后返回
        """
        context = self.get_context(user_id)
        reminders = []
        for rule in self.rules:
            try:
                result = rule.check(user_id, context)
                if result:
                    reminders.extend(result)
            except Exception as e:
                log.warning("[提醒] 规则错误: %s", e)

        # 5 分钟去重: 相同 (type, title) 不重复推送, 紧急提醒除外
        now = time.time()
        filtered = []
        for r in reminders:
            key = (r.get("type", ""), r.get("title", ""))
            last = self._last_sent.get(key, 0.0)
            priority = r.get("priority", 0)
            if priority >= 5 or (now - last) >= self._dedup_interval:
                self._last_sent[key] = now
                filtered.append(r)

        filtered.sort(key=lambda r: r.get("priority", 0), reverse=True)
        return filtered


reminder_engine = ReminderEngine()
