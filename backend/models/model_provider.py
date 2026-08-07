"""
模型提供商模型
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from backend.database import Base


class ModelProvider(Base):
    __tablename__ = "model_providers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    provider = Column(String(50), default="openai")
    api_base = Column(String(500), nullable=False)
    api_key = Column(Text, default="")
    model_name = Column(String(200), nullable=False)
    model_type = Column(String(20), default="llm")
    thinking_mode = Column(Boolean, default=False)
    thinking_budget = Column(Integer, default=4000)
    vision_support = Column(Boolean, default=False)
    embedding_dimensions = Column(Integer, nullable=True)
    temperature = Column(String(20), default="0.7")
    max_tokens = Column(Integer, default=8192)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
