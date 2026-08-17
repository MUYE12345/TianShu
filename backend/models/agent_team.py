"""
智能体编排团队模型 — 持久化用户搭建的编排拓扑

背景: 此前编排团队仅存前端 localStorage, 刷新/换浏览器即丢失。
新增 teams 表存储团队名称、模式、节点拓扑与全局指令。
"""
from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, DateTime
from sqlalchemy.sql import func
from backend.database import Base


class AgentTeam(Base):
    """编排团队"""
    __tablename__ = "agent_teams"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, default="未命名团队")
    mode = Column(String(20), default="subagent")        # subagent / team
    nodes = Column(JSON, default=list)                    # [{id,name,role,task,companionId,...}]
    prompt = Column(Text, default="")                     # 全局指令
    is_favorite = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "nodes": self.nodes or [],
            "prompt": self.prompt or "",
            "is_favorite": bool(self.is_favorite),
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
        }
