"""
智能体编排服务 — 运行用户定义的团队图（真实 LLM 执行）

参考 tianzhi2 `backend/swarm/langgraph_flow.py` 的编排模型：
  主控规划(primary_plan) → 子智能体分阶段并行执行(execute_stage) → 主控汇总(final_summary)

每个节点会按它关联的「智能体」(companionId → Agent 表) 注入角色 system_prompt 与专属模型:
  - 有专属模型(model_id) → 为该节点构建独立 LLM 适配器实例
  - 无配置 → 回退主模型 + "你是智能体「name」"兜底提示词

事件流（SSE）:
  agent_turn {agent, status: start/end/规划中/汇总中} — 每个智能体的流转
  plan       {plan}          — 主控的分工计划
  token      {text}          — 各智能体结论 / 最终报告
  done       {final_response}
  error      {message}
"""
import asyncio
from backend.core.model_config import model_manager


# 单阶段超时(规划/单个Worker/汇总), 防止模型挂起卡死整个编排
ORCH_STAGE_TIMEOUT = 120


class _AgentLLM:
    """按智能体配置封装的 LLM: 独立适配器实例 + 专属模型名(兼容 ainvoke/chat_stream 用法)"""

    def __init__(self, adapter, model_name: str):
        self.adapter = adapter
        self.default_model = model_name
        self.model_name = model_name

    async def ainvoke(self, messages) -> str:
        return await self.adapter.chat(messages, self.model_name)

    def chat_stream(self, messages, model=None):
        return self.adapter.chat_stream(messages, model or self.model_name)


def _resolve_node_config(node: dict):
    """按节点关联的智能体(companionId/agent_id)解析 (llm, system_prompt)。

    查 Agent 表取 system_prompt 与 model_id → ModelProvider 构建独立适配器;
    查不到/无专属模型 → 返回 (None, None), 由调用方回退主模型与名称兜底。
    """
    aid = node.get("companionId") or node.get("agent_id")
    if not aid:
        return None, None
    from backend.database import SessionLocal
    from backend.models.agent import Agent
    from backend.models.model_provider import ModelProvider
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == int(aid)).first()
        if not agent:
            return None, None
        system_prompt = (node.get("system_prompt") or "").strip() or (agent.system_prompt or "")
        mp = None
        if agent.model_id:
            mp = db.query(ModelProvider).filter(
                ModelProvider.id == agent.model_id).first()
        if not mp or not mp.api_base or not mp.api_key or not mp.model_name:
            return None, system_prompt or None
        # get_adapter 返回的是注册的单例实例; 用 type() 取类, 新建独立实例(避免污染全局配置)
        adapter_cls = type(model_manager.get_adapter(mp.provider or "openai"))
        adapter = adapter_cls(api_base=mp.api_base, api_key=mp.api_key)
        return _AgentLLM(adapter, mp.model_name), system_prompt or None
    finally:
        db.close()


async def _call_llm(llm, system_prompt: str, user_prompt: str) -> str:
    """调用模型。每个智能体用自己的 system_prompt，体现角色分工。"""
    try:
        result = await asyncio.wait_for(
            llm.ainvoke([
                {"role": "system", "content": system_prompt or "你是一个智能助手。"},
                {"role": "user", "content": user_prompt},
            ]),
            timeout=ORCH_STAGE_TIMEOUT,
        )
        return str(result).strip()
    except asyncio.TimeoutError:
        return f"（该智能体执行超时({ORCH_STAGE_TIMEOUT}s)，已跳过）"
    except Exception as e:  # noqa: BLE001
        return f"（该智能体执行失败: {type(e).__name__}: {e}）"


async def _call_llm_stream(llm, system_prompt: str, user_prompt: str,
                           event_queue: asyncio.Queue) -> str:
    """流式调用：边生成边发 token 事件，返回完整文本（观感更实时）。"""
    parts = []
    try:
        async def _run():
            async for chunk in llm.chat_stream([
                {"role": "system", "content": system_prompt or "你是一个智能助手。"},
                {"role": "user", "content": user_prompt},
            ], llm.default_model):
                if chunk:
                    parts.append(chunk)
                    await event_queue.put({"type": "token", "text": chunk})
        await asyncio.wait_for(_run(), timeout=ORCH_STAGE_TIMEOUT)
    except asyncio.TimeoutError:
        if not parts:
            return f"（该智能体执行超时({ORCH_STAGE_TIMEOUT}s)，已跳过）"
    except Exception as e:  # noqa: BLE001
        if not parts:
            return f"（该智能体执行失败: {type(e).__name__}: {e}）"
    return "".join(parts).strip()


def _team_desc(nodes: list) -> str:
    lines = []
    for n in nodes:
        role_label = {"primary": "主控", "sub": "成员", "member": "成员"}.get(n.get("role"), "成员")
        duty = (n.get("task") or "").strip()
        lines.append(f"- {n.get('name', '未知')}（{role_label}）职责：{duty or '未指定'}")
    return "\n".join(lines)


def _format_results(results: dict) -> str:
    return "\n\n".join(f"### {name}\n{text}" for name, text in results.items())


async def run_orchestration(task: str, mode: str, nodes: list,
                            event_queue: asyncio.Queue):
    """运行团队编排。nodes 为 [{'id','name','role','task','companionId'}]。"""
    main_llm = model_manager.get_main_llm()
    nodes = [n for n in nodes if n.get("name")]

    if not nodes:
        await event_queue.put({"type": "error", "message": "没有可执行的智能体"})
        return

    # 每个节点解析出 (专属LLM, 角色提示词); 无配置则回退主模型 + 名称兜底
    def _resolve(n):
        llm, sp = _resolve_node_config(n)
        n["_llm"] = llm or main_llm
        n["_prompt"] = (sp or "").strip() or f"你是智能体「{n.get('name')}」。"

    for n in nodes:
        _resolve(n)

    if mode == "subagent":
        primary = next((n for n in nodes if n.get("role") == "primary"), nodes[0])
        workers = [n for n in nodes if n.get("id") != primary.get("id")]
    else:
        # 平等协作：第一个智能体承担汇总角色，其余并行讨论
        primary = nodes[0]
        workers = nodes[1:]

    # ── 1. 主控规划 ──
    await event_queue.put({"type": "agent_turn", "agent": primary.get("name", "主控"), "status": "规划分工中..."})
    plan = await _call_llm(
        primary["_llm"], primary["_prompt"],
        f"你是团队主控智能体。请为以下任务制定执行计划，并把子任务分派给各成员（说明每个成员负责什么）。\n\n"
        f"## 任务\n{task}\n\n## 团队成员\n{_team_desc(nodes)}\n\n"
        f"请输出分工安排（2-5 句即可）。",
    )
    await event_queue.put({"type": "plan", "plan": plan[:500]})

    # ── 2. 子智能体并行执行 ──
    results: dict = {}

    async def run_worker(node):
        name = node.get("name", "成员")
        await event_queue.put({"type": "agent_turn", "agent": name, "status": "start"})
        duty = (node.get("task") or "").strip()
        user_prompt = (
            f"## 全局任务\n{task}\n\n## 主控分工\n{plan}\n\n"
            + (f"## 你的职责\n{duty}\n\n" if duty else "")
            + f"请按你的角色完成这部分工作，直接输出你的结论（不要提及自己是AI）。"
        )

        async def _run():
            # 结论流式输出
            await event_queue.put({"type": "token", "text": f"\n\n**【{name} 的结论】**\n"})
            result = await _call_llm_stream(node["_llm"], node["_prompt"], user_prompt, event_queue)
            await event_queue.put({"type": "token", "text": "\n"})
            return result

        try:
            result = await asyncio.wait_for(_run(), timeout=ORCH_STAGE_TIMEOUT)
        except asyncio.TimeoutError:
            result = f"（该智能体执行超时({ORCH_STAGE_TIMEOUT}s)，已跳过）"
        await event_queue.put({"type": "agent_turn", "agent": name, "status": "end"})
        return name, result

    if workers:
        done = await asyncio.gather(*[run_worker(w) for w in workers])
        for name, result in done:
            results[name] = result

    # ── 3. 主控汇总（流式） ──
    await event_queue.put({"type": "agent_turn", "agent": primary.get("name", "主控"), "status": "汇总结果中..."})
    if results:
        summary_prompt = (
            f"请综合所有成员的执行结果，给用户一份完整、结构化的最终报告。\n\n"
            f"## 原始任务\n{task}\n\n## 各成员结果\n{_format_results(results)}\n\n"
            f"## 要求\n1. 用中文，结构清晰，先给总览再分点展开。\n2. 不要遗漏关键信息，客观说明每个成员的主要贡献。"
        )
    else:
        summary_prompt = f"请直接完成以下任务：\n{task}"
    await event_queue.put({"type": "token", "text": "\n\n## 最终汇总\n"})
    summary = await _call_llm_stream(primary["_llm"], primary["_prompt"], summary_prompt, event_queue)
    await event_queue.put({"type": "done", "final_response": summary})
