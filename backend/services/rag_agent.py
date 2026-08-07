"""
Agentic RAG 检索循环 — 改写→检索(混合+图)→评分→重检(≤2轮)→综合(流式)→反思

这是知识库问答的"大脑": 传统 RAG 一次检索不到/数据不合格时无法自愈,
这里通过带反馈的改写重检 + 启发式阈值(边界带才 LLM 评分)保证可控成本。

产出: 异步生成器, yield SSE 事件 dict。
  {"type":"meta", "chat_id", "citations"}            ← 最先, 带会话ID
  {"type":"agent","stage":"rewrite","text":q,...}     ← 改写
  {"type":"agent","stage":"graph","entities":[...],...} ← 图扩展命中
  {"type":"agent","stage":"grade","verdict":...,"score":...} ← 评分
  {"type":"citations","citations":[...]}              ← 检索后引用(前端可提前渲染)
  {"type":"token","text":...}                          ← 流式作答
  {"type":"done","final_response":...,"citations":...,"chat_id":...}
"""
from backend.config import settings
from backend.services.kb_rag import kb_rag
from backend.services.kg_rag import kg_rag


def _llm():
    from backend.core.model_config import model_manager
    return model_manager.get_main_llm()


def _sse(ev: dict) -> str:
    import json
    return f"event: {ev.get('type')}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"


async def _rewrite(llm, question: str, history_prefix: str = "", feedback: str = "") -> str:
    """把问题改写为可独立检索的形式(融入历史或上轮反馈)。失败回退原问题。"""
    if feedback:
        prompt = (f"上一轮检索效果不佳({feedback})。请改写查询以换一种方式检索。要求:\n"
                  f"- 原样保留原问题的核心实体/专名\n"
                  f"- 换措辞、补同义词, 或拆成更具体的子问题\n"
                  f"- 输出一句完整的检索式问题\n原问题: {question}")
    elif history_prefix.strip():
        prompt = (f"{history_prefix[:600]}\n\n根据以上对话历史, 把用户最新提问改写为"
                  f"可独立检索的完整问题(补齐指代/专名)。若已完整则原样输出。只输出问题。\n最新提问: {question}")
    else:
        return question
    try:
        out = await llm.chat([{"role": "user", "content": prompt}],
                             settings.MAIN_MODEL_NAME, temperature=0.2, max_tokens=128)
        q = str(out).strip().split("\n")[0][:200]
        return q if q else question
    except Exception:  # noqa: BLE001
        return question


async def _grade(llm, question: str, hits: list) -> str:
    """LLM 判断检索片段能否作答。返回 ok|low|missing。"""
    ctx = "\n".join(
        f"[{i+1}] {h.get('filename','')}|{h.get('section','')}: {h.get('text','')[:120]}"
        for i, h in enumerate(hits[:3]))
    prompt = (f"判断下面的检索片段能否回答用户问题。只能回复一个词:\n"
              f"ok(能答) / low(沾边但不全) / missing(无关或缺失)\n\n问题: {question}\n片段:\n{ctx}")
    try:
        out = str(await llm.chat([{"role": "user", "content": prompt}],
                                 settings.MAIN_MODEL_NAME, temperature=0, max_tokens=16)).strip().lower()
        for w in ("missing", "low", "ok"):
            if w in out:
                return w
        return "low"
    except Exception:  # noqa: BLE001
        return "low"


def _heuristic_verdict(hits: list, best_score: float):
    """
    启发式阈值判据。返回 (verdict|None, need_llm)。

    策略: 检索相关性信语义分, 回答充分性交给综合阶段 LLM。
      - score >= HIGH → ok(直接进综合, 由综合 LLM 判断片段是否真能作答, 诚实兜底)
      - score <  LOW → missing(语义没找到相关内容 → 带反馈重检, 这是真正的自愈)
      - 之间(边界带) → 需要 LLM 评分确认
    """
    if not hits:
        return "missing", False
    if best_score >= settings.RAG_GRADE_HIGH:
        return "ok", False
    if best_score < settings.RAG_GRADE_LOW:
        return "missing", False
    return None, True


def _retrieve_and_expand(kid: str, q: str, source_ids) -> list:
    """混合检索 + 图扩展(图命中的来源给 boost)。返回按分排序的 hits。"""
    hits = kb_rag.retrieve(kid, q, top_k=settings.RAG_TOP_K,
                           source_ids=source_ids, use_cache=False)
    graph = kg_rag.expand(kid, q)
    if graph["count"]:
        gsrc = graph["sources"]
        for h in hits:
            if h.get("source_id") in gsrc:
                h["score"] = h.get("score", 0) + settings.GRAPH_BOOST
        hits.sort(key=lambda x: x["score"], reverse=True)
    return hits, graph


def _format_context(hits: list):
    """跨来源去重 + 子块精摘 + 父块上下文。返回 (context_text, citations)。"""
    seen, parts, citations = set(), [], []
    for i, h in enumerate(hits, 1):
        key = (h.get("source_id"), h.get("section", ""))
        if key in seen:
            continue
        seen.add(key)
        head = f"[{i}] 文件: {h.get('filename','')}"
        if h.get("section"):
            head += f" | 章节: {h['section']}"
        text = (h.get("text") or "")[:400]
        parent = (h.get("parent_text") or "").strip()
        block = f"{head}\n{text}"
        if parent and parent not in text:
            block += f"\n(上下文: {parent[:500]})"
        parts.append(block)
        citations.append({"title": h.get("filename", ""),
                          "section": h.get("section", ""),
                          "score": h.get("score", 0)})
    return "\n\n".join(parts), citations


async def agentic_chat(kid: str, req, chat: dict, history_prefix: str = ""):
    """Agentic 检索问答异步生成器。yield SSE 事件 dict, 末事件为 done。"""
    llm = _llm()
    question = req.messages[-1]["content"] if req.messages else ""
    source_ids = req.sourceIds or None
    chat_id = chat.get("id", "")

    # meta: 会话ID(引用后补发)
    yield {"type": "meta", "chat_id": chat_id, "citations": []}

    # 1. 改写(仅多轮历史存在时有意义; 单轮直接问)
    q = await _rewrite(llm, question, history_prefix) if history_prefix.strip() else question
    yield {"type": "agent", "stage": "rewrite", "text": q,
           "skipped": not history_prefix.strip()}

    all_hits, citations = [], []
    final = ""
    max_retries = max(0, int(settings.RAG_AGENT_MAX_RETRIES or 2))

    # 2~4. 检索→评分→(带反馈重检), 最多 max_retries+1 轮; 连续两轮无改善提前退出
    prev_verdict, prev_best = None, None
    for rnd in range(max_retries + 1):
        hits, graph = _retrieve_and_expand(kid, q, source_ids)
        all_hits = hits or all_hits
        best_score = hits[0]["score"] if hits else 0.0

        if graph["count"]:
            yield {"type": "agent", "stage": "graph",
                   "entities": graph["entities"][:8], "sources": graph["count"],
                   "text": f"图命中 {graph['count']} 个关联来源"}

        verdict, need_llm = _heuristic_verdict(hits, best_score)
        if need_llm:
            verdict = await _grade(llm, q, hits)
        yield {"type": "agent", "stage": "grade", "verdict": verdict,
               "score": round(best_score, 3), "round": rnd + 1}

        if verdict == "ok":
            break
        # 无答案的内容, 重检分数不涨且判定不变 → 提前退出, 不浪费调用
        if prev_verdict is not None and prev_verdict == verdict and best_score <= prev_best * 1.05:
            yield {"type": "agent", "stage": "grade", "verdict": verdict,
                   "score": round(best_score, 3), "round": rnd + 1, "early_exit": True}
            break
        prev_verdict, prev_best = verdict, best_score
        if rnd < max_retries:
            q = await _rewrite(llm, q, feedback=verdict)
            yield {"type": "agent", "stage": "rewrite", "text": q, "round": rnd + 2}

    # 检索结果为空 → 明确告知, 不编造
    if not all_hits:
        final = "知识库中未检索到与问题相关的内容。请换一种问法, 或先补充相关文档。"
        yield {"type": "done", "final_response": final, "citations": [], "chat_id": chat_id}
        return

    # 引用(前端可提前渲染)
    context, citations = _format_context(all_hits)
    yield {"type": "citations", "citations": citations}

    # 5. 跨源综合(流式)
    history_part = f"## 对话历史(供参考)\n{history_prefix[:600]}\n\n" if history_prefix else ""
    prompt = f"""{history_part}基于以下知识库片段回答问题。只依据给定片段, 不要编造; 片段不足以回答时明确说明"库内未找到"。

知识库片段:
{context}

问题: {question}

要求:
1. 引用处标注 [编号], 引用精确到文件名与章节。
2. 若片段来自不同文档, 比较并综合它们, 指出一致/互补/冲突之处。
3. 若某方面片段没有覆盖, 明确说明, 不编造。"""
    try:
        async for tok in llm.chat_stream([{"role": "user", "content": prompt}],
                                         settings.MAIN_MODEL_NAME):
            if tok:
                final += tok
                yield {"type": "token", "text": tok}
    except Exception as e:  # noqa: BLE001
        final = f"（AI 回复暂不可用: {e}）"
        yield {"type": "error", "message": final}

    # 6. 反思(可选): 完整性检查, 不完整再兜底一轮
    if settings.RAG_AGENT_REFLECT and all_hits:
        incomplete = await _check_completeness(llm, question, final)
        if incomplete:
            yield {"type": "agent", "stage": "reflect", "text": "回答可能不完整, 补充检索中..."}
            q2 = await _rewrite(llm, q, feedback="回答不完整, 需要更充分的依据")
            hits2, _g2 = _retrieve_and_expand(kid, q2, source_ids)
            if hits2:
                context2, _c2 = _format_context(hits2)
                prompt2 = (f"基于以下补充片段, 完善你的回答。只补充与问题直接相关的内容, 不要重复已答部分。\n\n"
                           f"补充片段:\n{context2}\n\n问题: {question}\n你的回答: {final}")
                supplement = ""
                try:
                    async for tok in llm.chat_stream([{"role": "user", "content": prompt2}],
                                                     settings.MAIN_MODEL_NAME):
                        if tok:
                            supplement += tok
                            yield {"type": "token", "text": tok}
                except Exception:  # noqa: BLE001
                    supplement = ""
                if supplement:
                    final = final + "\n\n【补充】\n" + supplement

    yield {"type": "done", "final_response": final, "citations": citations, "chat_id": chat_id}


async def _check_completeness(llm, question: str, answer: str) -> bool:
    """反思: 回答是否完整覆盖问题。仅回复 完整/不完整。"""
    if not answer.strip():
        return True
    prompt = (f"判断下面的回答是否完整回答了用户问题。若回答明确说'未找到/不清楚'或明显遗漏, 回复'不完整'; "
              f"否则回复'完整'。\n问题: {question}\n回答: {answer[:800]}")
    try:
        out = str(await llm.chat([{"role": "user", "content": prompt}],
                                 settings.MAIN_MODEL_NAME, temperature=0, max_tokens=16)).strip().lower()
        return "不完整" in out or "incomplete" in out
    except Exception:  # noqa: BLE001
        return False
