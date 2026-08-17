"""
定时任务路由

说明: 本项目为单用户个人应用, 任务不关联 user_id。若部署为多用户公开服务,
需为任务绑定 user_id 并按用户隔离。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db, engine
from backend.models.task import ScheduledTask
from sqlalchemy import inspect, text
from backend.core.security import get_current_user

# 确保表结构匹配（安全迁移: 只补缺列, 不 drop 整表, 避免清空数据）
try:
    inspector = inspect(engine)
    if 'scheduled_tasks' in inspector.get_table_names():
        cols = {c['name'] for c in inspector.get_columns('scheduled_tasks')}
        # SQLite 仅支持 ADD COLUMN; 缺什么补什么, 有默认值的直接加
        _ADD_COLUMNS = {
            "cron": "VARCHAR(100) DEFAULT '0 9 * * *'",
            "recurring": "BOOLEAN DEFAULT 1",
            "manual": "BOOLEAN DEFAULT 0",
            "durable": "BOOLEAN DEFAULT 1",
            "last_fired_at": "DATETIME",
        }
        with engine.begin() as conn:
            for col, ddl in _ADD_COLUMNS.items():
                if col not in cols:
                    conn.execute(text(f"ALTER TABLE scheduled_tasks ADD COLUMN {col} {ddl}"))
except Exception as e:  # noqa: BLE001
    import logging
    logging.getLogger(__name__).warning("scheduled_tasks 表迁移跳过: %s", e)

router = APIRouter()


def _task_to_dict(task: ScheduledTask) -> dict:
    """将ScheduledTask ORM对象转为前端期望的字典格式"""
    return {
        "id": str(task.id),
        "cron": task.cron,
        "prompt": task.prompt,
        "recurring": task.recurring,
        "manual": task.manual,
        "durable": task.durable,
        "createdAt": int(task.created_at.timestamp() * 1000) if task.created_at else 0,
        "lastFiredAt": int(task.last_fired_at.timestamp() * 1000) if task.last_fired_at else None,
    }


@router.get("")
def list_tasks(db: Session = Depends(get_db)):
    """获取所有定时任务

    注意：当前未按用户过滤，返回全部任务。
    未来应加入 user_id 过滤，确保用户仅能看到自己的任务。
    """
    tasks = db.query(ScheduledTask).order_by(ScheduledTask.created_at.desc()).all()
    return {"tasks": [_task_to_dict(t) for t in tasks]}


@router.post("")
def create_task(current_user = Depends(get_current_user), body: dict = None,
                db: Session = Depends(get_db)):
    """创建定时任务

    注意：当前未关联用户，未来应绑定当前认证用户的 user_id。
    """
    task = ScheduledTask(
        cron=body.get("cron", "0 9 * * *"),
        prompt=body.get("prompt", ""),
        recurring=body.get("recurring", True),
        manual=body.get("manual", False),
        durable=body.get("durable", True),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    # 同步到后台调度器, 让新任务到点自动执行
    try:
        from backend.services.task_scheduler import task_scheduler
        task_scheduler.reload()
    except Exception:  # noqa: BLE001
        pass
    return {"message": "创建成功", "task": _task_to_dict(task)}


@router.delete("/{task_id}")
def delete_task(task_id: int, current_user = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """删除定时任务

    注意：当前未校验任务所属用户，任何用户均可删除任意任务。
    未来应增加 user_id 归属校验。
    """
    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(404, detail="任务不存在")
    db.delete(task)
    db.commit()
    # 同步移除调度器中的对应 job
    try:
        from backend.services.task_scheduler import task_scheduler
        task_scheduler.reload()
    except Exception:  # noqa: BLE001
        pass
    return {"message": "删除成功"}
