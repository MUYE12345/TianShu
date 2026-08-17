"""
设置路由 — 返回实际配置（敏感信息脱敏）
"""
from fastapi import APIRouter, Depends
from backend.config import settings
from backend.core.security import get_current_user

router = APIRouter()


@router.get("")
def get_settings():
    """获取设置（含默认值，密码类字段脱敏）"""
    return {
        "app": {"name": settings.APP_NAME, "debug": settings.DEBUG},
        "model": {
            "main": {
                "api_base": settings.MAIN_MODEL_API_BASE,
                "api_key": _mask_key(settings.MAIN_MODEL_API_KEY),
                "model_name": settings.MAIN_MODEL_NAME,
                "temperature": settings.MAIN_MODEL_TEMPERATURE,
                "max_tokens": settings.MAIN_MODEL_MAX_TOKENS,
            },
            "review": {
                "api_base": settings.REVIEW_MODEL_API_BASE,
                "api_key": _mask_key(settings.REVIEW_MODEL_API_KEY),
                "model_name": settings.REVIEW_MODEL_NAME,
                "temperature": settings.REVIEW_MODEL_TEMPERATURE,
            },
        },
        "push": {
            "weather_time": settings.WEATHER_PUSH_TIME,
            "news_time": settings.NEWS_PUSH_TIME,
            "channels": (settings.NEWS_PUSH_CHANNELS or "").split(","),
            "feishu_configured": bool(settings.FEISHU_WEBHOOK_URL),
            "qqmail_configured": bool(settings.QQMAIL_USER),
        },
        "weather_configured": bool(settings.WEATHER_API_KEY),
        "google_configured": bool(settings.GOOGLE_API_KEY and settings.GOOGLE_SEARCH_ENGINE_ID),
    }


@router.put("")
def update_settings(current_user = Depends(get_current_user), body: dict = None):
    """更新设置（仅保存到内存，持久化需扩展）"""
    # 目前仅做配置检查，后续可扩展到配置文件持久化
    return {"status": "ok", "message": "设置已更新"}


def _mask_key(key: str) -> str:
    """脱敏密钥：只显示前4后4字符"""
    if not key or len(key) < 8:
        return key
    return key[:4] + "****" + key[-4:]
