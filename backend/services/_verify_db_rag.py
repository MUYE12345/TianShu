# -*- coding: utf-8 -*-
"""验证 kb_rag SQLite+FTS5 改造: 建索引 → FTS 检索(嵌入用 stub 避免真实 API)"""
import sys, logging
sys.path.insert(0, r"D:\LargeModelProject\aa-myagent\Intelligen_housekeeper")
logging.disable(logging.CRITICAL)

from backend.database import init_db, SessionLocal, zh_ngrams
init_db()

import backend.services.kb_rag as kb_mod

# stub 嵌入: 返回固定维度向量, 避免真实 DashScope 调用(验证重点是 SQLite/FTS 逻辑)
def _fake_encode(texts):
    return [[0.1] * 8 for _ in texts]
def _fake_encode_one(text):
    return [0.1] * 8
kb_mod.embedding_adapter.encode = _fake_encode
kb_mod.embedding_adapter.encode_one = _fake_encode_one
# 禁用 Milvus(不依赖向量库)
kb_mod.KBRag._ensure_milvus = lambda self: False
kb_mod.KBRag._ensure_dim = lambda self, dim: False
kb_mod.KBRag._embed_children = lambda self, kid, children: None
kb_mod.KBRag._reindex = lambda self, kid, chunks: None

from backend.services.kb_rag import kb_rag
from backend.models.kb import KbNotebook, KbSource

db = SessionLocal()
kid = "35f3d24c3018"
nb = db.query(KbNotebook).filter(KbNotebook.id == kid).first()
if not nb:
    print("找不到测试知识库")
    sys.exit(0)

sources = db.query(KbSource).filter(KbSource.kb_id == kid).all()
items = [{"id": s.id, "filename": s.filename, "text": (s.text_cache or "")[:20000]} for s in sources]
print(f"来源数: {len(items)}")

chunks = kb_rag.ensure_index(kid, items)
n_child = sum(1 for c in chunks if c.get("level") == "child")
print(f"分块数: {len(chunks)} (子块 {n_child})")

from backend.models.kb import KbChunk
cnt = db.query(KbChunk).filter(KbChunk.kb_id == kid).count()
print(f"SQLite kb_chunks 行数: {cnt}")

print("\nzh_ngrams 示例:", zh_ngrams("智能体设计工具调用")[:80])
for q in ["agent", "工具", "MCP", "Agent"]:
    hits = kb_rag._fts_search(kid, q, limit=3)
    print(f"FTS 查询 '{q}': {len(hits)} 命中, top: {[(h['id'], h['filename'][:22]) for h in hits[:2]]}")

try:
    res = kb_rag.retrieve(kid, "agent 是什么", top_k=3, use_cache=False)
    print(f"\n混合检索 'agent 是什么': {len(res)} 结果")
    for r in res[:3]:
        print(f"  score={r.get('score', 0):.4f} file={r.get('filename','')[:30]}")
except Exception as e:
    print(f"混合检索异常: {type(e).__name__}: {e}")

print(f"\nstats(child): {kb_rag.stats(kid)}")
db.close()
print("\nDONE")
