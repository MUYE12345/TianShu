"""
智能体组模型（多智能体协作配置）
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from backend.database import Base


class AgentGroup(Base):
    __tablename__ = "agent_groups"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, default="")
    agents = Column(JSON, default=list)          # [{name, model, tools, system_prompt}]
    coordination = Column(String(20), default="parallel")  # parallel / sequential
    is_active = Column(Boolean, default=True)
    config = Column(JSON, default=dict)           # 扩展配置（工具列表、模型参数等）
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
