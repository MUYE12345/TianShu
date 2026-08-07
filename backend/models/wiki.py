"""
Wiki笔记模型
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from backend.database import Base


class WikiPage(Base):
    __tablename__ = "wiki_pages"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(200), unique=True, nullable=False, index=True)
    title = Column(String(200), nullable=False)
    page_type = Column(String(20), default="concept")  # concept / entity / source / synthesis
    content = Column(Text, default="")
    tags = Column(JSON, default=list)
    aliases = Column(JSON, default=list)
    backlinks = Column(JSON, default=list)
    is_published = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class WikiVersion(Base):
    """Wiki页面版本历史"""
    __tablename__ = "wiki_versions"

    id = Column(Integer, primary_key=True, index=True)
    page_slug = Column(String(200), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, default="")
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, server_default=func.now())
