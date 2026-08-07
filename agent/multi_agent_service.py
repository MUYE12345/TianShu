"""
多智能体调度器 v2 — 动态子智能体创建 + 三层记忆

架构参考:
  AgentScope meta_planner: Master 通过 create_worker TOOL 动态创建子智能体
  Hermes MemoryManager:   Provider-based 记忆分层, context fencing, lifecycle hooks

设计:
  MasterAgent (管理者)
    ├── PlanNotebook: 当前任务分解计划
    ├── Tool: create_worker(task, context) → 动态创建 Worker
    ├── Tool: finalize_answer(result)     → 结束任务, 合成最终答案
    ├── Tool: save_insight(content)       → 将关键发现写入共享记忆
    │
    ├── Worker A ── 独立 LLM + 工具子集 + 隔离记忆 → 结构化结果
    ├── Worker B ── 独立 LLM + 工具子集 + 隔离记忆 → 结构化结果
    └── Worker C ── 独立 LLM + 工具子集 + 隔离记忆 → 结构化结果

  三层记忆:
    Master Memory   — 对话历史 + 计划状态 (ConversationMemory)
    Worker Memory   — 每个 Worker 独立隔离 (WorkerMemory, 内存级)
    Shared Knowledge — 沉淀到全局知识库 (KnowledgeMemory)
"""
import json
import re
import asyncio
from typing import AsyncGenerator, Optional
from pydantic import BaseModel, Field

from backend.config import settings
from backend.core.logger import log
from backend.core.model_config import model_manager
from agent.multi_agent_memory import agent_memory, WorkerMemory


# ── 结构化输出模型 ──


def _extract_json(text: str) -> str:
    """从 LLM 输出中稳健提取 JSON 对象：去代码围栏，截取第一个 { 到最后一个 }。"""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    return text


class WorkerResult(BaseModel):
    """子智能体执行结果（结构化传递）"""
    success: bool = Field(description="是否成功完成任务")
    message: str = Field(description="执行结果摘要")
    details: str = Field(default="", description="详细输出")
    insights: list[str] = Field(default_factory=list, description="值得共享的关键发现")


class TaskPlan(BaseModel):
    """任务分解计划"""
    goal: str = Field(description="任务核心目标")
    subtasks: list[dict] = Field(description="子任务列表: [{name, task, tools}]")
    coordination: str = Field(default="parallel",
                              description="协作策略: parallel/sequential")


# ── Worker 智能体 ──


class DynamicWorker:
    """动态创建的子智能体

    每个 Worker 拥有:
    - 独立的 DirectLLM 实例
    - 隔离的 WorkerMemory
    - 指定的工具子集
    - 结构化输出 (WorkerResult)
    """

    def __init__(self, name: str, task: str, context: str = "",
                 tools: list = None, tool_descs: str = ""):
        self.name = name
        self.memory = agent_memory.create_worker(name, task, context)
        self.tools = tools or []
        self.tool_descs = tool_descs
        self._llm = model_manager.get_main_llm()

    async def run(self) -> WorkerResult:
        """执行子任务(带真实工具调用), 返回结构化结果"""
        self.memory.start()
        log.info("[Worker %s] 开始执行: %s", self.name, self.memory.task[:60])

        try:
            system_prompt = self.memory.build_system_prompt()
            if self.tool_descs:
                system_prompt += f"\n\n## 可用工具\n{self.tool_descs}"

            system_prompt += """

## 工作方式
- 只有真正需要实时信息/文件操作/代码/计算时才调用工具, 输出:
  TOOL_CALL:工具名|{"参数":"值"}
  支持一次多个工具, 用 --- 分隔。
- 完成任务后, 请用以下格式输出最终结果:
FINAL_RESULT: {"success": true/false, "message": "摘要", "details": "详细内容", "insights": ["发现1", "发现2"]}"""

            tool_map = {getattr(t, "name", str(t)): t for t in (self.tools or [])}
            max_worker_loops = settings.MULTI_AGENT_MAX_WORKER_LOOPS
            max_tool_rounds = settings.MULTI_AGENT_MAX_TOOL_ROUNDS
            tool_rounds = 0
            final_result = WorkerResult(success=False, message="未完成")

            for loop in range(max_worker_loops):
                messages = [{"role": "system", "content": system_prompt},
                            {"role": "user", "content": "请开始执行你的任务。" if loop == 0
                             else "请继续完成任务。"}] + self.memory.conversation[-4:]

                response = await self._llm.ainvoke(messages)
                self.memory.add_turn("assistant", response)

                # 1. 最终结果
                if "FINAL_RESULT:" in response:
                    try:
                        json_str = response.split("FINAL_RESULT:", 1)[1].strip()
                        result_dict = json.loads(json_str)
                        final_result = WorkerResult.model_validate(result_dict)
                        self.memory.set_result(
                            final_result.success,
                            final_result.message,
                            final_result.model_dump(),
                        )
                        break
                    except (json.JSONDecodeError, Exception) as e:
                        log.warning("[Worker %s] 结果解析失败: %s", self.name, e)
                        final_result = WorkerResult(
                            success=False,
                            message=f"结果解析失败: {e}",
                        )
                        break

                # 2. 工具调用
                blocks = [b.strip() for b in response.split("---") if b.strip().startswith("TOOL_CALL:")]
                if blocks:
                    if tool_rounds >= max_tool_rounds:
                        self.memory.add_turn("user", "工具调用轮数已达上限, 请直接输出 FINAL_RESULT 总结已有结果。")
                        continue
                    tool_rounds += 1
                    results = []
                    for block in blocks:
                        raw = block[len("TOOL_CALL:"):]
                        if "|" not in raw:
                            results.append(f"[解析失败] {raw[:60]}")
                            continue
                        name, args_str = raw.split("|", 1)
                        name = name.strip()
                        try:
                            args = json.loads(args_str)
                        except json.JSONDecodeError:
                            args = {}
                        fn = tool_map.get(name)
                        try:
                            r = fn.invoke(args) if fn else f"工具不存在: {name}"
                        except Exception as e:  # noqa: BLE001
                            r = f"执行错误: {e}"
                        results.append(f"[{name}] {str(r)[:500]}")
                    if results:
                        self.memory.add_turn("user", "工具结果:\n" + "\n".join(results) + "\n\n请继续。")
                    continue

                # 3. 无工具也无 FINAL_RESULT → 中间输出, 继续下一轮
                self.memory.add_turn("user", "请总结当前进展, 如已完成请直接输出 FINAL_RESULT。")

            return final_result

        except Exception as e:
            log.warning("[Worker %s] 执行异常: %s", self.name, e)
            return WorkerResult(success=False, message=f"执行异常: {e}")


# ── 主智能体 ──


class MasterAgent:
    """
    主智能体 — 任务管理者

    角色:
    - 分析用户任务 → 分解为子任务
    - 动态创建 Worker → 分配任务
    - 收集 Worker 结果 → 合成最终答案
    - 沉淀关键发现 → 共享知识

    工作流:
      Analyze → Plan → Deploy → Collect → Synthesize → Respond
    """

    def __init__(self, tools: list = None, tool_descs: str = "",
                 max_workers: int = None, worker_timeout: int = None):
        self.llm = model_manager.get_main_llm()
        self.workers: dict[str, DynamicWorker] = {}
        self.tools = tools or []
        self.tool_descs = tool_descs
        # LLM 计划里 tools 是字符串名, 建 名称→对象 映射供 worker 解析
        self._tool_map = {getattr(t, "name", str(t)): t for t in self.tools}
        self.plan: Optional[TaskPlan] = None
        self.accumulated_results: list[WorkerResult] = []
        self.max_workers = max_workers or settings.MULTI_AGENT_MAX_WORKERS
        self.worker_timeout = worker_timeout or settings.MULTI_AGENT_WORKER_TIMEOUT
        self.task_queue: list[dict] = []

    async def run(self, user_input: str, context: str = "",
                  chat_history: list = None) -> AsyncGenerator[dict, None]:
        """主智能体执行循环"""
        yield {"type": "master_think", "status": "深度分析任务中..."}

        # 注入共享知识/RAG 上下文, 供任务分解与 Worker 参考(避免子智能体盲跑)
        knowledge_ctx = agent_memory.get_shared_context(user_input, top_k=5)
        plan_ctx = context or ""
        if knowledge_ctx:
            plan_ctx = f"{plan_ctx}\n\n## 相关知识\n{knowledge_ctx}".strip()

        # ═══ Phase 1: Plan 分析 & 分解任务 ═══
        plan = await self._analyze_task(user_input, plan_ctx)
        self.plan = plan
        yield {"type": "plan", "plan": json.dumps({
            "goal": plan.goal,
            "subtasks": [s["name"] for s in plan.subtasks],
            "strategy": plan.coordination,
        }, ensure_ascii=False)}

        # ═══ Phase 2: Deploy 创建 Worker 执行 ═══
        worker_tasks = []
        for subtask in plan.subtasks:
            worker = await self._create_worker(
                name=subtask["name"],
                task=subtask["task"],
                tools=subtask.get("tools", []),
                context=plan_ctx,
            )
            if worker is not None:
                worker_tasks.append(worker)
                yield {"type": "agent_start", "agent": worker.name,
                       "task": subtask["task"][:80]}
            else:
                yield {"type": "agent_queued", "agent": subtask["name"],
                       "task": subtask["task"][:80]}

        # ═══ Phase 3: Collect 执行 & 收集结果 ═══
        async def _run_worker_with_timeout(worker: DynamicWorker) -> WorkerResult:
            try:
                return await asyncio.wait_for(
                    worker.run(), timeout=self.worker_timeout
                )
            except asyncio.TimeoutError:
                log.warning("[Master] Worker %s 执行超时(%ds)",
                            worker.name, self.worker_timeout)
                return WorkerResult(
                    success=False,
                    message=f"执行超时({self.worker_timeout}s)",
                )

        results = []
        if plan.coordination == "sequential":
            # 顺序执行: 前一个的结果可作为后一个的额外上下文
            for i, worker in enumerate(worker_tasks):
                extra_context = ""
                if i > 0 and results:
                    prev = results[-1]
                    extra_context = f"前序步骤结果: {prev.message}\n{prev.details[:300]}"
                    if extra_context:
                        worker.memory.context += f"\n\n{extra_context}"
                result = await _run_worker_with_timeout(worker)
                results.append(result)
                yield {"type": "agent_result", "agent": worker.name,
                       "result": result.message[:200]}
        else:
            # 并行执行
            batch_results = await asyncio.gather(
                *[_run_worker_with_timeout(w) for w in worker_tasks]
            )
            for i, worker in enumerate(worker_tasks):
                results.append(batch_results[i])
                yield {"type": "agent_result", "agent": worker.name,
                       "result": batch_results[i].message[:200]}

        # 处理排队任务
        while self.task_queue:
            queued = self.task_queue.pop(0)
            worker = DynamicWorker(
                name=queued["name"],
                task=queued["task"],
                context=queued.get("context", ""),
                tools=queued["tools"],
                tool_descs=queued["tool_descs"],
            )
            self.workers[queued["name"]] = worker
            yield {"type": "agent_start", "agent": worker.name,
                   "task": queued["task"][:80]}
            result = await _run_worker_with_timeout(worker)
            results.append(result)
            yield {"type": "agent_result", "agent": worker.name,
                   "result": result.message[:200]}

        self.accumulated_results = results

        # ═══ Phase 4: Synthesize 合成答案 ═══
        yield {"type": "master_review", "status": "汇总子智能体结果中..."}

        synthesis = await self._synthesize(user_input)
        yield {"type": "token", "text": f"\n\n{synthesis}"}

        yield {"type": "synthesis", "result": synthesis}
        yield {"type": "done", "final_response": synthesis}

    def _share_insights(self):
        """把子智能体返回的 insights 写入共享知识(跨会话复用)。失败隔离不阻断合成。"""
        goal = self.plan.goal if self.plan else ""
        for res in self.accumulated_results:
            for insight in (res.insights or []):
                if not (insight or "").strip():
                    continue
                try:
                    agent_memory.share_knowledge(
                        insight.strip(), source=f"multi_agent:{goal[:30]}", importance=2)
                except Exception as e:  # noqa: BLE001
                    log.warning("[Master] 共享知识写入失败: %s", e)

    async def _analyze_task(self, user_input: str, context: str) -> TaskPlan:
        """分析任务, 分解为子任务清单"""
        prompt = f"""你是一个天枢的主控Agent。请分析以下用户任务并制定执行计划。

任务: {user_input}

请用JSON格式输出:
{{
  "goal": "任务核心目标（一句话）",
  "subtasks": [
    {{"name": "子任务名称（英文简短）", "task": "给子智能体的详细任务描述", "tools": ["可选工具名"]}}
  ],
  "coordination": "parallel（并行）或 sequential（顺序执行）"
}}

规则:
- 分析/调研/报告类任务请分解为 2-4 个独立子任务（如技术原理、工程实践、应用场景等不同角度）
- 简单任务可用 1 个子任务
- 各子任务应尽量独立, 减少相互依赖

只输出 JSON 本身, 不要包含 markdown 代码块、注释或任何其他文字。"""
        try:
            response = await self.llm.ainvoke(
                f"{prompt}\n\n上下文: {context[:500]}" if context else prompt
            )
            plan_dict = json.loads(_extract_json(response))
            return TaskPlan(**plan_dict)
        except (json.JSONDecodeError, Exception) as e:
            log.warning("任务分解失败, 使用默认计划: %s", e)
            return TaskPlan(
                goal=user_input,
                subtasks=[{"name": "assistant", "task": user_input}],
                coordination="parallel",
            )

    def _resolve_tools(self, tools) -> list:
        """把计划里的工具字符串名解析为真实工具对象; 空则给全部工具。"""
        objs = [self._tool_map[t] for t in (tools or []) if t in self._tool_map]
        return objs or self.tools

    async def _create_worker(self, name: str, task: str,
                              tools: list = None, context: str = "") -> Optional[DynamicWorker]:
        """创建子智能体，若超过 max_workers 限制则排队"""
        tool_objs = self._resolve_tools(tools)
        if len(self.workers) >= self.max_workers:
            self.task_queue.append({
                "name": name,
                "task": task,
                "tools": tool_objs,
                "tool_descs": self.tool_descs,
                "context": context,
            })
            log.info("[Master] 达到最大Worker数(%d), 任务排队: %s",
                      self.max_workers, name)
            return None
        worker = DynamicWorker(
            name=name,
            task=task,
            context=context,
            tools=tool_objs,
            tool_descs=self.tool_descs,
        )
        self.workers[name] = worker
        return worker

    async def _synthesize(self, user_input: str) -> str:
        """综合所有 Worker 结果, 生成最终回答"""
        summaries = agent_memory.get_all_worker_summaries()
        shared = agent_memory.get_shared_context(user_input, top_k=3)

        # 沉淀子智能体的关键发现到共享知识(跨会话复用)
        self._share_insights()

        shared_section = ""
        if shared:
            shared_section = "## 相关知识\n" + shared

        prompt = f"""你是一个天枢的主控Agent。请综合所有子智能体的执行结果, 给用户一个完整的回答。

## 用户原始需求
{user_input}

## 子智能体执行结果
{summaries or "(无子智能体, 直接回答)"}

{shared_section}

要求:
1. 用中文回答, 结构清晰
2. 综合各子智能体的结果, 不要遗漏关键信息
3. 如果某些子任务失败, 如实告知用户
4. 给出可执行的建议或总结"""
        try:
            response = await self.llm.ainvoke(prompt)
            response = str(response).strip()
        except Exception as e:  # noqa: BLE001
            return f"抱歉, 合成结果时出现错误: {e}"

        # ── 独立审查闸门: 用审查模型校验主模型合成质量, reject 则回炉一次 ──
        reviewed = await self._review_synthesis(user_input, response)
        if reviewed:
            return reviewed
        return response

    async def _review_synthesis(self, user_input: str, response: str):
        """用审查模型(get_review_llm)独立校验合成回答。

        返回:
          - 修正后的回答(reject 且回炉成功) 或
          - None(通过 / warn 或审查不可用 / 回炉失败 → 用原回答)
        """
        try:
            from backend.core.model_config import model_manager
            reviewer = model_manager.get_review_llm()
            check_prompt = (
                f"你是独立审查员。审查下面的AI回答是否满足用户需求:\n"
                f"用户需求: {user_input}\n"
                f"AI回答: {response[:2000]}\n\n"
                f"检查: 是否回答了问题、是否编造/与事实矛盾、是否遗漏关键信息。\n"
                f"只回复一个词: pass / warn / reject"
            )
            verdict = str(await reviewer.ainvoke(check_prompt)).strip().lower()
            if "reject" not in verdict:
                return None  # pass / warn 都放行
        except Exception:  # noqa: BLE001
            return None  # 审查不可用 → 放行原回答

        # reject → 回炉一次(带审查意见)
        try:
            feedback = f"独立审查认为上述回答不合格, 请重写以满足用户需求, 只输出最终回答:\n用户需求: {user_input}"
            rewrite = await self.llm.ainvoke(feedback)
            return str(rewrite).strip()
        except Exception:  # noqa: BLE001
            return None


# ── 调度器 ──


class MultiAgentScheduler:
    """多智能体调度器 v2

    与旧版兼容的主入口, 创建 MasterAgent 并执行。
    """

    def __init__(self, tools: list = None, tool_descs: str = "",
                 max_workers: int = None, worker_timeout: int = None):
        self.master = MasterAgent(
            tools=tools, tool_descs=tool_descs,
            max_workers=max_workers, worker_timeout=worker_timeout,
        )

    async def run(self, user_input: str, context: str = "",
                  chat_history: list = None) -> AsyncGenerator[dict, None]:
        """运行多智能体协作"""
        async for event in self.master.run(user_input, context, chat_history):
            yield event


# 全局实例（兼容旧引用）
multi_agent = MultiAgentScheduler()
