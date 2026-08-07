"""
提醒模型（陪伴助手）
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from backend.database import Base


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reminder_type = Column(String(30), nullable=False, index=True)  # weather/work_rest/knowledge/task
    title = Column(String(200))
    content = Column(Text)
    priority = Column(Integer, default=1)
    is_read = Column(Boolean, default=False)
    is_handled = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
