"""
记忆管理器 — 多策略记忆系统

三层记忆:
- conversation: 对话历史(SQLite FTS5 全文检索)
- knowledge: 知识点(TF-IDF + 重要性 + 时效衰减)
- preference: 用户偏好(SQLite, 置信度衰减)

检索策略:
1. 关键词TF-IDF匹配(知识)
2. FTS5全文搜索(对话)
3. 重要性加权(显式importance字段)
4. 时效衰减(越新权重越高)
5. 统一排序(跨源混合结果)
"""
from typing import List, Optional, Dict
from backend.core.logger import log
from agent.memory.providers.conversation_memory import ConversationMemory
from agent.memory.providers.knowledge_memory import KnowledgeMemory
from agent.memory.providers.preference_memory import PreferenceMemory


class MemoryManager:
    def __init__(self):
        self.conversation = ConversationMemory()
        self.knowledge = KnowledgeMemory()
        self.preference = PreferenceMemory()
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return
        self.conversation.initialize()
        self.knowledge.initialize()
        self.preference.initialize()
        self.evict_old_memories()  # 启动时自动淘汰旧记忆
        self._initialized = True
        log.info("模块初始化完成")

    def evict_old_memories(self, max_age_days: int = 90):
        """淘汰超过指定天数的旧记忆"""
        deleted = self.conversation.evict_old(max_age_days)
        if deleted:
            log.info(f"已淘汰 {deleted} 条超过 {max_age_days} 天的对话记忆")
        return deleted

    # ── 对话记忆 ──
    def save_conversation(self, session_id: str, user_msg: str, asst_msg: str, metadata: dict = None):
        self.conversation.save(session_id, user_msg, asst_msg, metadata)

    def get_context(self, session_id: str, limit: int = 20) -> list:
        return self.conversation.get_history(session_id, limit)

    def search_conversations(self, query: str, limit: int = 10) -> list:
        return self.conversation.search(query, limit)

    # ── 知识记忆(BM25+语义混合检索) ──
    def save_knowledge(self, content: str, source: str = "", tags: list = None,
                       importance: int = 1):
        """保存知识点"""
        self.knowledge.save(content, source, tags, importance)

    def search_knowledge(self, query: str, limit: int = 5) -> list:
        """BM25+语义混合检索 + RRF融合"""
        return self.knowledge.search(query, limit)

    def rebuild_embeddings(self):
        """重建所有知识嵌入"""
        self.knowledge.rebuild_embeddings()

    # ── 统一跨源检索 ──
    def search_all(self, query: str, limit: int = 8) -> dict:
        """
        跨源统一检索: 知识 + 对话

        结果按综合得分排序, 知识权重0.6, 对话权重0.4
        知识: TF-IDF × 重要性 × 时效
        对话: FTS5排名
        """
        k_results = self.knowledge.search(query, limit=limit)
        c_results = self.conversation.search(query, limit=limit)

        # 统一评分 (知识默认分高于对话)
        unified = []
        for k in k_results:
            unified.append({
                "content": k["content"], "source": "knowledge",
                "score": k.get("score", 0.5) * 0.6,
                "metadata": k.get("metadata", {}),
            })
        for i, c in enumerate(c_results):
            score = 0.3 * (1 - i / max(len(c_results), 1))  # 排名越前分越高
            unified.append({
                "content": c.get("content", ""), "source": "conversation",
                "score": score * 0.4,
                "metadata": {"session_id": c.get("session_id", "")},
            })

        unified.sort(key=lambda x: x["score"], reverse=True)
        return {
            "results": unified[:limit],
            "knowledge_count": len(k_results),
            "conversation_count": len(c_results),
        }

    # ── RAG上下文构建 ──
    def get_rag_context(self, query: str, max_sources: int = 5) -> str:
        """RAG增强上下文: 知识+对话混合"""
        unified = self.search_all(query, max_sources)

        parts = []
        for r in unified["results"]:
            if r["source"] == "knowledge":
                src = r["metadata"].get("source", "知识库")
                parts.append(f"[📚{src}] {r['content'][:300]}")
            else:
                sid = r["metadata"].get("session_id", "?")
                parts.append(f"[💬对话{sid}] {r['content'][:200]}")

        return "\n\n".join(parts) if parts else ""

    # ── 偏好记忆 ──
    def get_preference(self, key: str):
        return self.preference.get(key)

    def set_preference(self, key: str, value, source: str = "explicit"):
        self.preference.set(key, value, source)

    def get_preference_context(self) -> str:
        """获取偏好上下文(注入Agent提示词)"""
        return self.preference.get_contextual()

    def learn_preferences(self, user_msg: str, asst_msg: str, llm=None):
        """从对话中学习偏好"""
        return self.preference.learn_from_conversation(user_msg, asst_msg, llm)

    def get_all_preferences(self) -> dict:
        return self.preference.get_all()

    # ── 记忆统计 ──
    def get_stats(self) -> dict:
        return {
            "knowledge": self.knowledge.get_stats(),
            "preference": self.preference.get_stats(),
        }

    # ── 自动摘要(长对话压缩) ──
    def summarize_conversation(self, session_id: str, llm=None) -> str:
        """压缩长对话为摘要"""
        history = self.get_context(session_id, limit=50)
        if len(history) < 20:
            return ""

        text = "\n".join([f"{h['role']}: {h['content'][:100]}" for h in history])
        if llm:
            try:
                summary = llm.invoke(f"用一句话总结这段对话的核心内容:\n{text}")
                return summary.strip()
            except Exception:
                pass
        return ""


memory_manager = MemoryManager()
