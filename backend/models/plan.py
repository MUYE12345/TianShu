"""
每日规划模型
"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from backend.database import Base


class DailyPlan(Base):
    __tablename__ = "daily_plans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_date = Column(Date, nullable=False)
    title = Column(String(200))
    items = Column(JSON, default=list)  # [{content, done, time, priority}]
    note = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("user_id", "plan_date", name="uq_user_plan_date"),)
