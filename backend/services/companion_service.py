"""陪伴助手服务 — 4种提醒规则"""
from typing import List
from backend.companion.engine import reminder_engine
from backend.companion.rules.weather_rule import WeatherRule
from backend.companion.rules.work_rest_rule import WorkRestRule
from backend.companion.rules.knowledge_rule import KnowledgeRule
from backend.companion.rules.task_rule import TaskRule


class CompanionService:
    """陪伴助手服务: 天气/工作休息/知识/任务 4种提醒"""

    def __init__(self):
        self._registered = False

    def _ensure_rules(self):
        if self._registered:
            return
        reminder_engine.register_rule(WeatherRule())
        reminder_engine.register_rule(WorkRestRule())
        reminder_engine.register_rule(KnowledgeRule())
        reminder_engine.register_rule(TaskRule())
        self._registered = True

    def check_reminders(self, user_id: int = 1) -> List[dict]:
        """检查提醒 (去重和重要性排序由 engine 内部处理)"""
        self._ensure_rules()
        return reminder_engine.check(user_id)


companion_service = CompanionService()
