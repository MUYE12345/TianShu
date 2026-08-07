"""
陪伴助手路由
"""
from fastapi import APIRouter
from backend.services.companion_service import companion_service

router = APIRouter()


@router.get("/reminders")
def get_reminders():
    reminders = companion_service.check_reminders()
    return {"items": reminders, "total": len(reminders)}


@router.post("/reminders/check")
def check_reminders():
    reminders = companion_service.check_reminders()
    return {"items": reminders, "total": len(reminders)}
