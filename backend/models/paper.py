"""
论文解析模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.database import Base


class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    authors = Column(JSON, default=list)
    abstract = Column(Text)
    source = Column(String(20), default="upload")   # upload / arxiv
    source_url = Column(String(500))
    pdf_path = Column(String(500))
    pages = Column(Integer, default=0)
    status = Column(String(20), default="pending")  # pending / ocr_done / parsed / error
    created_at = Column(DateTime, server_default=func.now())

    paper_pages = relationship("PaperPage", back_populates="paper", cascade="all, delete-orphan")
    figures = relationship("PaperFigure", back_populates="paper", cascade="all, delete-orphan")


class PaperPage(Base):
    __tablename__ = "paper_pages"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False)
    page_num = Column(Integer, nullable=False)
    image_path = Column(String(500))
    ocr_text = Column(Text)
    translated_text = Column(Text)
    parsed_content = Column(JSON)
    para_boxes = Column(JSON)  # [{x0,y0,x1,y1,text}] 段落框（像素坐标，对应页面图）

    paper = relationship("Paper", back_populates="paper_pages")


class PaperFigure(Base):
    __tablename__ = "paper_figures"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False)
    page_num = Column(Integer)
    image_path = Column(String(500))
    caption = Column(Text)
    llm_explanation = Column(Text)

    paper = relationship("Paper", back_populates="figures")
