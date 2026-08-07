"""
知识记忆 — BM25 + Milvus 向量 混合检索 + 持久化存储

检索策略:
1. BM25 关键词检索 — 改进版TF-IDF(饱和处理+文档长度归一化)
2. 语义向量检索 — Milvus 向量数据库 (Sentence-Transformers 嵌入)
3. 混合融合 — RRF(倒数排名融合) + 重要性/时效加权

存储策略:
- knowledge_store.json — 完整知识点(内容+元数据)
- knowledge_milvus.db — Milvus Lite 向量库(嵌入向量 + 语义检索)
- 增量更新: 新增知识时只计算新条目的嵌入并 upsert 到 Milvus
"""
import json, os, time, math, re
import numpy as np
from typing import List, Optional, Tuple
from collections import Counter

from backend.config import DATA_DIR


class KnowledgeMemory:
    """知识记忆提供者 (BM25 + Milvus 混合检索)"""

    COLLECTION = "knowledge_semantic"
    EMBED_DIM = 384  # paraphrase-multilingual-MiniLM-L12-v2

    def __init__(self, persist_dir: str = str(DATA_DIR / "chromadb")):
        self.persist_dir = persist_dir
        self._store_path = os.path.join(persist_dir, "knowledge_store.json")
        self._milvus_uri = os.path.join(persist_dir, "knowledge_milvus.db")
        self._fallback_store = []
        self._milvus = None  # MilvusClient (Milvus Lite 本地文件)
        self._embedder = None

    # ── 初始化 ──
    def initialize(self):
        os.makedirs(self.persist_dir, exist_ok=True)
        if os.path.exists(self._store_path):
            try:
                with open(self._store_path, "r", encoding="utf-8") as f:
                    self._fallback_store = json.load(f)
                print(f"[知识记忆] 加载 {len(self._fallback_store)} 条知识")
            except Exception:
                self._fallback_store = []
        # 确保 Milvus 集合存在；存储有数据但向量库为空时回填
        if self._ensure_milvus() and self._fallback_store:
            self._ensure_collection()
            count = self._milvus.get(self.COLLECTION, ids=[0], output_fields=["text"])
            has_data = len(count) > 0 if count else False
            if not has_data:
                self.rebuild_embeddings()

    # ── Milvus 向量库 ──
    def _ensure_milvus(self):
        """惰性初始化 Milvus Lite 客户端"""
        if self._milvus is not None:
            return True
        try:
            from pymilvus import MilvusClient
            self._milvus = MilvusClient(self._milvus_uri)
            return True
        except Exception as e:
            print(f"[知识记忆] Milvus 初始化失败, 语义检索降级: {e}")
            self._milvus = None
            return False

    def _ensure_collection(self):
        if not self._milvus:
            return
        try:
            if not self._milvus.has_collection(self.COLLECTION):
                self._milvus.create_collection(
                    self.COLLECTION, dimension=self.EMBED_DIM,
                    metric_type="COSINE", id_type="int",
                    primary_field_name="id", vector_field_name="vector",
                    enable_dynamic_field=True,
                )
            # Milvus 需要显式 load 才能检索
            self._milvus.load_collection(self.COLLECTION)
        except Exception as e:
            print(f"[知识记忆] 创建/加载 Milvus 集合失败: {e}")

    def _persist(self):
        try:
            with open(self._store_path, "w", encoding="utf-8") as f:
                json.dump(self._fallback_store, f, ensure_ascii=False, indent=2)
        except Exception: pass

    # ── 嵌入模型 ──
    def _get_embedder(self):
        """惰性加载嵌入模型"""
        if self._embedder is not None:
            return self._embedder
        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            print("[知识记忆] 语义模型加载完成")
        except ImportError:
            print("[知识记忆] sentence-transformers未安装, 语义搜索不可用")
            self._embedder = None
        except Exception as e:
            print(f"[知识记忆] 语义模型加载失败: {e}")
            self._embedder = None
        return self._embedder

    def _compute_embedding(self, text: str) -> Optional[np.ndarray]:
        embedder = self._get_embedder()
        if embedder is None:
            return None
        return embedder.encode([text[:500]])[0]

    # ── 存储 ──
    def save(self, content: str, source: str = "", tags: list = None,
             importance: int = 1):
        """保存知识点(含预计算嵌入)"""
        item = {
            "content": content, "source": source,
            "tags": tags or [], "importance": importance,
            "timestamp": time.time(),
        }
        self._fallback_store.append(item)
        self._persist()

        # 增量计算嵌入并 upsert 到 Milvus
        emb = self._compute_embedding(content)
        if emb is not None and self._ensure_milvus():
            self._ensure_collection()
            try:
                self._milvus.upsert(self.COLLECTION, data=[{
                    "id": len(self._fallback_store) - 1,
                    "vector": emb.tolist(),
                    "text": content[:500],
                }])
            except Exception as e:
                print(f"[知识记忆] Milvus upsert 失败: {e}")

    def rebuild_embeddings(self):
        """重建所有嵌入并写入 Milvus(数据变更后调用)"""
        if not self._ensure_milvus():
            return
        try:
            # 清空重建：即使没有数据也要清掉旧向量
            if self._milvus.has_collection(self.COLLECTION):
                self._milvus.drop_collection(self.COLLECTION)
            self._ensure_collection()
        except Exception as e:
            print(f"[知识记忆] Milvus 清库失败: {e}")
            return
        embedder = self._get_embedder()
        if embedder is None or not self._fallback_store:
            return
        try:
            texts = [item["content"][:500] for item in self._fallback_store]
            vectors = embedder.encode(texts)
            data = [{"id": i, "vector": vectors[i].tolist(), "text": texts[i]}
                    for i in range(len(texts))]
            if data:
                self._milvus.insert(self.COLLECTION, data=data)
            print(f"[知识记忆] Milvus 向量重建完成: {len(data)}条")
        except Exception as e:
            print(f"[知识记忆] Milvus 重建失败: {e}")

    # ── BM25 检索 ──
    def _tokenize(self, text: str) -> list:
        tokens = []
        # 中文: 双字词 + 单字
        for i, ch in enumerate(text):
            if '一' <= ch <= '鿿':
                if i > 0 and '一' <= text[i-1] <= '鿿':
                    tokens.append(text[i-1:i+1])  # 双字词
                tokens.append(ch)
        # 英文词
        tokens.extend(re.findall(r'[a-zA-Z]{2,}', text.lower()))
        return tokens

    def _bm25_score(self, query: str, doc_idx: int, doc_freq: dict,
                    total_docs: int, avg_dl: float) -> float:
        """BM25评分"""
        k1, b = 1.5, 0.75  # BM25参数
        q_words = [w for w in self._tokenize(query) if w.strip()]
        doc_text = self._fallback_store[doc_idx]["content"]
        doc_words = self._tokenize(doc_text)
        dl = len(doc_words)

        score = 0.0
        for term in set(q_words):
            tf = doc_words.count(term)
            df = doc_freq.get(term, 0)
            if df == 0:
                continue
            idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1)
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * dl / avg_dl)
            score += idf * numerator / denominator
        return score

    def _bm25_search(self, query: str, limit: int = 10) -> List[dict]:
        """BM25关键词检索"""
        total = len(self._fallback_store)
        if total == 0:
            return []

        # 计算平均文档长度
        all_words = [self._tokenize(item["content"]) for item in self._fallback_store]
        avg_dl = sum(len(w) for w in all_words) / total

        # 计算文档频率
        doc_freq = Counter()
        for words in all_words:
            for w in set(words):
                doc_freq[w] += 1

        results = []
        for idx, item in enumerate(self._fallback_store):
            bm25 = self._bm25_score(query, idx, doc_freq, total, avg_dl)
            if bm25 > 0:
                importance = item.get("importance", 1)
                ts = item.get("timestamp", time.time())
                age_days = (time.time() - ts) / 86400
                time_w = 1.0 if age_days < 7 else max(0.5, 1.0 - (age_days - 7) / 46)
                final_score = bm25 * (0.5 + importance * 0.2) * time_w
                results.append({
                    "content": item["content"],
                    "metadata": {"source": item.get("source", ""),
                                 "importance": importance,
                                 "age_days": round(age_days, 1)},
                    "bm25_score": round(bm25, 4),
                    "final_score": round(final_score, 4),
                    "match_type": "bm25",
                })
        results.sort(key=lambda x: x["final_score"], reverse=True)
        return results[:limit]

    # ── 语义检索 (Milvus) ──
    def _semantic_search(self, query: str, limit: int = 10) -> List[dict]:
        """基于 Milvus 向量数据库的语义相似度检索"""
        if not self._ensure_milvus() or not self._fallback_store:
            return []
        q_emb = self._compute_embedding(query)
        if q_emb is None:
            return []
        self._ensure_collection()
        try:
            hits = self._milvus.search(
                self.COLLECTION, data=[q_emb.tolist()],
                limit=limit, output_fields=["text"],
            )
        except Exception as e:
            print(f"[知识记忆] Milvus 检索失败: {e}")
            return []

        results = []
        for hit in (hits or [[]])[0]:
            idx = hit.get("id")
            sim = hit.get("distance", 0)
            if not isinstance(idx, int) or idx < 0 or idx >= len(self._fallback_store):
                continue
            item = self._fallback_store[idx]
            importance = item.get("importance", 1)
            final_score = sim * (0.5 + importance * 0.2)
            results.append({
                "content": item["content"],
                "metadata": {"source": item.get("source", ""),
                             "importance": importance},
                "sem_similarity": round(sim, 4),
                "final_score": round(final_score, 4),
                "match_type": "semantic",
            })
        return results

    # ── 混合检索 (核心) ──
    def search(self, query: str, limit: int = 5,
               bm25_weight: float = 0.4, semantic_weight: float = 0.6) -> list:
        """
        混合检索: BM25 + 语义, RRF融合

        策略:
        1. 同时执行BM25和语义检索
        2. 用RRF(Reciprocal Rank Fusion)合并排名
        3. 重要性/时效加权

        返回: [{content, metadata, score, match_type, rank_bm25, rank_semantic}]
        """
        # 并行检索
        bm25_results = self._bm25_search(query, limit * 3)
        semantic_results = self._semantic_search(query, limit * 3)

        # RRF融合
        k = 60  # RRF常量
        rrf_scores = {}

        for rank, item in enumerate(bm25_results):
            key = item["content"]
            rrf_scores[key] = rrf_scores.get(key, 0) + 1 / (k + rank + 1)

        for rank, item in enumerate(semantic_results):
            key = item["content"]
            rrf_scores[key] = rrf_scores.get(key, 0) + 1 / (k + rank + 1)

        # 构建最终结果
        merged = []
        seen = set()
        for item in bm25_results + semantic_results:
            content = item["content"]
            if content in seen:
                # 合并同一条目的两种检索信息
                for m in merged:
                    if m["content"] == content:
                        if item["match_type"] == "bm25":
                            m["bm25_score"] = item.get("bm25_score", 0)
                        else:
                            m["sem_similarity"] = item.get("sem_similarity", 0)
                        m["rrf_score"] = rrf_scores.get(content, 0)
                        m["match_type"] = "hybrid"
                        continue
                continue
            seen.add(content)

            entry = {
                "content": content,
                "metadata": item["metadata"],
                "bm25_score": item.get("bm25_score", 0),
                "sem_similarity": item.get("sem_similarity", 0),
                "rrf_score": round(rrf_scores.get(content, 0), 6),
                "match_type": item["match_type"],
            }
            merged.append(entry)

        # 按RRF分数排序
        merged.sort(key=lambda x: x["rrf_score"], reverse=True)
        return merged[:limit]

    # ── 辅助方法 ──
    def get_stats(self) -> dict:
        total = len(self._fallback_store)
        if total == 0:
            return {"total": 0}
        sources = Counter(i.get("source", "?") for i in self._fallback_store)
        tags = Counter(t for i in self._fallback_store for t in i.get("tags", []))
        milvus_count = 0
        if self._milvus:
            try:
                milvus_count = self._milvus.get_collection_stats(self.COLLECTION).get("row_count", 0)
            except Exception:
                milvus_count = -1
        return {
            "total": total,
            "sources": dict(sources.most_common(5)),
            "top_tags": dict(tags.most_common(5)),
            "vector_store": "milvus",
            "milvus_entities": milvus_count,
        }

    def delete(self, query: str) -> int:
        before = len(self._fallback_store)
        removed_idxs = [i for i, item in enumerate(self._fallback_store)
                        if query in item["content"]]
        self._fallback_store = [item for item in self._fallback_store
                                if query not in item["content"]]
        removed = before - len(self._fallback_store)
        if removed:
            self._persist()
            # 索引变化, 重建 Milvus 向量库保证 id 与 store 一致
            self.rebuild_embeddings()
        return removed
