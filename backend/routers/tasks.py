"""任务路由 — 定时任务列表 + 立即运行(触发 agent 后台执行)

前端 DailyPlan 的任务列表走 /api/cron(定时任务); 这里提供:
  GET  /api/tasks        → 任务列表(与 cron 一致, 便于统一)
  POST /api/tasks/run    → 立即运行: 把 prompt 交给 agent 后台执行
"""
import asyncio
import threading
import time

from fastapi import APIRouter, HTTPException

from backend.core.logger import log

router = APIRouter()


async def _drain(agen):
    """消费 agent 事件流(后台线程里跑完即弃)。"""
    async for _ev in agen:
        pass


@router.get("")
def list_tasks():
    """任务列表(对齐 /api/cron 的返回结构)"""
    try:
        from backend.database import SessionLocal
        from backend.models.task import ScheduledTask
        db = SessionLocal()
        try:
            tasks = db.query(ScheduledTask).order_by(ScheduledTask.id.desc()).limit(50).all()
            return {"tasks": [{
                "id": t.id,
                "prompt": getattr(t, "prompt", "") or "",
                "cron": getattr(t, "cron", "") or "",
                "status": getattr(t, "status", "pending") or "pending",
            } for t in tasks]}
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        log.warning("任务列表读取失败: %s", e)
        return {"tasks": []}


@router.post("/run")
def run_task_now(body: dict = None):
    """立即运行一个任务: prompt 交给 agent 后台执行(fire-and-forget)"""
    if not isinstance(body, dict) or not (body.get("prompt") or "").strip():
        raise HTTPException(status_code=400, detail="prompt 必填")
    prompt = body["prompt"].strip()

    def runner():
        try:
            from agent.agent_service import agent_service
            asyncio.run(_drain(agent_service.run(prompt, f"task_{int(time.time())}")))
        except Exception as e:  # noqa: BLE001
            log.warning("任务执行失败: %s", e)

    threading.Thread(target=runner, daemon=True).start()
    return {"status": "triggered", "message": "任务已触发, 后台执行中"}
