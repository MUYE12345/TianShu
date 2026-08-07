"""工作休息提醒规则 — 基于持续工作时长 + 上下文感知的智能提醒"""
import os, time, json
from datetime import datetime
from typing import List
from backend.config import DATA_DIR
from backend.companion.rules.base_rule import BaseRule

_WORK_FILE = str(DATA_DIR / "user_data" / "work_session.json")
_INTERVAL = 45 * 60        # 45分钟短休
_LONG_INTERVAL = 2 * 3600  # 2小时长休
_MAX_DAILY = 8


def _load():
    try:
        if os.path.exists(_WORK_FILE):
            with open(_WORK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception: pass
    return {"start": None, "last_remind": 0, "breaks": 0, "long_count": 0}


def _save(s):
    os.makedirs(os.path.dirname(_WORK_FILE), exist_ok=True)
    with open(_WORK_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)


class WorkRestRule(BaseRule):
    def check(self, user_id: int, context: dict = None) -> List[dict]:
        context = context or {}
        now = time.time()
        today = datetime.now().strftime("%Y-%m-%d")
        s = _load()

        # 每日重置
        if s.get("date") != today:
            s = {"start": None, "last_remind": 0, "breaks": 0, "long_count": 0, "date": today}

        time_of_day = context.get("time_of_day", "")
        hour = context.get("hour", datetime.now().hour)
        reminders = []

        # 夜深了还在工作 → 提醒休息而不是继续
        if time_of_day in ("night",) and hour >= 22:
            if s.get("start") and (now - s["start"]) > 30 * 60:
                reminders.append({
                    "type": "work_rest", "title": "已经很晚了",
                    "content": "已经深夜了, 早点休息吧, 明天再做效率更高~",
                    "priority": 5, "action": "sleep",
                })
                _save(s)
                return reminders

        # 午休时间提醒
        if 11 <= hour <= 13 and s.get("start") and (now - s["start"]) > 2 * 3600:
            reminders.append({
                "type": "work_rest", "title": "午休时间",
                "content": "该吃午饭啦! 休息30分钟, 下午效率更高~",
                "priority": 4, "action": "lunch_rest",
            })

        # 如果30分钟内有过活动, 认为是工作状态
        if s.get("start") and now - s["start"] < 30 * 60:
            elapsed = now - s["start"]

            # === 上下文感知: 根据时间段调整提醒策略 ===
            # 下午更容易疲劳, 适当缩短短休间隔
            interval = _INTERVAL
            if time_of_day == "afternoon":
                interval = int(_INTERVAL * 0.8)  # 下午约36分钟提醒一次

            # 45分钟短休
            if elapsed >= interval and (now - s.get("last_remind", 0)) > interval * 0.7:
                if s["breaks"] < _MAX_DAILY:
                    mins = int(elapsed / 60)

                    # 根据上下文定制提醒文案
                    content = f"已连续工作{mins}分钟, 站起来活动5分钟, 看看窗外~"
                    if time_of_day == "afternoon":
                        content = f"已连续工作{mins}分钟, 下午容易疲劳, 起来走走喝杯水~"
                    elif time_of_day == "evening":
                        content = f"已连续工作{mins}分钟, 休息一下眼睛, 准备收尾工作吧~"

                    reminders.append({
                        "type": "work_rest", "title": "该休息了",
                        "content": content,
                        "priority": 4, "action": "rest",
                    })
                    s["last_remind"] = now
                    s["breaks"] += 1

            # 2小时长休
            if elapsed >= _LONG_INTERVAL and s["long_count"] < 3:
                reminders.append({
                    "type": "work_rest", "title": "长时间工作提醒",
                    "content": "已工作2小时以上! 建议休息15分钟, 做做伸展运动。",
                    "priority": 5, "action": "long_rest",
                })
                s["long_count"] += 1
        else:
            s["start"] = now

        _save(s)
        return reminders
