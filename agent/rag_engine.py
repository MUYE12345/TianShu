"""
RAG引擎 — 统一知识检索

三层检索:
  Wiki页面(关键词+标签+图谱) → 知识记忆(BM25+语义) → 对话记忆(FTS5)
  加权RRF融合: Wiki 0.4 + 知识 0.4 + 对话 0.2

改进:
  - 重排序: 检索后用关键词覆盖度重新排序，提升相关度
  - 请求缓存: 相同查询60秒内直接返回缓存结果，避免重复计算
"""

from backend.core.cache import request_cache


class RagEngine:
    def retrieve(self, query: str, top_k: int = 5) -> str:
        """
        统一知识检索 (三级跨源加权RRF + 重排序 + 缓存)

        Wiki(0.4) + 知识记忆(0.4) + 对话历史(0.2)
        返回: 格式化上下文文本
        """
        try:
            # ── 缓存命中检查 ──
            cache_key = f"rag:{query}:{top_k}"
            cached = request_cache.get(cache_key)
            if cached is not None:
                return cached

            from agent.knowledge_engine import knowledge_engine
            result = knowledge_engine.search(query, top_k)
            results = result.get("results", [])

            if not results:
                request_cache.set(cache_key, "", ttl=60)
                return ""

            # ── 重排序: 关键词覆盖度 → 标签提升 ──
            results = self._rerank(results, query)

            # 按来源分组格式化
            wiki_items = [r for r in results if r["source"] == "wiki"]
            knowledge_items = [r for r in results if r["source"] == "knowledge"]
            conv_items = [r for r in results if r["source"] == "conversation"]

            parts = []

            if wiki_items:
                wiki_lines = []
                for w in wiki_items[:3]:
                    slug = w.get("slug", "")
                    wiki_lines.append(
                        f"- [{w.get('type','Wiki')}] {w.get('content','')}: "
                        f"{w.get('body','')[:150]}...  "
                        f"(匹配: {w.get('match_reason','')})"
                    )
                parts.append("📖 相关Wiki:\n" + "\n".join(wiki_lines))

            if knowledge_items:
                kn_lines = [
                    f"- [知识点] {k.get('body','')[:200]}..."
                    for k in knowledge_items[:3]
                ]
                parts.append("📚 相关知识:\n" + "\n".join(kn_lines))

            if conv_items:
                cv_lines = [
                    f"- [对话] {c.get('body','')[:120]}..."
                    for c in conv_items[:2]
                ]
                if cv_lines:
                    parts.append("💬 相关历史:\n" + "\n".join(cv_lines))

            result_text = "\n\n".join(parts) if parts else ""

            # ── 写入缓存, 60秒TTL ──
            request_cache.set(cache_key, result_text, ttl=60)
            return result_text

        except Exception:
            return ""

    # ── 重排序逻辑 ──

    @staticmethod
    def _rerank(results: list, query: str) -> list:
        """
        基于关键词覆盖度的简单重排序。

        策略:
          1. 将查询拆分为词项
          2. 统计每个结果在(content+body)中命中的词项数
          3. wiki结果额外根据标签匹配提升
          4. 最终得分 = 原始RRF分 + 覆盖度加分 + 标签提升
        """
        if not results or not query:
            return results

        query_terms = set(query.lower().split())
        if not query_terms:
            return results

        for item in results:
            content = (item.get("content", "") or "").lower()
            body = (item.get("body", "") or "").lower()
            combined_text = content + " " + body

            # 关键词覆盖度: 查询词项出现在文本中的数量
            overlap = sum(1 for t in query_terms if t in combined_text)

            # wiki标签提升
            tag_boost = 0.0
            if item.get("source") == "wiki":
                tags = [t.lower() for t in (item.get("tags", []) or [])]
                for t in query_terms:
                    if any(t in tag for tag in tags):
                        tag_boost += 1.0

            rrf = item.get("rrf_score", 0) or 0
            item["rerank_score"] = round(rrf + (overlap * 0.15) + (tag_boost * 0.25), 6)

        results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return results


rag_engine = RagEngine()


if __name__ == "__main__":
    # ── 重排序方法验证 ──
    _SAMPLE_RESULTS = [
        {
            "content": "Python 异步编程指南",
            "body": "asyncio 是 Python 用于编写并发代码的库",
            "type": "技术",
            "tags": ["python", "asyncio", "异步"],
            "source": "wiki",
            "slug": "async-guide",
            "rrf_score": 0.123456,
            "match_reason": "标题",
        },
        {
            "content": "JavaScript Promise 教程",
            "body": "Promise 是处理异步操作的标准模式",
            "type": "技术",
            "tags": ["javascript", "promise"],
            "source": "wiki",
            "slug": "promise-guide",
            "rrf_score": 0.100000,
            "match_reason": "内容",
        },
        {
            "content": "什么是异步编程",
            "body": "异步编程是一种让程序在等待时执行其他任务的编程范式",
            "type": "知识点",
            "tags": [],
            "source": "knowledge",
            "rrf_score": 0.080000,
            "match_reason": "hybrid",
        },
    ]

    _QUERY = "python 异步编程"
    _RE_RANKED = RagEngine._rerank(_SAMPLE_RESULTS, _QUERY)

    print("=" * 50)
    print(f"查询: \"{_QUERY}\"")
    print(f"结果数: {len(_RE_RANKED)}")
    print("-" * 50)
    for item in _RE_RANKED:
        print(f"  内容: {item['content']}")
        print(f"  来源: {item['source']}")
        print(f"  原始 RRF: {item.get('rrf_score', 0):.6f}")
        print(f"  重排序分: {item.get('rerank_score', 0):.6f}")
        print(f"  匹配: {item.get('match_reason', '')}")
        print()

    assert len(_RE_RANKED) == 3, "结果数量应保持不变"
    assert all("rerank_score" in item for item in _RE_RANKED), "每个结果都应包含 rerank_score"
    assert _RE_RANKED[0]["rerank_score"] >= _RE_RANKED[-1]["rerank_score"], "结果应按 rerank_score 降序排列"
    assert _RE_RANKED[0]["content"] == "Python 异步编程指南", "Python 异步编程指南 应排第一(标签+覆盖度提升)"

    print("OK 重排序验证通过")
    print("=" * 50)
