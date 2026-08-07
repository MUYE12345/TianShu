"""
每日规划服务
"""
from datetime import date, datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from backend.models.plan import DailyPlan


class PlanService:
    """规划服务"""

    def get_today(self, db: Session, user_id: int = 1) -> Optional[dict]:
        return self.get_by_date(db, date.today(), user_id)

    def get_by_date(self, db: Session, plan_date: date, user_id: int = 1) -> Optional[dict]:
        plan = db.query(DailyPlan).filter(
            DailyPlan.user_id == user_id,
            DailyPlan.plan_date == plan_date,
        ).first()
        if not plan:
            return None
        return {"id": plan.id, "date": str(plan.plan_date), "title": plan.title or "",
                "items": plan.items or [], "note": plan.note or ""}

    def upsert(self, db: Session, plan_date: date, title: str = "", items: list = None,
               note: str = "", user_id: int = 1) -> dict:
        plan = db.query(DailyPlan).filter(
            DailyPlan.user_id == user_id, DailyPlan.plan_date == plan_date
        ).first()
        if plan:
            plan.title = title
            if items is not None:
                plan.items = items
            plan.note = note
        else:
            plan = DailyPlan(user_id=user_id, plan_date=plan_date,
                             title=title, items=items or [], note=note)
            db.add(plan)
        db.commit()
        db.refresh(plan)
        return {"id": plan.id, "date": str(plan.plan_date), "title": plan.title,
                "items": plan.items, "note": plan.note}


plan_service = PlanService()
