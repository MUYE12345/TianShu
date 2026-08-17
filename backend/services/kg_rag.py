"""
轻量实体图 (GraphRAG) — LLM 提取实体/关系 + 跨文档合并 + 检索时邻居扩展

构建:
  父块(整 section)分批喂给主 LLM → 提取 {entities, relations} → 跨文档按规范化名合并节点
  → 批量计算节点嵌入 → 写 data/kb_rag/{kid}_graph.json

检索:
  问题 → 嵌入余弦 + 文本子串匹配种子实体 → 1-hop 邻居 → 命中的 source_ids
  → 由 rag_agent 给这些来源的 chunk 加 graph_boost

图不存在/构建失败 → 恒为空图, 检索退化为纯混合(不阻断)。
"""
import json
import re
from collections import defaultdict

from backend.config import DATA_DIR, settings
from backend.core.embedding_adapter import embedding_adapter

INDEX_DIR = DATA_DIR / "kb_rag"


def _extract_json(text: str):
    """从 LLM 输出剥离围栏并提取第一个 JSON 对象。失败返回 None。"""
    if not text:
        return None
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None


def _llm_extract(batch_text: str):
    """调用主 LLM 批量提取实体+关系。返回 {"entities":[...], "relations":[...]} 或 None。"""
    from backend.core.model_config import model_manager
    llm = model_manager.get_main_llm()
    prompt = f"""你是实体关系抽取器。对下面文本提取"实体"和"实体间关系"，只输出合法 JSON，不要解释、不要额外文字。

严格输出格式：
{{"entities":[{{"name":"实体名","type":"concept|method|tech|person|org|paper|dataset|other","summary":"一句话描述，≤20字"}}],
 "relations":[{{"source":"实体A名","target":"实体B名","relation":"关系描述，如 提出/基于/包含"}}]}}
若没有实体，输出 {{"entities":[],"relations":[]}}

---文本---
{batch_text}
"""
    try:
        out = llm.invoke(prompt)
        return _extract_json(str(out))
    except Exception as e:  # noqa: BLE001
        print(f"[KGRAG] LLM 提取失败: {e}")
        return None


class KnowledgeGraph:
    def __init__(self):
        self._graphs = {}  # kid -> {"nodes": [...], "edges": [...], "adj": {name: [neighbors]}}

    # ── 存取 ──
    def graph_path(self, kid):
        return INDEX_DIR / f"{kid}_graph.json"

    def _load(self, kid) -> dict:
        if kid in self._graphs:
            return self._graphs[kid]
        p = self.graph_path(kid)
        g = {"nodes": [], "edges": []}
        if p.exists():
            try:
                g = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                g = {"nodes": [], "edges": []}
        self._build_adj(g)
        # 磁盘不存 embedding(见 rebuild): 加载后惰性补嵌, 供语义匹配使用。
        # 兼容旧版本文件(可能残留 embedding 字段), 统一剥离并重算。
        nodes = g.get("nodes", [])
        if nodes:
            need_embed = any(n.get("embedding") is None for n in nodes)
            for n in nodes:
                n.pop("embedding", None)
            if need_embed:
                try:
                    self._embed_nodes(nodes)
                except Exception:  # noqa: BLE001
                    pass
        self._graphs[kid] = g
        return g

    @staticmethod
    def _build_adj(g: dict):
        adj = defaultdict(set)
        for e in g.get("edges", []):
            s, t = e.get("source"), e.get("target")
            if s and t:
                adj[s].add(t)
                adj[t].add(s)
        g["adj"] = {k: sorted(v) for k, v in adj.items()}

    def clear(self, kid):
        """删除知识库/来源时清理图。"""
        self._graphs.pop(kid, None)
        try:
            self.graph_path(kid).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass

    # ── 构建 ──
    def build_graph_if_needed(self, kid, source_ids: list) -> bool:
        """图已存在且覆盖当前来源则跳过, 否则全量重建。后台调用。"""
        if not settings.GRAPH_ENABLED:
            return False
        g = self._load(kid)
        existing = set()
        for n in g.get("nodes", []):
            existing.update(n.get("source_ids", []))
        if g.get("nodes") and set(source_ids).issubset(existing):
            return True
        return self.rebuild(kid)

    def _load_parents_from_db(self, kid: str) -> list:
        """从 SQLite kb_chunks 读取父块(替代旧版 {kid}_chunks.json, 分块已迁库)。"""
        try:
            from backend.database import SessionLocal
            from backend.models.kb import KbChunk
            db = SessionLocal()
            try:
                rows = (db.query(KbChunk)
                        .filter(KbChunk.kb_id == kid, KbChunk.level == "parent")
                        .order_by(KbChunk.pos)
                        .all())
                return [{"source_id": r.source_id, "section": r.section or "",
                         "text": r.text or ""}
                        for r in rows if r.text and r.text.strip()]
            finally:
                db.close()
        except Exception as e:  # noqa: BLE001
            print(f"[KGRAG] 读取父块失败: {e}")
            return []

    def rebuild(self, kid) -> bool:
        """从 SQLite 父块提取实体/关系, 跨文档合并节点, 计算嵌入, 写图文件。"""
        parents = self._load_parents_from_db(kid)
        if not parents:
            return False

        batch = max(1, int(settings.GRAPH_BUILD_BATCH or 5))
        nodes, edges = [], []
        node_by_key = {}
        edge_set = set()
        for i in range(0, len(parents), batch):
            grp = parents[i:i + batch]
            text = "\n\n".join(f"[{g['source_id']}] {g['text'][:800]}" for g in grp)
            data = _llm_extract(text)
            if not data:
                continue
            src_ids = {g["source_id"] for g in grp}
            for e in data.get("entities", []):
                name = (e.get("name") or "").strip()
                if not name:
                    continue
                key = name.lower()
                if key not in node_by_key:
                    node_by_key[key] = {"name": name, "type": e.get("type", "concept"),
                                        "summary": e.get("summary", ""), "source_ids": []}
                    nodes.append(node_by_key[key])
                node_by_key[key]["source_ids"] = sorted(set(node_by_key[key]["source_ids"]) | src_ids)
            for r in data.get("relations", []):
                s, t, rel = (r.get("source") or "").strip(), (r.get("target") or "").strip(), (r.get("relation") or "").strip()
                if not s or not t:
                    continue
                sk, tk = s.lower(), t.lower()
                for nm, key in ((s, sk), (t, tk)):
                    if key not in node_by_key:
                        node_by_key[key] = {"name": nm, "type": "concept",
                                            "summary": "", "source_ids": sorted(src_ids)}
                        nodes.append(node_by_key[key])
                ekey = (sk, tk, rel)
                if ekey in edge_set:
                    continue
                edge_set.add(ekey)
                edges.append({"source": s, "target": t, "relation": rel, "weight": 1})

        if nodes:
            self._embed_nodes(nodes)
        g = {"nodes": nodes, "edges": edges}
        self._build_adj(g)
        self._graphs[kid] = g
        try:
            # 磁盘只存元数据: 1024 维嵌入不落盘(节点多时文件体积会暴涨),
            # 加载后按需在内存中重新计算(见 _load 的 lazy 补嵌)。
            disk_nodes = [{k: v for k, v in n.items() if k != "embedding"} for n in nodes]
            self.graph_path(kid).write_text(
                json.dumps({"nodes": disk_nodes, "edges": edges}, ensure_ascii=False),
                encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"[KGRAG] 写图失败: {e}")
        print(f"[KGRAG] 知识库 {kid} 图构建完成: {len(nodes)} 节点 / {len(edges)} 边")
        return bool(nodes)

    def _embed_nodes(self, nodes: list):
        """批量计算节点嵌入(名字+摘要)。失败则清空, 图匹配退化为文本子串。"""
        texts = [f"{n['name']} {n['summary']}".strip()[:200] for n in nodes]
        try:
            vecs = embedding_adapter.encode(texts)
            if vecs:
                for n, v in zip(nodes, vecs):
                    n["embedding"] = v
        except Exception as e:  # noqa: BLE001
            print(f"[KGRAG] 节点嵌入失败: {e}")

    # ── 检索扩展 ──
    def expand(self, kid: str, query: str, limit: int = None) -> dict:
        """
        图扩展: 问题→种子实体→1-hop 邻居→source_ids。
        返回 {"sources": {sid: count}, "entities": [命中实体名], "count": n}。
        空图/失败 → {"sources": {}, "entities": [], "count": 0}。
        """
        g = self._load(kid)
        nodes = g.get("nodes", [])
        empty = {"sources": {}, "entities": [], "count": 0}
        if not nodes:
            return empty
        limit = limit or settings.GRAPH_ENTITY_TOP_K
        seed = self._match_entities(query, nodes, limit)
        if not seed:
            return empty
        adj = g.get("adj", {})
        neighbor_names = set(seed)
        for name in seed:
            neighbor_names.update(adj.get(name, []) or [])
        sources = defaultdict(int)
        name_lower = {n["name"].lower(): n for n in nodes}
        for name in neighbor_names:
            n = name_lower.get(name.lower())
            if n:
                for sid in n.get("source_ids", []):
                    sources[sid] += 1
        return {"sources": dict(sources), "entities": seed, "count": len(sources)}

    def _match_entities(self, query: str, nodes: list, limit: int) -> list:
        """文本子串匹配(优先) + 嵌入余弦(补充), 返回 top 实体名。"""
        hits = []
        q = query.lower()
        for n in nodes:
            nm = (n.get("name") or "").lower()
            if nm and nm in q:
                hits.append((n["name"], 1.0))
        try:
            import numpy as np
            qv = embedding_adapter.encode_one(query)
            if qv is not None:
                qn = np.linalg.norm(qv)
                for n in nodes:
                    ev = n.get("embedding")
                    if not ev:
                        continue
                    sim = float(np.dot(qv, ev) / (qn * np.linalg.norm(ev) + 1e-9))
                    hits.append((n["name"], sim))
        except Exception:  # noqa: BLE001
            pass
        if not hits:
            return []
        best = {}
        for name, s in hits:
            best[name] = max(best.get(name, -1), s)
        ranked = sorted(best.items(), key=lambda x: x[1], reverse=True)
        return [nm for nm, _ in ranked[:limit]]

    def stats(self, kid: str) -> dict:
        g = self._load(kid)
        return {"nodes": len(g.get("nodes", [])), "edges": len(g.get("edges", []))}


kg_rag = KnowledgeGraph()
