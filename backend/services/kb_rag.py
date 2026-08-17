"""
知识库混合检索 RAG — 结构感知分块 + 向量化(DashScope/本地可切换) + FTS5 + RRF + 启发式重排

流程:
  上传解析完成 → 结构感知分块(标题路径/句界) → 嵌入(可切换, 默认 DashScope 1024维) → 存入 Milvus
  问答时 → 问题嵌入做语义检索(Milvus) + 关键词检索(SQLite FTS5) → RRF 融合 → 启发式重排 → Top-K 块拼上下文

存储(迁移后):
  kb_chunks 表(SQLite)      — 分块文本与元数据(父子块)
  kb_chunks_fts(FTS5)       — 全文索引(text 英文 / text_zh 中文2-gram)
  kb_rag_milvus.db          — Milvus Lite 向量库(kb_chunks 集合, 按 kid 过滤, HNSW 索引)

降级策略:
  嵌入不可用 → 纯 FTS5 关键词检索仍可工作(不依赖向量库与嵌入模型)。
"""
import json
import os
import re
import time
from collections import Counter

from sqlalchemy import text

from backend.config import DATA_DIR, settings
from backend.core.cache import request_cache
from backend.core.embedding_adapter import embedding_adapter


INDEX_DIR = DATA_DIR / "kb_rag"  # 向量库目录(分块已迁入 SQLite)


class KBRag:
    COLLECTION = "kb_chunks"

    def __init__(self):
        self._milvus = None
        self._store = {}  # kid -> [{id, kid, source_id, filename, text, section, pos}](内存缓存, DB 为准)

    # ═══════════ 基础设施 ═══════════
    def _ensure_milvus(self):
        """初始化 MilvusClient。集合按实际向量维度在 _ensure_dim 中创建/迁移。"""
        if self._milvus is not None:
            return True
        try:
            from pymilvus import MilvusClient
            os.makedirs(INDEX_DIR, exist_ok=True)
            self._milvus = MilvusClient(str(INDEX_DIR / "kb_rag_milvus.db"))
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[KBRAG] Milvus 初始化失败: {e}")
            self._milvus = None
            return False

    def _create_collection(self, dim: int):
        """创建集合(带 HNSW 索引), 维度用实际向量维度。"""
        self._milvus.create_collection(
            self.COLLECTION, dimension=dim,
            metric_type="COSINE", id_type="int",
            primary_field_name="id", vector_field_name="vector",
            enable_dynamic_field=True,
            index_params={
                "index_type": "HNSW",
                "metric_type": "COSINE",
                "params": {"M": 8, "efConstruction": 200},
            },
        )

    def _ensure_dim(self, dim: int) -> bool:
        """确保集合维度与 dim 一致(不一致则 drop 重建), 并加载集合。返回是否就绪。

        注意: drop 重建会清空整个集合的向量, 因此重建后必须立即对
        **所有知识库**重新建索引回填, 否则除当前知识库外的其它库向量会全部丢失。
        """
        if not self._ensure_milvus():
            return False
        try:
            rebuilt = False
            if not self._milvus.has_collection(self.COLLECTION):
                self._create_collection(dim)
            else:
                info = self._milvus.describe_collection(self.COLLECTION)
                cur = info.get("dimension", 0) if info else 0
                if cur and cur != dim:
                    print(f"[KBRAG] 集合维度 {cur} != 实际 {dim}, 重建集合")
                    self._milvus.drop_collection(self.COLLECTION)
                    self._create_collection(dim)
                    rebuilt = True
            self._milvus.load_collection(self.COLLECTION)
            if rebuilt:
                # 集合被清空重建 → 全量重嵌, 防止其它知识库向量丢失
                self._reindex_all_knowledge_bases()
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[KBRAG] 集合维度检查失败: {e}")
            return False

    def _reindex_all_knowledge_bases(self):
        """维度切换重建集合后, 遍历所有知识库的分块重新嵌入回填向量。"""
        from backend.models.kb import KbChunk
        from backend.database import SessionLocal
        try:
            db = SessionLocal()
            try:
                kids = [r[0] for r in db.query(KbChunk.kb_id).distinct().all()]
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            return
        for kid in kids:
            try:
                chunks = self._db_load_chunks(kid)
                self._store[kid] = chunks
                n_child = sum(1 for c in chunks if c.get("level", "child") == "child")
                if not n_child:
                    continue
                self._reindex(kid, chunks)
                print(f"[KBRAG] 维度迁移重嵌完成: 知识库 {kid} ({n_child} 子块)")
            except Exception as e:  # noqa: BLE001
                print(f"[KBRAG] 维度迁移重嵌失败 {kid}: {e}")

    # ═══════════ 结构感知分块 ═══════════
    @staticmethod
    def _sentence_cut(text: str, max_len: int) -> int | None:
        """在 <= max_len 处找最近的句界(。！？…!? 或换行), 避免句中硬切。找不到返回 None。"""
        region = text[:max_len]
        # 找最近的中英句界标点(含 ASCII 句号 .), 切在其后
        cut = -1
        for idx, ch in enumerate(region):
            if ch in "。！？…!?.":
                cut = idx + 1
        if cut != -1 and max_len - cut <= 100:
            return cut
        nl = region.rfind("\n")
        if nl != -1 and max_len - nl <= 100:
            return nl + 1
        return None

    @staticmethod
    def _split_long(text: str, size: int, overlap: int) -> list:
        """超长段落按句界切多块(带 overlap 衔接)。"""
        pieces = []
        while len(text) > size:
            cut = KBRag._sentence_cut(text, size)
            if cut is None:
                cut = size
            pieces.append(text[:cut])
            text = text[cut - overlap:] if overlap else text[cut:]
        if text.strip():
            pieces.append(text)
        return pieces

    @staticmethod
    def _para_overlap(a_text: str, b_text: str) -> float:
        """相邻段词项重叠率 Jaccard, 用于语义边界启发式判定。"""
        ta, tb = set(KBRag._tokenize(a_text)), set(KBRag._tokenize(b_text))
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / max(len(ta), len(tb))

    def _semantic_boundary(self, prev_text: str, line: str) -> bool:
        """
        判断 line 是否开启新语义段。
        启发式: 词项重叠率 < LOW → 新段; > HIGH → 同段;
        之间 → 对该两段嵌入算余弦, 低于阈值 → 新段。
        嵌入不可用/失败 → 保守判同段(不误切)。
        """
        ov = self._para_overlap(prev_text, line)
        if ov < settings.RAG_SEMANTIC_OVERLAP_LOW:
            return True
        if ov > settings.RAG_SEMANTIC_OVERLAP_HIGH:
            return False
        # 边界带 → 嵌入二次确认
        try:
            from backend.core.embedding_adapter import embedding_adapter
            import numpy as np
            pv = embedding_adapter.encode_one(prev_text[-500:])
            cv = embedding_adapter.encode_one(line[:500])
            if pv is None or cv is None:
                return False
            sim = float(np.dot(pv, cv) / (np.linalg.norm(pv) * np.linalg.norm(cv) + 1e-9))
            return sim < settings.RAG_SEMANTIC_THRESHOLD
        except Exception:  # noqa: BLE001
            return False

    def chunk_text(self, text: str, size: int = None, overlap: int = None) -> list:
        """
        语义分段(结构感知 + 语义边界):
          - Markdown `#` 标题维护 section 路径
          - 相邻段落词项重叠率低/嵌入余弦低 → 新语义段
          - 返回 [{text, section}] —— 每个元素是一个语义段(父块粒度), 供 split_children 拆子块
        """
        size = size or settings.RAG_CHUNK_SIZE
        overlap = overlap or settings.RAG_CHUNK_OVERLAP
        if not text:
            return []
        heading_stack: list = []   # [(level, title)]
        current_section = ""
        sections = []
        cur_paras: list = []
        cur_section = ""

        def section_path():
            return " > ".join(t for _, t in heading_stack)

        def flush():
            nonlocal cur_paras
            if cur_paras:
                sections.append({"text": "\n".join(cur_paras).strip(),
                                 "section": cur_section})
            cur_paras = []

        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            m = re.match(r"^(#{1,6})\s+(.+)$", line)
            if m:
                level, title = len(m.group(1)), m.group(2).strip()
                while heading_stack and level <= heading_stack[-1][0]:
                    heading_stack.pop()
                heading_stack.append((level, title))
                current_section = section_path()
                flush()
                cur_section = current_section
                continue
            # 语义边界: 与前段词项重叠率低 → 新段
            if cur_paras and self._semantic_boundary("\n".join(cur_paras), line):
                flush()
                cur_section = current_section
            cur_paras.append(line)
            # 段组过大时提前封段, 避免单个 section 无限膨胀
            if len("\n".join(cur_paras)) > size * 3:
                flush()
                cur_section = current_section
        flush()
        return [c for c in sections if c["text"]]

    @staticmethod
    def split_children(section_text: str, size: int = None, overlap: int = None) -> list:
        """把语义段(section)按句界切成 ~RAG_CHILD_SIZE 的子块(检索单元)。"""
        size = size or settings.RAG_CHILD_SIZE
        overlap = overlap or settings.RAG_CHUNK_OVERLAP
        if not section_text:
            return []
        if len(section_text) <= size:
            return [section_text] if section_text.strip() else []
        return [p for p in KBRag._split_long(section_text, size, overlap) if p.strip()]

    # ═══════════ 建索引(SQLite + FTS5) ═══════════
    def is_indexed(self, kid: str, source_ids: list) -> bool:
        """来源集合是否已全部建立分块索引(查 SQLite)"""
        from backend.models.kb import KbChunk
        from backend.database import SessionLocal
        try:
            db = SessionLocal()
            try:
                rows = db.query(KbChunk.source_id).filter(
                    KbChunk.kb_id == kid).distinct().all()
                indexed = {r[0] for r in rows}
                return bool(indexed) and set(source_ids) == indexed
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            return False

    # 进程内临时块 id 计数器: 分块阶段用负整数做临时引用, 落库后由 SQLite 自增分配真实 id
    _tmp_seq = 0

    @classmethod
    def _next_tmp(cls) -> int:
        cls._tmp_seq -= 1
        return cls._tmp_seq

    def _chunk_source(self, it: dict, kid: str) -> list:
        """对单个来源做父子分块(临时 id 引用)。返回 [chunks], 落库时换真实自增 id。"""
        text = (it.get("text") or "")[:100000]
        chunks = []
        for sec in self.chunk_text(text):
            parent_tmp = self._next_tmp()
            child_tmps = []
            children = self.split_children(sec["text"])
            for pos, child_text in enumerate(children):
                ctmp = self._next_tmp()
                chunks.append({"tmp": ctmp, "level": "child", "kid": kid,
                               "source_id": it["id"], "filename": it["filename"],
                               "section": sec.get("section", ""), "parent_tmp": parent_tmp,
                               "pos": pos, "text": child_text})
                child_tmps.append(ctmp)
            chunks.append({"tmp": parent_tmp, "level": "parent", "kid": kid,
                           "source_id": it["id"], "filename": it["filename"],
                           "section": sec.get("section", ""), "child_tmps": child_tmps,
                           "pos": 0, "text": sec["text"]})
        return chunks

    def _db_save_chunks(self, kid: str, chunks: list, removed_source_ids: set = None) -> list:
        """把分块写入 SQLite(kb_chunks) + FTS5 双写。返回带真实自增 id 的 chunk 列表。

        id 由数据库自增分配(全局唯一), 避免跨库冲突; FTS rowid 与 Milvus id 都使用它。
        """
        from backend.models.kb import KbChunk
        from backend.database import SessionLocal, zh_ngrams
        if not chunks and not removed_source_ids:
            return []
        try:
            db = SessionLocal()
            try:
                # 1) 删除被移除来源的块 + FTS 记录
                if removed_source_ids:
                    old = db.query(KbChunk).filter(
                        KbChunk.kb_id == kid,
                        KbChunk.source_id.in_(list(removed_source_ids))).all()
                    old_ids = [c.id for c in old]
                    for c in old:
                        db.delete(c)
                    if old_ids:
                        placeholders = ",".join(f":id{i}" for i in range(len(old_ids)))
                        params = {f"id{i}": v for i, v in enumerate(old_ids)}
                        db.execute(
                            text(f"DELETE FROM kb_chunks_fts WHERE rowid IN ({placeholders})"),
                            params)
                # 2) 插入新增块(不指定 id, 由数据库自增)
                obj_by_tmp = {}
                for c in chunks:
                    obj = KbChunk(
                        kb_id=kid, source_id=c["source_id"],
                        level=c.get("level", "child"), section=c.get("section", ""),
                        pos=c.get("pos", 0), text=c["text"],
                    )
                    db.add(obj)
                    obj_by_tmp[c["tmp"]] = obj
                db.flush()  # 分配真实自增 id
                # 3) 回填父子引用(临时 id → 真实 id)
                id_by_tmp = {t: o.id for t, o in obj_by_tmp.items()}
                for c in chunks:
                    obj = obj_by_tmp[c["tmp"]]
                    if c.get("parent_tmp") is not None:
                        obj.parent_id = id_by_tmp.get(c["parent_tmp"], 0)
                    if c.get("child_tmps"):
                        obj.child_ids = json.dumps(
                            [id_by_tmp[t] for t in c["child_tmps"]], ensure_ascii=False)
                # 4) 写 FTS(rowid = 真实 id; 先删同 rowid 残留避免冲突)
                for c in chunks:
                    obj = obj_by_tmp[c["tmp"]]
                    db.execute(text("DELETE FROM kb_chunks_fts WHERE rowid = :id"),
                               {"id": obj.id})
                    db.execute(
                        text("INSERT INTO kb_chunks_fts(rowid, text, text_zh) "
                             "VALUES (:id, :text, :text_zh)"),
                        {"id": obj.id, "text": obj.text,
                         "text_zh": zh_ngrams(obj.text)})
                db.commit()
                # 返回带真实 id 的 chunk 列表(供嵌入与 store 使用), 清理临时字段
                out = []
                for c in chunks:
                    obj = obj_by_tmp[c["tmp"]]
                    out.append({
                        "id": obj.id, "level": obj.level, "kid": kid,
                        "source_id": obj.source_id, "filename": c["filename"],
                        "section": obj.section or "", "parent_id": obj.parent_id or 0,
                        "child_ids": obj.child_ids or "[]",
                        "pos": obj.pos or 0, "text": obj.text or "",
                    })
                return out
            finally:
                db.close()
        except Exception as e:  # noqa: BLE001
            print(f"[KBRAG] SQLite 分块写入失败 {kid}: {e}")
            return []

    def _db_load_chunks(self, kid: str) -> list:
        """从 SQLite 读分块(内存缓存缺失时调用); 关联来源取 filename。"""
        from backend.models.kb import KbChunk, KbSource
        from backend.database import SessionLocal
        try:
            db = SessionLocal()
            try:
                rows = db.query(KbChunk).filter(KbChunk.kb_id == kid).order_by(
                    KbChunk.id).all()
                # 一次性取来源 filename 映射
                filenames = {}
                for s in db.query(KbSource).filter(KbSource.kb_id == kid).all():
                    filenames[s.id] = s.filename
                out = []
                for r in rows:
                    c = r.to_dict()
                    c["filename"] = filenames.get(c["source_id"], "")
                    out.append(c)
                return out
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            return []

    def _remove_sources_from_milvus(self, kid: str, source_ids: set):
        """从 Milvus 删除指定来源的向量(增量删除)。"""
        if not source_ids or not self._ensure_milvus():
            return
        try:
            ids = ", ".join(f'"{s}"' for s in source_ids)
            self._milvus.delete(
                self.COLLECTION, filter=f'kid == "{kid}" and source_id in [{ids}]')
        except Exception as e:  # noqa: BLE001
            print(f"[KBRAG] 增量删除向量失败 {kid}: {e}")

    def _embed_children(self, kid: str, children: list):
        """只对给定子块列表做嵌入并插入 Milvus(增量补嵌)。"""
        if not children:
            return
        texts = [c["text"][:1000] for c in children]
        vectors = embedding_adapter.encode(texts)
        if vectors is None:
            print(f"[KBRAG] 嵌入不可用, 知识库 {kid} 新增块仅保留文本索引")
            return
        vec_dim = len(vectors[0])
        if not self._ensure_dim(vec_dim):
            return
        data = [{"id": c["id"], "vector": vectors[i],
                 "text": c["text"][:1000], "kid": kid,
                 "source_id": c["source_id"], "filename": c["filename"],
                 "section": c.get("section", "")}
                for i, c in enumerate(children)]
        try:
            self._milvus.insert(self.COLLECTION, data=data)
        except Exception as e:  # noqa: BLE001
            print(f"[KBRAG] 向量写入失败: {e}")

    def ensure_index(self, kid: str, items: list):
        """增量建索引(SQLite + FTS5 + Milvus): items=[{id, filename, text}]

        来源集合完全一致 → 幂等跳过;
        有新增来源 → 只为新增来源分块+嵌入;
        有来源被删除 → 只移除对应块(SQLite/FTS/Milvus)。
        不再整库重建, 大库新增单文档成本从 O(全库) 降到 O(单文档)。
        """
        existing = self._store.get(kid)
        if existing is None:
            existing = self._db_load_chunks(kid)
            self._store[kid] = existing
        existing_ids = {c["source_id"] for c in existing}
        target_ids = {i["id"] for i in items}

        # 1) 完全一致: 幂等返回
        if existing and existing_ids == target_ids:
            return existing

        # 2) 移除被删除来源的块(SQLite/FTS + Milvus 向量)
        removed_ids = existing_ids - target_ids
        if removed_ids:
            existing = [c for c in existing if c["source_id"] not in removed_ids]
            self._db_save_chunks(kid, [], removed_source_ids=removed_ids)
            self._remove_sources_from_milvus(kid, removed_ids)

        # 3) 新增来源: 分块 + 增量补嵌
        new_items = [i for i in items if i["id"] not in existing_ids]
        added = []
        if new_items:
            for it in new_items:
                new_chunks = self._chunk_source(it, kid)
                added.extend(new_chunks)
            # 落库并拿回真实自增 id
            saved = self._db_save_chunks(kid, added)
            if saved:
                existing.extend(saved)
            # 只嵌新增的子块(用真实 id)
            new_children = [c for c in saved if c.get("level", "child") == "child"]
            self._embed_children(kid, new_children)

        self._store[kid] = existing
        n_child = sum(1 for c in existing if c.get("level", "child") == "child")
        print(f"[KBRAG] 知识库 {kid} 增量索引: 新增 {len(new_items)} 来源 / 移除 {len(removed_ids)} / 现 {len(existing)} 条目({n_child} 子块)")
        return existing

    def drop_index(self, kid: str):
        """删除知识库/来源后清理索引(SQLite + FTS + Milvus)。"""
        from backend.models.kb import KbChunk
        from backend.database import SessionLocal
        from sqlalchemy import text as _text
        self._store.pop(kid, None)
        try:
            db = SessionLocal()
            try:
                ids = [r[0] for r in db.query(KbChunk.id).filter(KbChunk.kb_id == kid).all()]
                db.query(KbChunk).filter(KbChunk.kb_id == kid).delete()
                if ids:
                    # SQLite 不支持 IN :param, 展开占位符; 参数用 dict 列表(SQLAlchemy 2.x)
                    placeholders = ",".join(f":id{i}" for i in range(len(ids)))
                    params = {f"id{i}": v for i, v in enumerate(ids)}
                    db.execute(_text(f"DELETE FROM kb_chunks_fts WHERE rowid IN ({placeholders})"),
                               params)
                db.commit()
            finally:
                db.close()
        except Exception as e:  # noqa: BLE001
            print(f"[KBRAG] 清理 SQLite 索引失败 {kid}: {e}")
        try:
            if self._ensure_milvus():
                self._milvus.delete(self.COLLECTION, filter=f'kid == "{kid}"')
        except Exception:  # noqa: BLE001
            pass

    def _reindex(self, kid: str, chunks: list):
        if not chunks:
            return
        # 只嵌子块(检索单元); 父块仅存 JSON 供上下文注入
        children = [c for c in chunks if c.get("level", "child") == "child"]
        if not children:
            return
        texts = [c["text"][:1000] for c in children]
        vectors = embedding_adapter.encode(texts)
        if vectors is None:
            print(f"[KBRAG] 嵌入不可用, 知识库 {kid} 仅保留 BM25 文本索引")
            return
        # 集合维度跟随实际向量维度(嵌入 provider 切换时可自动迁移)
        vec_dim = len(vectors[0])
        if not self._ensure_dim(vec_dim):
            return
        try:
            self._milvus.delete(self.COLLECTION, filter=f'kid == "{kid}"')
        except Exception:  # noqa: BLE001
            pass
        data = [{"id": c["id"], "vector": vectors[i],
                 "text": c["text"][:1000], "kid": kid,
                 "source_id": c["source_id"], "filename": c["filename"],
                 "section": c.get("section", "")}
                for i, c in enumerate(children)]
        try:
            self._milvus.insert(self.COLLECTION, data=data)
        except Exception as e:  # noqa: BLE001
            print(f"[KBRAG] 向量写入失败: {e}")

    # ═══════════ 语义检索 (Milvus) ═══════════
    def _semantic_search(self, kid: str, query: str, limit: int = 30,
                         source_ids: list = None) -> list:
        q = embedding_adapter.encode_one(query)
        if q is None:
            return []
        if not self._ensure_dim(len(q)):
            return []
        try:
            flt = f'kid == "{kid}"'
            if source_ids:
                ids = ", ".join(f'"{s}"' for s in source_ids)
                flt += f" and source_id in [{ids}]"
            hits = self._milvus.search(
                self.COLLECTION, data=[q],
                limit=limit, filter=flt,
                output_fields=["id", "text", "section", "source_id", "filename"],
                search_params={"metric_type": "COSINE", "params": {"efSearch": 64}},
            )
        except Exception as e:  # noqa: BLE001
            print(f"[KBRAG] Milvus 检索失败: {e}")
            return []
        out = []
        for hit in (hits or [[]])[0]:
            out.append({"id": hit.get("id"),
                        "sim": hit.get("distance", 0),
                        "source_id": (hit.get("entity") or {}).get("source_id", ""),
                        "filename": (hit.get("entity") or {}).get("filename", ""),
                        "section": (hit.get("entity") or {}).get("section", "")})
        return out

    # ═══════════ 关键词检索 (FTS5, 替代手写 BM25) ═══════════
    @staticmethod
    def _tokenize(text: str) -> list:
        """保留: 供重排阶段的词项覆盖度计算使用。"""
        tokens = []
        for i, ch in enumerate(text):
            if "一" <= ch <= "鿿":
                if i > 0 and "一" <= text[i - 1] <= "鿿":
                    tokens.append(text[i - 1:i + 1])
                tokens.append(ch)
        tokens.extend(re.findall(r"[a-zA-Z]{2,}", text.lower()))
        return tokens

    def _fts_search(self, kid: str, query: str, limit: int = 30,
                    source_ids: list = None) -> list:
        """FTS5 关键词检索(kb_chunks_fts): 返回与旧 BM25 兼容的结构。

        - text 列: unicode61 分词(英文)
        - text_zh 列: 中文 2-gram(查询同样切分)
        命中块再从 kb_chunks 表取元数据。
        """
        from backend.database import SessionLocal, zh_ngrams
        from sqlalchemy import text as _text
        if not query or not query.strip():
            return []
        q = query.strip()
        # 构造 FTS 查询: 对中文 2-gram 后的查询串做 OR 匹配
        zh_q = zh_ngrams(q)
        # 2-gram 空格已由 zh_ngrams 生成; 转成 FTS OR 表达式
        terms_zh = [t for t in zh_q.split() if t]
        match_parts = []
        if terms_zh:
            match_parts.append(" OR ".join(f'"{t}"' for t in terms_zh))
        # 英文词原样(unicode61 自动分词)
        en_terms = re.findall(r"[a-zA-Z][a-zA-Z0-9_]{1,}", q.lower())
        match_parts.extend(f'"{t}"' for t in en_terms)
        if not match_parts:
            return []
        match_expr = " OR ".join(match_parts)
        try:
            db = SessionLocal()
            try:
                # 先用 FTS 找到命中的 rowid(按 bm25 相关度排序)
                rows = db.execute(
                    _text("SELECT rowid, bm25(kb_chunks_fts) AS score "
                          "FROM kb_chunks_fts WHERE kb_chunks_fts MATCH :m "
                          "ORDER BY score LIMIT :lim"),
                    {"m": match_expr, "lim": limit * 3},
                ).fetchall()
                hit_ids = [r[0] for r in rows]
                if not hit_ids:
                    return []
                # 再取 chunk 元数据(filename 从 _store 关联, 已带)
                from backend.models.kb import KbChunk
                chunks = db.query(KbChunk).filter(KbChunk.id.in_(hit_ids)).all()
                by_id = {c.id: c for c in chunks}
                filename_by_id = {}
                for c in self._store.get(kid, []):
                    if c.get("id") in filename_by_id:
                        continue
                    filename_by_id[c["id"]] = c.get("filename", "")
                out = []
                for rid, score in rows:
                    c = by_id.get(rid)
                    if not c:
                        continue
                    if source_ids and c.source_id not in source_ids:
                        continue
                    out.append({"id": c.id, "bm25": -float(score),
                                "source_id": c.source_id,
                                "filename": filename_by_id.get(c.id, ""),
                                "section": c.section or "", "pos": c.pos or 0})
                out.sort(key=lambda x: x["bm25"], reverse=True)
                return out[:limit]
            finally:
                db.close()
        except Exception as e:  # noqa: BLE001
            print(f"[KBRAG] FTS5 检索失败 {kid}: {e}")
            return []

    # ═══════════ 混合检索 (核心) ═══════════
    def _index_version(self, kid: str) -> str:
        """索引版本号: SQLite 中该库的分块数 + 最大 id(反映来源增删)。"""
        from backend.models.kb import KbChunk
        from backend.database import SessionLocal
        try:
            db = SessionLocal()
            try:
                cnt = db.query(KbChunk).filter(KbChunk.kb_id == kid).count()
                mx = db.query(KbChunk.id).filter(KbChunk.kb_id == kid).order_by(
                    KbChunk.id.desc()).first()
                return f"{cnt}:{mx[0] if mx else 0}"
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            return "0"

    def retrieve(self, kid: str, query: str, top_k: int = None,
                 source_ids: list = None, use_cache: bool = True) -> list:
        """
        混合检索: FTS5 关键词 + 语义(Milvus) → RRF 融合 → 启发式重排。
        返回 [{id, source_id, filename, section, text, score}]，前端引用用。
        """
        top_k = top_k or settings.RAG_TOP_K
        # 缓存 key 必须含索引版本: 否则上传新文档后旧缓存仍命中
        cache_key = f"rag:{kid}:{self._index_version(kid)}:{query}:{top_k}:{sorted(source_ids or [])}"
        if use_cache:
            cached = request_cache.get(cache_key)
            if cached is not None:
                return cached

        # 分块从 SQLite 加载(内存缓存)
        chunks = self._store.get(kid)
        if chunks is None:
            chunks = self._db_load_chunks(kid)
            self._store[kid] = chunks
        if not chunks:
            return []

        cand = settings.RAG_CANDIDATE_K
        bm = self._fts_search(kid, query, cand, source_ids)
        sem = self._semantic_search(kid, query, cand, source_ids)

        # ── RRF 融合 ──
        k = 60
        rrf = {}
        for rank, it in enumerate(bm):
            rrf[it["id"]] = rrf.get(it["id"], 0) + 1 / (k + rank + 1)
        for rank, it in enumerate(sem):
            rrf[it["id"]] = rrf.get(it["id"], 0) + 1 / (k + rank + 1)

        # ── 启发式重排: 归一化分数 + 位置/标题/章节加权 ──
        bm_by_id = {it["id"]: it for it in bm}
        sem_by_id = {it["id"]: it for it in sem}
        max_bm = max((it["bm25"] for it in bm), default=0.0) or 1.0
        best_rrf = max(rrf.values(), default=0.0) or 1e-9
        by_id = {c["id"]: c for c in chunks}
        q_terms = set(self._tokenize(query))

        reranked = []
        for cid, sc in rrf.items():
            c = by_id.get(cid)
            if not c:
                continue
            bm25 = bm_by_id.get(cid, {}).get("bm25", 0.0)
            sim = sem_by_id.get(cid, {}).get("sim", 0.0)
            bm_norm = bm25 / max_bm if bm25 else 0.0
            sim_norm = max(0.0, sim)
            # RRF 归一化(相对第一名) → 0~1 量纲
            rrf_norm = sc / best_rrf
            # 加权融合: 语义/排名为主, 关键词为辅
            final = 0.4 * rrf_norm + 0.4 * sim_norm + 0.2 * bm_norm
            # 标题/章节命中加分
            if c["filename"] and any(t in c["filename"].lower() for t in q_terms):
                final += 0.15
            section = c.get("section", "")
            if section and any(t in section.lower() for t in q_terms):
                final += 0.10
            # 文档前部位置加权(摘要/引言常在前段)
            pos = c.get("pos", 0)
            final += max(0.0, 1.0 - pos / 50.0) * 0.05
            # 附带父块上下文(整 section), 供注入用
            parent_text = ""
            if c.get("parent_id") is not None:
                parent = by_id.get(c["parent_id"])
                if parent:
                    parent_text = parent.get("text", "")[:settings.RAG_PARENT_MAX_CHARS]
            reranked.append({**c, "score": round(final, 6), "parent_text": parent_text})

        reranked.sort(key=lambda x: x["score"], reverse=True)
        out = reranked[:top_k]
        if use_cache:
            request_cache.set(cache_key, out, ttl=settings.RAG_RETRIEVE_CACHE_TTL)
        return out

    def stats(self, kid: str) -> int:
        """子块数量(检索单元)。"""
        from backend.models.kb import KbChunk
        from backend.database import SessionLocal
        try:
            db = SessionLocal()
            try:
                return db.query(KbChunk).filter(
                    KbChunk.kb_id == kid, KbChunk.level == "child").count()
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            return 0


kb_rag = KBRag()
