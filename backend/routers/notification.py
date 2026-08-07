"""
通知推送路由 — 手动触发天气/新闻推送
"""
from fastapi import APIRouter, Query
from backend.config import settings
from agent.notification.scheduler import push_scheduler

router = APIRouter()


@router.get("/config")
def get_notify_config():
    """获取推送配置"""
    return {
        "feishu": {"configured": bool(settings.FEISHU_WEBHOOK_URL)},
        "qqmail": {"configured": bool(settings.QQMAIL_USER)},
        "weather_push_time": settings.WEATHER_PUSH_TIME,
        "news_push_time": settings.NEWS_PUSH_TIME,
        "channels": settings.NEWS_PUSH_CHANNELS.split(","),
    }


@router.post("/push")
def trigger_push(push_type: str = Query("all", description="weather / news / all")):
    """手动触发推送"""
    if push_type not in ("weather", "news", "all"):
        return {"success": False, "message": "push_type 必须为 weather / news / all"}
    result = push_scheduler.push_now(push_type)
    return {"success": True, "result": result}


@router.post("/test/feishu")
def test_feishu():
    """测试飞书推送"""
    from agent.notification.feishu.notifier import FeishuNotifier
    from agent.notification.notifier_base import NotifyContent
    notifier = FeishuNotifier()
    success = notifier.send(NotifyContent(
        title="测试推送", summary="这是一条测试消息",
        articles=[{"title": "天枢", "url": "http://localhost:8000"}]
    ))
    return {"success": success}


@router.post("/test/qqmail")
def test_qqmail():
    """测试QQ邮箱推送"""
    from agent.notification.qq_mail.notifier import QQMailNotifier
    from agent.notification.notifier_base import NotifyContent
    notifier = QQMailNotifier()
    success = notifier.send(NotifyContent(
        title="测试", summary="这是一封测试邮件", articles=[]
    ))
    return {"success": success}
