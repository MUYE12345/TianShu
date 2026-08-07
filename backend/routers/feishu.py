"""飞书机器人路由 — 通过飞书对话触发 Agent

飞书应用事件订阅指向 `POST /api/feishu/webhook`(需公网可达)。
支持:
  - url_verification 挑战应答
  - im.message.receive_v1 消息 → Agent 处理 → 回复
"""
import asyncio
from fastapi import APIRouter, Request
from agent.notification.feishu.bot import feishu_bot

router = APIRouter()


@router.post("/webhook")
async def feishu_webhook(request: Request):
    """飞书事件回调入口

    handle_webhook 内部用 asyncio.run 处理 agent(只允许在无运行中事件循环的线程里),
    因此用 asyncio.to_thread 放到工作线程, 避免 async 路由里 asyncio.run 抛错。
    """
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    result = await asyncio.to_thread(feishu_bot.handle_webhook, body or {})
    return result
