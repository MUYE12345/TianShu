"""
记忆模型（对话长期记忆）
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from backend.database import Base


class Memory(Base):
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    memory_type = Column(String(20), nullable=False, index=True)  # conversation/preference/knowledge/task
    content = Column(Text, nullable=False)
    embedding_id = Column(String(100))    # ChromaDB向量ID
    source = Column(String(50))           # chat / news / paper / manual
    importance = Column(Integer, default=1)  # 1-5
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, server_default=func.now())
