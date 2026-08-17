"""
知识库 ORM 模型 — 存储迁移(SQLite)核心

背景: 此前知识库依赖 JSON 文件 + 内存 dict(无事务/无权限/并发竞态),
迁移到 SQLite 后支持多用户、团队共享与 RAG 高效检索。
角色模型: admin(每库唯一)/ editor / viewer; admin 可迁移但始终唯一。

文档: docs/KB_DATABASE_MIGRATION.md
"""
from sqlalchemy import (Column, Integer, String, Text, Boolean, DateTime,
                        ForeignKey, Index, UniqueConstraint)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text
from backend.database import Base


class KbNotebook(Base):
    """知识库"""
    __tablename__ = "kb_notebooks"

    id = Column(String(32), primary_key=True)              # uuid4 hex[:12]
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    cover = Column(String(50), default="cover-1")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # 创建者(首个 admin)
    is_public = Column(Boolean, default=False)             # 进入"全部知识"共享区
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    sources = relationship("KbSource", back_populates="notebook",
                           cascade="all, delete-orphan")
    members = relationship("KbMember", back_populates="notebook",
                           cascade="all, delete-orphan")
    chats = relationship("KbChat", back_populates="notebook",
                         cascade="all, delete-orphan")
    artifacts = relationship("KbArtifact", back_populates="notebook",
                             cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description or "",
            "cover": self.cover or "cover-1",
            "owner_id": self.owner_id,
            "is_public": bool(self.is_public),
            "source_count": len(self.sources or []),
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
        }


class KbSource(Base):
    """知识库来源文档"""
    __tablename__ = "kb_sources"

    id = Column(String(32), primary_key=True)              # uuid4 hex[:8]
    kb_id = Column(String(32), ForeignKey("kb_notebooks.id", ondelete="CASCADE"),
                   nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    ext = Column(String(20), default="")
    size = Column(Integer, default=0)
    status = Column(String(20), default="parsing")         # parsing/parsed/failed
    parse_error = Column(Text, default="")
    previewable = Column(Boolean, default=False)
    text_preview = Column(Text, default="")                # 前 3000 字预览
    text_cache = Column(Text, default="")                  # 完整解析文本(原 {fid}.txt)
    file_path = Column(String(500), default="")            # 原件相对路径
    created_at = Column(DateTime, server_default=func.now())

    notebook = relationship("KbNotebook", back_populates="sources")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "ext": self.ext,
            "size": self.size,
            "status": self.status,
            "parse_error": self.parse_error,
            "previewable": bool(self.previewable),
            "text_preview": self.text_preview or "",
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class KbMember(Base):
    """知识库成员(共享)。创建者以 admin 写入; 每库 admin 唯一。"""
    __tablename__ = "kb_members"
    __table_args__ = (
        UniqueConstraint("kb_id", "user_id", name="uq_kb_members_pair"),
        # 部分唯一索引: 每库最多一个 admin(数据库层锁死"管理员唯一")
        Index("uq_kb_members_admin", "kb_id", unique=True,
              sqlite_where=text("role = 'admin'")),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_id = Column(String(32), ForeignKey("kb_notebooks.id", ondelete="CASCADE"),
                   nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False, default="viewer")  # admin/editor/viewer
    created_at = Column(DateTime, server_default=func.now())

    notebook = relationship("KbNotebook", back_populates="members")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kb_id": self.kb_id,
            "user_id": self.user_id,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class KbChat(Base):
    """知识库内会话"""
    __tablename__ = "kb_chats"

    id = Column(String(32), primary_key=True)              # uuid4 hex[:12]
    kb_id = Column(String(32), ForeignKey("kb_notebooks.id", ondelete="CASCADE"),
                   nullable=False, index=True)
    title = Column(String(200), default="新对话")
    source_ids = Column(Text, default="[]")                # JSON 数组: 聚焦文档
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    notebook = relationship("KbNotebook", back_populates="chats")
    messages = relationship("KbMessage", back_populates="chat",
                            cascade="all, delete-orphan")

    def to_dict(self, with_messages: bool = False) -> dict:
        d = {
            "id": self.id,
            "title": self.title,
            "source_ids": self.source_ids or "[]",
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
        }
        if with_messages:
            d["messages"] = [m.to_dict() for m in (self.messages or [])]
        return d


class KbMessage(Base):
    """知识库会话消息"""
    __tablename__ = "kb_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String(32), ForeignKey("kb_chats.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    role = Column(String(20), nullable=False)              # user/assistant
    content = Column(Text, default="")
    citations = Column(Text, default="[]")                 # JSON 引用列表
    created_at = Column(DateTime, server_default=func.now())

    chat = relationship("KbChat", back_populates="messages")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content or "",
            "citations": self.citations or "[]",
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class KbArtifact(Base):
    """知识库产物(文件本体仍在磁盘, DB 存元数据)"""
    __tablename__ = "kb_artifacts"

    id = Column(String(32), primary_key=True)              # uuid4 hex[:8]
    kb_id = Column(String(32), ForeignKey("kb_notebooks.id", ondelete="CASCADE"),
                   nullable=False, index=True)
    kind = Column(String(20), nullable=False)              # html/mindmap/ppt/brief/timeline
    label = Column(String(50), default="")
    title = Column(String(200), default="")
    filename = Column(String(255), default="")             # 磁盘文件名
    style = Column(String(50), default="")
    template = Column(String(50), default="")
    mindmap_type = Column(String(50), default="")
    prompt = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now())

    notebook = relationship("KbNotebook", back_populates="artifacts")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label or "",
            "title": self.title or "",
            "filename": self.filename or "",
            "style": self.style or "",
            "template": self.template or "",
            "mindmap_type": self.mindmap_type or "",
            "prompt": self.prompt or "",
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class KbChunk(Base):
    """知识库分块(父子)。替代 {kid}_chunks.json, 供 RAG 关键词检索(FTS5)使用。

    注意: 向量仍在 Milvus(kb_chunks 集合), 本表存分块文本与元数据,
    id 与 Milvus 中 vector 的 id 保持一致(全局递增)。
    """
    __tablename__ = "kb_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_id = Column(String(32), ForeignKey("kb_notebooks.id", ondelete="CASCADE"),
                   nullable=False, index=True)
    source_id = Column(String(32), ForeignKey("kb_sources.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    level = Column(String(10), default="child")            # parent/child
    section = Column(String(255), default="")
    parent_id = Column(Integer, default=0)                 # 父块 id(child 指向 parent)
    child_ids = Column(Text, default="[]")                 # JSON 数组(parent 存子块列表)
    pos = Column(Integer, default=0)
    text = Column(Text, default="")

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kb_id": self.kb_id, "source_id": self.source_id,
            "level": self.level, "section": self.section or "",
            "parent_id": self.parent_id, "child_ids": self.child_ids or "[]",
            "pos": self.pos, "text": self.text or "",
        }
