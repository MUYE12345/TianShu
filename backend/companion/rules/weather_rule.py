"""天气提醒规则 — 使用上下文中的天气数据, 避免重复请求"""
from backend.companion.rules.base_rule import BaseRule
from backend.core.logger import log
from typing import List


class WeatherRule(BaseRule):
    def check(self, user_id: int, context: dict = None) -> List[dict]:
        context = context or {}
        weather = context.get("weather")
        time_of_day = context.get("time_of_day", "")

        # 如果上下文中已有天气数据, 直接使用避免重复请求
        if weather:
            reminders = []
            text = weather.get("text", "")

            # 带伞提醒 (雨天 + 用户即将出门的时间段)
            if "雨" in text:
                reminders.append({
                    "type": "weather", "title": "今日有雨",
                    "content": "今天会下雨, 出门记得带伞~",
                    "priority": 4, "action": "umbrella",
                })

            # 穿衣建议 (早晚温差大时附带提醒)
            dressing = weather.get("dressing", "")
            if dressing:
                extra = ""
                if time_of_day in ("morning", "evening"):
                    extra = " 早晚温差大, 注意增减衣物。"
                reminders.append({
                    "type": "weather", "title": "穿衣建议",
                    "content": dressing + extra,
                    "priority": 3, "action": "dressing",
                })

            # 夜间低温提醒
            if time_of_day == "night" and weather.get("temp") and "寒冷" in dressing:
                reminders.append({
                    "type": "weather", "title": "夜间降温",
                    "content": "夜间温度较低, 注意保暖~",
                    "priority": 3, "action": "keep_warm",
                })

            return reminders

        # 上下文没有天气数据时, 降级为自行查询 (保留原有行为)
        try:
            city = context.get("user_city") or "北京"
            from agent.mcp.weather.weather_mcp import weather_handler
            import json
            data = json.loads(weather_handler(city))
            if "error" in data:
                log.warning("天气提醒: 获取天气失败 %s", data.get("error"))
                return []
            reminders = []
            current = data.get("current", {})
            if "雨" in str(current.get("text", "")):
                reminders.append({"type": "weather", "title": "今日有雨",
                                  "content": "今天会下雨, 出门记得带伞~", "priority": 4, "action": "umbrella"})
            suggestion = data.get("suggestion", {})
            dressing = suggestion.get("dressing", "")
            if dressing:
                reminders.append({"type": "weather", "title": "穿衣建议",
                                  "content": dressing, "priority": 3, "action": "dressing"})
            return reminders
        except Exception as e:
            log.warning("天气提醒规则异常: %s", e)
            return []
