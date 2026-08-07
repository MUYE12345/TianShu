"""
推送日志模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from backend.database import Base


class PushLog(Base):
    __tablename__ = "push_logs"

    id = Column(Integer, primary_key=True, index=True)
    channel = Column(String(20), nullable=False)      # feishu / qqmail
    push_type = Column(String(20), nullable=False)    # daily_news / current_news / test
    status = Column(String(20), nullable=False)       # success / failed
    content_summary = Column(String(200))
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
