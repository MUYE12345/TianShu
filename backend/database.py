"""
数据库引擎与会话管理
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from backend.config import settings

DATABASE_URL = settings.DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    pool_pre_ping=True,
    echo=settings.DEBUG,
)


def _enable_sqlite_fk():
    """SQLite 默认关闭外键约束: 启用后 ON DELETE CASCADE 才真正生效
    (知识库/来源/会话等删除时的级联清理依赖它)。"""
    if "sqlite" not in DATABASE_URL:
        return
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


_enable_sqlite_fk()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI依赖注入: 获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库表

    显式导入 backend.models 以注册全部 ORM 模型到 Base.metadata
    (否则 create_all 可能因模型未导入而静默建空表)。
    """
    import backend.models  # noqa: F401  注册所有模型
    Base.metadata.create_all(bind=engine)
    _init_kb_fts()


# ═══════════════════════════════════════
# 知识库分块全文索引(FTS5)
# ═══════════════════════════════════════

def _zh_ngrams(text: str) -> str:
    """中文 2-gram 切分(用于 FTS 检索): 连续中文切成相邻字符对, 其余原样保留。

    如 "深度学习" → "深度 度学 学习"; 英文 token 原样。
    查询时对 query 同样切分, 实现中文子串/双字检索。
    """
    import re
    out = []
    # 中文连续段
    for seg in re.split(r'([\u4e00-\u9fff]+)', text or ""):
        if not seg:
            continue
        if re.fullmatch(r'[\u4e00-\u9fff]+', seg):
            if len(seg) == 1:
                out.append(seg)
            else:
                out.append(" ".join(seg[i:i + 2] for i in range(len(seg) - 1)))
                # 单字也索引, 保证短查询可命中
                out.append(" ".join(seg))
        else:
            out.append(seg)
    return " ".join(x for x in out if x)


def _init_kb_fts():
    """创建 kb_chunks 的 FTS5 虚拟表(幂等)。

    独立 FTS 表(非外部内容表): 由应用层(kb_rag)在写 kb_chunks 时显式双写,
    因此无需 SQLite 触发器(触发器无法调用 Python 的 2-gram 分词)。
    - text:   原始文本(unicode61 分词, 英文检索)
    - text_zh:中文 2-gram 切分文本(中文检索)

    修复: 若 FTS 表存在但为空, 而 kb_chunks 有数据(例如 FTS 表被重建),
    启动时自动回填, 避免检索静默失效。
    """
    if "sqlite" not in DATABASE_URL:
        return
    with engine.begin() as conn:
        conn.exec_driver_sql("""
            CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5(
                text, text_zh,
                tokenize='unicode61'
            )
        """)
    # 自动回填: FTS 空但分块有数据
    try:
        from sqlalchemy import text as _t
        with engine.begin() as conn:
            fts_cnt = conn.execute(_t("SELECT count(*) FROM kb_chunks_fts")).scalar() or 0
            chunk_cnt = conn.execute(_t("SELECT count(*) FROM kb_chunks")).scalar() or 0
        if fts_cnt == 0 and chunk_cnt > 0:
            from backend.models.kb import KbChunk
            from backend.database import SessionLocal
            db = SessionLocal()
            try:
                rows = db.query(KbChunk).order_by(KbChunk.id).all()
                with engine.begin() as conn:
                    for r in rows:
                        conn.execute(
                            _t("INSERT INTO kb_chunks_fts(rowid, text, text_zh) "
                               "VALUES (:id, :t, :zh)"),
                            {"id": r.id, "t": r.text or "", "zh": _zh_ngrams(r.text or "")})
                import logging
                logging.getLogger(__name__).info("[FTS] 自动回填 %d 条分块索引", len(rows))
            finally:
                db.close()
    except Exception as e:  # noqa: BLE001
        print(f"[FTS] 自动回填失败: {e}")


def zh_ngrams(text: str) -> str:
    """对外暴露中文 2-gram 切分(供 kb_rag 查询侧使用)。"""
    return _zh_ngrams(text)
