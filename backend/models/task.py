"""
定时任务模型
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from backend.database import Base


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cron = Column(String(100), nullable=False)
    prompt = Column(Text, nullable=False, default="")
    recurring = Column(Boolean, default=True)
    manual = Column(Boolean, default=False)
    durable = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    last_fired_at = Column(DateTime, nullable=True, default=None)
