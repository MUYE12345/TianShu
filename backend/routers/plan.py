"""
每日规划路由
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.services.plan_service import plan_service

router = APIRouter()


@router.get("/today")
def get_today(db: Session = Depends(get_db)):
    plan = plan_service.get_today(db)
    if not plan:
        from datetime import date
        return {"date": str(date.today()), "items": []}
    return plan


@router.get("/{plan_date}")
def get_plan(plan_date: str, db: Session = Depends(get_db)):
    from datetime import date
    try:
        d = date.fromisoformat(plan_date)
    except ValueError:
        return {"error": "日期格式错误, 应为YYYY-MM-DD"}
    plan = plan_service.get_by_date(db, d)
    if not plan:
        return {"date": plan_date, "items": []}
    return plan


@router.put("/{plan_date}")
def upsert_plan(plan_date: str, body: dict = None, db: Session = Depends(get_db)):
    from datetime import date
    if not isinstance(body, dict):
        return {"error": "请求体必须为 JSON 对象"}
    try:
        d = date.fromisoformat(plan_date)
    except ValueError:
        return {"error": "日期格式错误"}
    return plan_service.upsert(db, d, body.get("title", ""), body.get("items"), body.get("note", ""))
