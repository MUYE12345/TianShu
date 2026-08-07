"""
新闻模型（每日新闻 + 时事新闻）
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from backend.database import Base


class DailyNews(Base):
    __tablename__ = "daily_news"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    url = Column(String(1000))
    source = Column(String(50), nullable=False, index=True)  # deep_tech/machine_heart/qbitai/aiera
    source_name = Column(String(50))                         # 深科技/机器之心/量子位/新智元
    summary = Column(Text)
    content = Column(Text)
    ai_summary = Column(Text)
    cover_image = Column(String(500))
    keywords = Column(JSON, default=list)
    is_top = Column(Boolean, default=False)
    published_at = Column(DateTime, index=True)
    created_at = Column(DateTime, server_default=func.now())


class CurrentNews(Base):
    __tablename__ = "current_news"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    url = Column(String(1000))
    section = Column(String(50), nullable=False, index=True)
    summary = Column(Text)
    content = Column(Text)
    ai_summary = Column(Text)
    cover_image = Column(String(500))
    published_at = Column(DateTime, index=True)
    created_at = Column(DateTime, server_default=func.now())


class HotSummary(Base):
    """每日热点摘要（缓存，每天只生成一次）"""
    __tablename__ = "hot_summaries"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), nullable=False, index=True)
    source_title = Column(String(50), default="")
    summary = Column(Text, nullable=False)
    total = Column(Integer, default=0)
    date = Column(String(20), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
