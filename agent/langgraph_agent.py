"""
LangGraph 智能体引擎 — 替换自研 Master/Worker 模式

架构:
  StateGraph(AgentState) → PlanNode → ExecuteNode → ReflectNode → (loop|end)

  专家模式:
    PlanNode 分析任务 → 如需子智能体则动态创建 SubAgent 图
    SubAgent 独立执行 → 返回结构化结果 → Master 合成

事件流 (与前端 ChatPage.vue 兼容):
  {"type": "thinking", "text": "..."}                              ← 思考模式
  {"type": "token", "text": "..."}
  {"type": "plan", "plan": "..."}
  {"type": "tool_start", "name": "...", "args": "..."}
  {"type": "tool_result", "name": "...", "result": "..."}
  {"type": "agent_turn", "agent": "master/worker", "status": "..."}
  {"type": "done", "final_response": "..."}
"""
import json
import asyncio
import logging
from typing import AsyncGenerator, TypedDict, Literal, Annotated, Sequence
from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.core.model_config import model_manager
from backend.core.context_compressor import ContextCompressor
from agent.tool_service import tool_service
from agent.tools.registry import get_simple_tools
from agent.multi_agent_memory import agent_memory
from agent.skills.skill_manager import skill_manager

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════
# 状态定义
# ═══════════════════════════════════════

class AgentState(TypedDict):
    """LangGraph 状态"""
    input: str                          # 用户输入
    system_prompt: str                  # 系统提示词
    messages: list                      # 对话历史
    plan: str                           # 当前计划
    current_step: int                   # 当前步骤
    max_steps: int                      # 最大步骤
    result: str                         # 最终结果
    error: str                          # 错误信息
    expert_mode: bool                   # 是否专家模式
    thinking_mode: bool                 # 思考模式
    sub_agents: list                    # 子智能体结果
    event_queue: asyncio.Queue          # 事件队列 → 前端 SSE
    model: str                          # 模型名称
    tool_rounds: int                    # 累计工具调用轮数(防止死循环)
    last_used_tool: bool                # 上一步是否使用了工具（用于提前结束）


# 工具调用轮数上限: 超过后不再执行工具, 强制输出文本推进步骤
MAX_TOOL_ROUNDS = 5


# ═══════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════

def _sanitize_messages(messages: list) -> list:
    """清洗历史消息: 只保留 role/content; 非空的 tool_calls 转成文本拼入 content,
    让模型能看到历史工具调用上下文。空 tool_calls([]) 必须丢弃
    (DeepSeek/DashScope 拒绝带空 tool_calls 的消息)。
    """
    out = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = m.get("role", "")
        content = m.get("content", "") or ""
        if not role or not content:
            continue
        item = {"role": role, "content": content}
        # 非空 tool_calls: 序列化为可读文本追加, 保留工具调用上下文
        tcs = m.get("tool_calls") or []
        if isinstance(tcs, list) and tcs:
            try:
                item["content"] = content + "\n[工具调用记录] " + json.dumps(tcs, ensure_ascii=False)[:500]
            except Exception:  # noqa: BLE001
                pass
        out.append(item)
    return out


def _strip_tool_calls(text: str) -> str:
    """去掉响应中残留的 TOOL_CALL 指令行，避免原始调用标记泄漏到最终回答。"""
    if not text:
        return text
    lines = [ln for ln in text.split("\n") if not ln.strip().startswith("TOOL_CALL:")]
    return "\n".join(lines).strip()

async def _think_chat(llm, messages: list, model: str, thinking_mode: bool,
                      event_queue: asyncio.Queue) -> str:
    """调用 LLM，当 thinking_mode 开启时提取并发送思考过程事件。"""
    if not thinking_mode:
        return await llm.chat(messages, model)

    # 构建 thinking kwargs
    config = model_manager.main_config
    thinking_kwargs = model_manager.get_thinking_kwargs(config, runtime_enabled=True)
    try:
        result = await llm.chat_with_thinking(messages, model, **thinking_kwargs)
    except Exception:
        logger.warning("chat_with_thinking 失败，回退到普通 chat")
        return await llm.chat(messages, model)

    if result.get("thinking"):
        await event_queue.put({"type": "thinking", "text": result["thinking"]})
    return result.get("content", "")


# ═══════════════════════════════════════
# 节点定义
# ═══════════════════════════════════════

async def plan_node(state: AgentState) -> dict:
    """Plan 节点：分析任务生成计划"""
    event_queue = state["event_queue"]
    llm = model_manager.get_main_llm()

    plan_prompt = f"""分析任务并制定执行计划(1-3步):
任务: {state['input']}
{'注意: 你可以创建子智能体来并行处理复杂任务。' if state['expert_mode'] else ''}

输出格式:
计划: <简要描述>
步骤: <1. xxx> <2. xxx> <3. xxx>"""
    plan_text = await _think_chat(
        llm,
        [{"role": "system", "content": state["system_prompt"]},
         {"role": "user", "content": plan_prompt}],
        state.get("model", ""),
        state.get("thinking_mode", False),
        event_queue,
    )

    # 仅思考模式开启时才向前端发送"规划"过程；关闭时规划只驱动内部图执行
    if state.get("thinking_mode", False):
        await event_queue.put({"type": "plan", "plan": plan_text[:300]})

    # 判断是否需要子智能体（专家模式）
    sub_agents = []
    if state["expert_mode"] and any(kw in plan_text.lower()
                                     for kw in ["子智能体", "并行", "同时", "分工", "分别", "worker"]):
        await event_queue.put({"type": "agent_turn", "agent": "master",
                               "status": "检测到需要多智能体协作，创建子智能体中..."})

    return {
        "plan": plan_text,
        "current_step": 0,
        "sub_agents": sub_agents,
        "messages": state["messages"] + [{"role": "assistant", "content": f"## 计划\n{plan_text}"}],
    }


async def execute_node(state: AgentState) -> dict:
    """Execute 节点：执行计划中的步骤"""
    event_queue = state["event_queue"]
    llm = model_manager.get_main_llm()
    tools = get_simple_tools()
    tool_map = {t.name: t for t in tools}

    messages = state["messages"]
    system = state["system_prompt"]
    step = state["current_step"]
    tool_rounds = state.get("tool_rounds", 0)

    # 多轮上下文: 滑窗+压缩替代固定取最近 6 条 —— 长对话保留摘要, 短对话全量
    history_ctx = messages
    if len(messages) > 8:
        try:
            history_ctx = ContextCompressor().compress_messages(
                messages, target_tokens=4000, window_size=8)
        except Exception:
            history_ctx = messages[-6:]

    # 构建当前步骤的 prompt
    step_prompt = f"""执行计划第 {step + 1} 步。

可用工具: {tool_service.get_tool_descriptions()}

如果需要调用工具，请输出:
TOOL_CALL:工具名|{{"参数":"值"}}

支持同时调用多个工具（用 --- 分隔）:
TOOL_CALL:工具1|{{"参数":"值"}}
---
TOOL_CALL:工具2|{{"参数":"值"}}

注意:
- 只有真正需要实时信息/文件操作/代码/计算时才调用工具
- 一般问答直接回答，不要调用工具
- 已经拿到工具结果后，就直接整理成最终回答，不要再次调用工具

完成后直接输出回答。"""

    response = await _think_chat(
        llm,
        [{"role": "system", "content": system},
         *history_ctx,
         {"role": "user", "content": step_prompt}],
        state.get("model", ""),
        state.get("thinking_mode", False),
        event_queue,
    )

    # 解析 TOOL_CALL
    tool_blocks = response.split("---")
    has_tool = any(b.strip().startswith("TOOL_CALL:") for b in tool_blocks)

    # 工具预算耗尽: 即使 LLM 输出了 TOOL_CALL 也不再执行, 直接当作最终文本, 强制推进步骤
    if has_tool and tool_rounds >= MAX_TOOL_ROUNDS:
        has_tool = False

    if has_tool:
        all_results = []
        for block in tool_blocks:
            block = block.strip()
            if not block.startswith("TOOL_CALL:"):
                if block:
                    await event_queue.put({"type": "token", "text": block})
                continue
            parts = block[len("TOOL_CALL:"):].split("|", 1)
            func_name = parts[0].strip()
            raw_args = parts[1] if len(parts) > 1 else "{}"
            try:
                func_args = json.loads(raw_args)
            except json.JSONDecodeError:
                func_args = {}

            await event_queue.put({"type": "tool_start", "name": func_name, "args": raw_args[:200]})
            tool_fn = tool_map.get(func_name)
            try:
                result = tool_fn.invoke(func_args) if tool_fn else f"工具不存在: {func_name}"
                await event_queue.put({"type": "tool_result", "name": func_name, "result": str(result)[:500]})
                all_results.append((func_name, result))
            except Exception as e:
                await event_queue.put({"type": "tool_result", "name": func_name, "result": f"错误: {e}"})

        if all_results:
            summary = "\n".join([f"[{n}] {str(r)[:400]}" for n, r in all_results])
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": f"工具结果:\n{summary}\n\n请继续。"})
            return {"messages": messages, "current_step": step, "tool_rounds": tool_rounds + 1,
                    "last_used_tool": True}

    # 无工具调用，输出文本（剥离残留 TOOL_CALL 指令）
    cleaned = _strip_tool_calls(response)
    await event_queue.put({"type": "token", "text": cleaned})
    messages.append({"role": "assistant", "content": cleaned})
    return {"messages": messages, "result": cleaned, "current_step": step + 1,
            "tool_rounds": tool_rounds, "last_used_tool": False}


async def reflect_node(state: AgentState) -> dict:
    """Reflect 节点：反思当前结果"""
    event_queue = state["event_queue"]
    llm = model_manager.get_main_llm()

    if not state.get("result"):
        return {"current_step": state["current_step"] + 1}

    await event_queue.put({"type": "reflect", "status": "反思中..."})

    reflect_prompt = f"""反思以下回答是否需要改进:
用户问题: {state['input']}
当前回答: {state['result'][:500]}

如果回答已完美，输出: NO_CHANGE
如果有改进空间，输出改进后的回答。"""

    reflection = await _think_chat(
        llm,
        [{"role": "user", "content": reflect_prompt}],
        state.get("model", ""),
        state.get("thinking_mode", False),
        event_queue,
    )

    reflection = _strip_tool_calls(reflection)
    if "NO_CHANGE" not in reflection and len(reflection) > 20:
        await event_queue.put({"type": "self_refine", "status": "改进中..."})
        return {"result": reflection, "current_step": state["current_step"] + 1}

    return {"current_step": state["current_step"] + 1}


# ═══════════════════════════════════════
# 路由逻辑
# ═══════════════════════════════════════

def should_continue(state: AgentState) -> Literal["execute", "reflect", "__end__"]:
    """决定下一步"""
    if state.get("error"):
        return "__end__"
    # 执行过且上一步是纯文本回答（没调工具）：直接进反思，不再重复执行
    if (state.get("last_used_tool") is False and state.get("current_step", 0) > 0):
        return "reflect"
    if state["current_step"] >= state["max_steps"]:
        return "reflect"
    return "execute"


def after_reflect(state: AgentState) -> Literal["plan", "__end__"]:
    """反思后的路由: 纯文本回答直接结束（避免简单问题反复重规划拖慢响应）；
    用了工具的复杂任务才重规划，且最多 max_steps 次。"""
    if not state.get("last_used_tool"):
        return "__end__"
    if state["current_step"] < state["max_steps"]:
        return "plan"
    return "__end__"


# ═══════════════════════════════════════
# 构建图
# ═══════════════════════════════════════

def build_agent_graph() -> StateGraph:
    """构建 LangGraph 智能体图"""
    graph = StateGraph(AgentState)

    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("reflect", reflect_node)

    graph.set_entry_point("plan")

    graph.add_conditional_edges("plan", should_continue, {
        "execute": "execute",
        "reflect": "reflect",
        "__end__": "__end__",
    })
    graph.add_conditional_edges("execute", should_continue, {
        "execute": "execute",
        "reflect": "reflect",
        "__end__": "__end__",
    })
    graph.add_conditional_edges("reflect", after_reflect, {
        "plan": "plan",
        "__end__": "__end__",
    })

    graph.add_edge("plan", "__end__")  # fallback

    # 不启用 checkpointer: event_queue(asyncio.Queue) 等运行时对象无法被 MemorySaver
    # 做 msgpack 序列化, 会抛 "Type is not msgpack serializable: Queue"; 单次对话无需跨请求状态
    return graph.compile()


# ═══════════════════════════════════════
# 对外接口
# ═══════════════════════════════════════

async def _run_multi_agent(user_input: str, session_id: str,
                           event_queue: asyncio.Queue, chat_history: list = None):
    """真实多智能体编排：Master 分解任务 → 动态创建 Worker 执行 → 合成答案。

    事件转发给前端：agent_turn（子智能体流转）/ plan / token / done。
    chat_history: 最近对话历史, 作为上下文注入 Master 的任务分解, 避免子智能体盲跑。
    """
    from agent.multi_agent_service import MultiAgentScheduler
    from agent.multi_agent_memory import agent_memory
    from agent.tools.registry import get_simple_tools

    agent_memory.set_session(session_id)
    tools = get_simple_tools()
    tools_desc = tool_service.get_tool_descriptions() if hasattr(tool_service, 'get_tool_descriptions') else ""
    scheduler = MultiAgentScheduler(tools=tools, tool_descs=tools_desc)

    # 把最近的对话历史拼成上下文(只取最近 6 条, 控制 token), 供任务分解参考
    context = ""
    hist = _sanitize_messages(chat_history or [])[-6:]
    if hist:
        context = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in hist if m.get("content"))[:800]

    await event_queue.put({"type": "agent_turn", "agent": "master", "status": "启动多智能体编排..."})

    async for ev in scheduler.master.run(user_input, context=context):
        et = ev["type"]
        if et == "token":
            await event_queue.put(ev)
        elif et == "master_think":
            await event_queue.put({"type": "agent_turn", "agent": "master", "status": ev.get("status", "")})
        elif et == "plan":
            await event_queue.put({"type": "plan", "plan": ev.get("plan", "")})
        elif et == "agent_start":
            await event_queue.put({"type": "agent_turn", "agent": ev.get("agent", "worker"),
                                   "status": "start", "task": ev.get("task", "")})
        elif et == "agent_queued":
            await event_queue.put({"type": "agent_turn", "agent": ev.get("agent", "worker"),
                                   "status": "queued"})
        elif et == "agent_result":
            await event_queue.put({"type": "agent_turn", "agent": ev.get("agent", "worker"),
                                   "status": "end", "result": ev.get("result", "")})
        elif et == "master_review":
            await event_queue.put({"type": "agent_turn", "agent": "master", "status": ev.get("status", "")})
        elif et == "synthesis":
            await event_queue.put({"type": "token", "text": ev.get("result", "")})
            await event_queue.put({"type": "done", "final_response": ev.get("result", "")})
        elif et == "done":
            await event_queue.put({"type": "done", "final_response": ev.get("final_response", "")})


async def run_agent(
    user_input: str,
    session_id: str,
    chat_history: list = None,
    expert_mode: bool = False,
    thinking_mode: bool = False,
    rag_context: str = "",
    agent_system_prompt: str = "",
) -> AsyncGenerator[dict, None]:
    """运行 LangGraph 智能体，产出 SSE 事件流

    agent_system_prompt: 可选。所选智能体的角色提示词(来自「智能体管理」),
    传入后作为该轮回答的角色定义, 叠加在天枢工作流程之上。
    """
    event_queue = asyncio.Queue()

    # 构建初始状态
    tools_desc = tool_service.get_tool_descriptions() if hasattr(tool_service, 'get_tool_descriptions') else ""
    role_line = agent_system_prompt.strip() if agent_system_prompt and agent_system_prompt.strip() else "你是遵循四层架构的天枢Agent。"
    system_prompt = f"""{role_line}

可用工具:
{tools_desc}

工作流程:
1. 规划(Plan): 分析任务, 生成执行计划
2. 执行(Execute): 按计划调用工具
3. 反思(Reflect): 检查回答质量

重要原则:
- 只有当任务确实需要实时信息、访问/操作文件、执行代码或精确计算时才调用工具
- 对于一般知识问答，直接用你的知识回答，不要调用工具
- 不要为了搜索而搜索；一次工具调用足够就不要重复调用
- 完成后直接回复中文答案。"""

    if rag_context:
        system_prompt += f"""

## 参考资料(知识库检索)
{rag_context}"""

    # SKILL: 渐进式披露(元数据 + 匹配技能的详细指令)
    try:
        skills_prompt = skill_manager.get_skills_prompt(user_input)
        if skills_prompt:
            system_prompt += f"\n\n{skills_prompt}"
    except Exception:
        pass

    from backend.config import settings as s
    initial_state = AgentState(
        input=user_input,
        system_prompt=system_prompt,
        messages=_sanitize_messages(chat_history or []),
        plan="",
        current_step=0,
        max_steps=3,
        result="",
        error="",
        expert_mode=expert_mode,
        thinking_mode=thinking_mode,
        sub_agents=[],
        event_queue=event_queue,
        model=s.MAIN_MODEL_NAME,
        tool_rounds=0,
        last_used_tool=False,
    )

    # 启动 LangGraph 执行
    graph = build_agent_graph()

    async def run_graph():
        try:
            if expert_mode:
                # 专家模式：真实多智能体编排（Master 分解 → Worker 执行 → 合成）
                await _run_multi_agent(user_input, session_id, event_queue,
                                       chat_history=initial_state["messages"])
            else:
                config = {"configurable": {"thread_id": session_id}}
                final_state = await graph.ainvoke(initial_state, config)
                await event_queue.put({"type": "done", "final_response": final_state.get("result", "")})
        except Exception as e:
            logger.warning("LangGraph 执行错误: %s", e)
            await event_queue.put({"type": "error", "message": f"执行错误: {e}"})
        finally:
            await event_queue.put(None)  # 结束信号

    # 并发执行图 + 产出事件
    task = asyncio.create_task(run_graph())

    while True:
        event = await event_queue.get()
        if event is None:
            break
        yield event

    await task
