"""
智能体数据模型 — 参考 tz2.0 Agent ORM 设计
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime, JSON
from sqlalchemy.sql import func
from backend.database import Base


class Agent(Base):
    """智能体模型（数据库持久化）"""
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text, default="")
    category = Column(String(50), default="通用")
    model = Column(String(100), default="deepseek-chat")      # 兼容旧字段
    model_id = Column(Integer, default=0)                      # 关联 ModelProvider.id
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=4096)
    system_prompt = Column(Text, default="")
    enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)  # 扩展配置
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
