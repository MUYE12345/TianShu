"""
统一知识引擎 — 三层知识架构 + 跨源检索

架构:
  Layer 1 (源): 文档 → 上传/解析
  Layer 2 (页): Wiki → 结构化理解(标签/类型/链接)
  Layer 3 (点): 记忆 → 原子知识(BM25+语义+重要性+时效)

知识流动:
  文档上传 → 解析 → Wiki页面 → 提取知识点 → 记忆索引
  对话学习 → 记忆巩固 → Wiki页面 → 知识图谱

检索策略:
  1. Wiki页面: 关键词+类型过滤+图谱关联
  2. 知识记忆: BM25+语义向量+RRF融合
  3. 对话记忆: FTS5全文搜索
  4. 统一排序: 加权RRF (知识0.4 + Wiki0.4 + 对话0.2)
"""
from typing import List, Dict, Optional


class UnifiedKnowledgeEngine:
    """统一知识引擎"""

    def __init__(self):
        self._wiki = None
        self._memory = None

    @property
    def wiki_service(self):
        if self._wiki is None:
            from backend.services.wiki_service import wiki_service
            self._wiki = wiki_service
        return self._wiki

    @property
    def memory_manager(self):
        if self._memory is None:
            from agent.memory.memory_manager import memory_manager
            memory_manager.initialize()
            self._memory = memory_manager
        return self._memory

    # ── 文档→Wiki→记忆 流水线 ──

    def ingest_document(self, file_path: str, file_type: str = "auto") -> dict:
        """
        文档摄入: 上传→解析→创建Wiki页面→提取知识点

        返回: {wiki_page, knowledge_points, status}
        """
        # 1. 解析文档
        content = self._parse_document(file_path, file_type)
        if not content:
            return {"status": "error", "message": "文档解析失败"}

        # 2. 提取标题
        title = self._extract_title(file_path, content)

        # 3. 创建Wiki页面
        page = self.wiki_service.create_page(
            title=title,
            content=content,
            page_type="source",
            tags=[file_type],
        )
        if "error" in page:
            return {"status": "error", "message": page["error"]}

        # 4. 提取知识点并索引
        points = self._extract_knowledge_points(content)
        for pt in points:
            self.memory_manager.save_knowledge(
                pt, source=f"wiki:{page['slug']}", importance=2,
            )

        return {
            "status": "success",
            "wiki_page": page,
            "knowledge_points": len(points),
        }

    def _parse_document(self, path: str, ftype: str) -> str:
        """解析文档(MD/TXT/PDF)"""
        ext = ftype if ftype != "auto" else path.rsplit(".", 1)[-1].lower()
        try:
            if ext in ("md", "txt"):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            elif ext == "pdf":
                import fitz
                doc = fitz.open(path)
                text = "\n".join([page.get_text() for page in doc])
                doc.close()
                return text
        except Exception as e:
            from backend.core.logger import log
            log.warning("解析失败: %s", e)
        return ""

    def _extract_title(self, path: str, content: str) -> str:
        """提取文档标题"""
        import os
        basename = os.path.basename(path).rsplit(".", 1)[0]
        # 从内容第一行尝试取标题
        first_line = content.strip().split("\n")[0]
        if first_line.startswith("# "):
            return first_line[2:].strip()
        if 5 <= len(first_line) <= 100:
            return first_line
        return basename

    def _extract_knowledge_points(self, text: str, max_points: int = 5) -> list:
        """从文本提取知识点(简单分句)"""
        import re
        sentences = re.split(r'[。！？\n]', text[:3000])
        points = []
        for s in sentences:
            s = s.strip()
            if 10 < len(s) < 200:
                points.append(s)
                if len(points) >= max_points:
                    break
        return points

    # ── 跨源统一检索 ──

    def search(self, query: str, limit: int = 8) -> dict:
        """
        统一检索: Wiki页面 + 知识记忆 + 对话记忆

        三级检索 + 加权RRF融合:
        - Wiki: 关键词匹配, 权重0.4
        - 知识: BM25+语义混合, 权重0.4
        - 对话: FTS5, 权重0.2
        """
        # 1. Wiki页面搜索
        wiki_results = self._search_wiki(query, limit)

        # 2. 知识记忆搜索
        knowledge_results = self.memory_manager.search_knowledge(query, limit)

        # 3. 对话记忆搜索
        conversation_results = self.memory_manager.search_conversations(query, limit)

        # 4. 统一排序
        unified = self._unified_rank(wiki_results, knowledge_results, conversation_results, limit)

        return {
            "query": query,
            "results": unified,
            "sources": {
                "wiki": len(wiki_results),
                "knowledge": len(knowledge_results),
                "conversation": len(conversation_results),
            },
        }

    def _search_wiki(self, query: str, limit: int) -> list:
        """Wiki关键词搜索(含类型+标签匹配)"""
        pages = self.wiki_service.list_pages()
        q_lower = query.lower()
        results = []
        for p in pages:
            title = (p.get("title", "") or "").lower()
            content = (p.get("content", "") or "").lower()
            tags = [t.lower() for t in (p.get("tags", []) or [])]
            page_type = (p.get("type", "") or "").lower()

            # 多维度匹配
            title_match = q_lower in title
            content_match = q_lower in content[:1000]
            tag_match = any(q_lower in t for t in tags)
            type_match = q_lower in page_type

            if title_match or content_match or tag_match or type_match:
                score = 0
                if title_match: score += 3.0
                if content_match: score += 1.0
                if tag_match: score += 2.0
                if type_match: score += 1.5

                # 图谱关联加分: wikilinks中包含查询词
                wikilinks = [l.lower() for l in p.get("wikilinks", [])]
                if any(q_lower in l for l in wikilinks):
                    score += 2.0

                results.append({
                    "content": p.get("title", ""),
                    "body": (p.get("content", "") or "")[:300],
                    "type": p.get("type", "?"),
                    "tags": p.get("tags", []),
                    "source": "wiki",
                    "slug": p.get("slug", ""),
                    "score": score,
                    "match_reason": self._describe_match(title_match, content_match, tag_match, type_match),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def _describe_match(self, title, content, tag, ptype) -> str:
        reasons = []
        if title: reasons.append("标题")
        if content: reasons.append("内容")
        if tag: reasons.append("标签")
        if ptype: reasons.append("类型")
        return "+".join(reasons)

    def _unified_rank(self, wiki: list, knowledge: list, conversation: list, limit: int) -> list:
        """加权RRF统一排序"""
        k = 60
        rrf = {}

        # Wiki: 权重0.4
        for rank, item in enumerate(wiki):
            key = f"wiki:{item['content']}"
            rrf[key] = rrf.get(key, 0) + 0.4 / (k + rank + 1)

        # 知识: 权重0.4
        for rank, item in enumerate(knowledge):
            key = f"knowledge:{item['content']}"
            rrf[key] = rrf.get(key, 0) + 0.4 / (k + rank + 1)

        # 对话: 权重0.2
        for rank, item in enumerate(conversation):
            key = f"conversation:{item.get('content', '')}"
            rrf[key] = rrf.get(key, 0) + 0.2 / (k + rank + 1)

        # 构建合并结果
        merged = []
        for item in wiki:
            key = f"wiki:{item['content']}"
            item["rrf_score"] = round(rrf.get(key, 0), 6)
            item["source"] = "wiki"
            merged.append(item)

        for item in knowledge:
            key = f"knowledge:{item['content']}"
            entry = {
                "content": item.get("content", ""),
                "body": item.get("content", "")[:300],
                "type": "知识点",
                "tags": item.get("metadata", {}).get("tags", []),
                "source": "knowledge",
                "rrf_score": round(rrf.get(key, 0), 6),
                "match_reason": item.get("match_type", "hybrid"),
            }
            merged.append(entry)

        for item in conversation:
            key = f"conversation:{item.get('content', '')}"
            entry = {
                "content": item.get("content", "")[:100],
                "body": item.get("content", "")[:200],
                "type": "对话",
                "source": "conversation",
                "rrf_score": round(rrf.get(key, 0), 6),
                "match_reason": "FTS5全文",
            }
            merged.append(entry)

        merged.sort(key=lambda x: x["rrf_score"], reverse=True)
        return merged[:limit]

    # ── Wiki页面同步到记忆 ──

    def sync_wiki_to_memory(self, slug: str) -> int:
        """将单个Wiki页面同步到记忆索引"""
        page = self.wiki_service.read_page(slug)
        if not page:
            return 0
        content = page.get("content", "")
        if not content:
            return 0
        points = self._extract_knowledge_points(content)
        for pt in points:
            self.memory_manager.save_knowledge(
                pt, source=f"wiki:{slug}",
                importance=2,
            )
        return len(points)

    def sync_all_wiki_to_memory(self) -> int:
        """将所有Wiki页面同步到记忆索引"""
        pages = self.wiki_service.list_pages()
        total = 0
        for p in pages:
            total += self.sync_wiki_to_memory(p["slug"])
        return total

    # ── 记忆巩固 → Wiki ──

    def consolidate_to_wiki(self, query: str, context: str = "") -> dict:
        """从记忆中发现知识点, 建议创建Wiki页面"""
        knowledge = self.memory_manager.search_knowledge(query, 10)
        conversations = self.memory_manager.search_conversations(query, 5)

        # 找到高频共现的知识点
        related = []
        for k in knowledge:
            related.append({
                "content": k["content"][:200],
                "source": k.get("metadata", {}).get("source", ""),
                "importance": k.get("metadata", {}).get("importance", 1),
            })

        # 建议创建Wiki页面
        suggestions = []
        if len(related) >= 3:
            suggestions.append({
                "action": "create_wiki",
                "title": f"关于 {query} 的知识汇总",
                "from_sources": len(related),
                "type": "knowledge",
            })

        return {
            "related_knowledge": related,
            "suggestions": suggestions,
            "conversation_count": len(conversations),
        }


knowledge_engine = UnifiedKnowledgeEngine()
