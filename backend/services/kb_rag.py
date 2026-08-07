"""
知识库混合检索 RAG — 结构感知分块 + 向量化(DashScope/本地可切换) + BM25 + RRF + 启发式重排

流程:
  上传解析完成 → 结构感知分块(标题路径/句界) → 嵌入(可切换, 默认 DashScope 1024维) → 存入 Milvus
  问答时 → 问题嵌入做语义检索 + BM25 关键词检索 → RRF 融合 → 启发式重排 → Top-K 块拼上下文

存储:
  data/kb_rag/{kid}_chunks.json   — 每库分块文本(含 source_id/filename/section/pos)
  data/kb_rag/kb_rag_milvus.db    — Milvus Lite 向量库(kb_chunks 集合, 按 kid 过滤, HNSW 索引)

降级策略:
  嵌入不可用 → 纯 BM25 关键词检索仍可工作(不依赖向量库与嵌入模型)。
"""
import json
import math
import os
import re
import time
from collections import Counter

from backend.config import DATA_DIR, settings
from backend.core.cache import request_cache
from backend.core.embedding_adapter import embedding_adapter


INDEX_DIR = DATA_DIR / "kb_rag"  # 分块文本与向量库目录


class KBRag:
    COLLECTION = "kb_chunks"

    def __init__(self):
        self._milvus = None
        self._store = {}  # kid -> [{id, kid, source_id, filename, text, section, pos}]

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
        """确保集合维度与 dim 一致(不一致则 drop 重建), 并加载集合。返回是否就绪。"""
        if not self._ensure_milvus():
            return False
        try:
            if not self._milvus.has_collection(self.COLLECTION):
                self._create_collection(dim)
            else:
                info = self._milvus.describe_collection(self.COLLECTION)
                cur = info.get("dimension", 0) if info else 0
                if cur and cur != dim:
                    print(f"[KBRAG] 集合维度 {cur} != 实际 {dim}, 重建集合")
                    self._milvus.drop_collection(self.COLLECTION)
                    self._create_collection(dim)
            self._milvus.load_collection(self.COLLECTION)
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[KBRAG] 集合维度检查失败: {e}")
            return False

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

    # ═══════════ 建索引 ═══════════
    def is_indexed(self, kid: str, source_ids: list) -> bool:
        idx_file = INDEX_DIR / f"{kid}_chunks.json"
        if not idx_file.exists():
            return False
        try:
            chunks = json.loads(idx_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return False
        indexed = {c["source_id"] for c in chunks}
        return bool(chunks) and set(source_ids) == indexed

    def ensure_index(self, kid: str, items: list):
        """items: [{id, filename, text}]，来源集合变化才重建分块索引。"""
        if self.is_indexed(kid, [i["id"] for i in items]):
            try:
                self._store[kid] = json.loads(
                    (INDEX_DIR / f"{kid}_chunks.json").read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
            return self._store.get(kid, [])

        chunks, gid = [], 0
        for it in items:
            text = (it.get("text") or "")[:100000]
            # 父子分块: 语义段 → 父块(整段) + 子块(~250字, 检索单元)
            for si, sec in enumerate(self.chunk_text(text)):
                # 父块先占独立 id(避免与首个子块 id 冲突), 子块从 parent_id+1 开始
                parent_id = gid
                gid += 1
                child_ids = []
                children = self.split_children(sec["text"])
                for pos, child_text in enumerate(children):
                    chunks.append({"id": gid, "level": "child", "kid": kid,
                                   "source_id": it["id"], "filename": it["filename"],
                                   "section": sec.get("section", ""), "parent_id": parent_id,
                                   "pos": pos, "text": child_text})
                    child_ids.append(gid)
                    gid += 1
                chunks.append({"id": parent_id, "level": "parent", "kid": kid,
                               "source_id": it["id"], "filename": it["filename"],
                               "section": sec.get("section", ""), "child_ids": child_ids,
                               "pos": 0, "text": sec["text"]})
        self._store[kid] = chunks
        os.makedirs(INDEX_DIR, exist_ok=True)
        (INDEX_DIR / f"{kid}_chunks.json").write_text(
            json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
        self._reindex(kid, chunks)
        n_child = sum(1 for c in chunks if c.get("level", "child") == "child")
        print(f"[KBRAG] 知识库 {kid} 索引完成: {n_child} 子块 / {len(chunks)} 总条目")
        return chunks

    def drop_index(self, kid: str):
        """删除知识库/来源后清理索引。"""
        self._store.pop(kid, None)
        try:
            (INDEX_DIR / f"{kid}_chunks.json").unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
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

    # ═══════════ BM25 关键词检索 ═══════════
    @staticmethod
    def _tokenize(text: str) -> list:
        tokens = []
        for i, ch in enumerate(text):
            if "一" <= ch <= "鿿":
                if i > 0 and "一" <= text[i - 1] <= "鿿":
                    tokens.append(text[i - 1:i + 1])
                tokens.append(ch)
        tokens.extend(re.findall(r"[a-zA-Z]{2,}", text.lower()))
        return tokens

    def _bm25_search(self, kid: str, query: str, limit: int = 30,
                     source_ids: list = None) -> list:
        chunks = [c for c in self._store.get(kid, [])
                  if c.get("level", "child") == "child"]
        if not chunks:
            return []
        if source_ids:
            chunks = [c for c in chunks if c["source_id"] in source_ids]
        if not chunks:
            return []
        k1, b = 1.5, 0.75
        docs = [self._tokenize(c["text"]) for c in chunks]
        avg_dl = sum(len(d) for d in docs) / len(docs)
        df = Counter()
        for d in docs:
            for w in set(d):
                df[w] += 1
        q_terms = set(self._tokenize(query))
        scored = []
        for idx, c in enumerate(chunks):
            words = docs[idx]
            score = 0.0
            for term in q_terms:
                tf = words.count(term)
                freq = df.get(term, 0)
                if freq == 0:
                    continue
                idf = math.log((len(chunks) - freq + 0.5) / (freq + 0.5) + 1)
                score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * len(words) / avg_dl))
            if score > 0:
                scored.append({"id": c["id"], "bm25": score,
                               "source_id": c["source_id"], "filename": c["filename"],
                               "section": c.get("section", ""), "pos": c.get("pos", 0)})
        scored.sort(key=lambda x: x["bm25"], reverse=True)
        return scored[:limit]

    # ═══════════ 混合检索 (核心) ═══════════
    def retrieve(self, kid: str, query: str, top_k: int = None,
                 source_ids: list = None, use_cache: bool = True) -> list:
        """
        混合检索: BM25 + 语义 → RRF 融合 → 启发式重排。
        返回 [{id, source_id, filename, section, text, score}]，前端引用用。
        """
        top_k = top_k or settings.RAG_TOP_K
        cache_key = f"rag:{kid}:{query}:{top_k}:{sorted(source_ids or [])}"
        if use_cache:
            cached = request_cache.get(cache_key)
            if cached is not None:
                return cached

        chunks = self._store.get(kid)
        if not chunks:
            try:
                chunks = json.loads(
                    (INDEX_DIR / f"{kid}_chunks.json").read_text(encoding="utf-8"))
                self._store[kid] = chunks
            except Exception:  # noqa: BLE001
                chunks = []
        if not chunks:
            return []

        cand = settings.RAG_CANDIDATE_K
        bm = self._bm25_search(kid, query, cand, source_ids)
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
        try:
            chunks = json.loads(
                (INDEX_DIR / f"{kid}_chunks.json").read_text(encoding="utf-8"))
            return sum(1 for c in chunks if c.get("level", "child") == "child")
        except Exception:  # noqa: BLE001
            return 0


kb_rag = KBRag()
