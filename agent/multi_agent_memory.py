"""
多智能体记忆管理器 — 三层记忆架构

参考 Hermes memory_manager.py (provider-based facade) + AgentScope PlanNotebook

设计：
  Master Memory      — 主智能体的对话历史 + 计划状态（通过 ConversationMemory 持久化）
  Worker Memory      — 每个子智能体独立的隔离记忆（内存级，任务完成后可选择合并）
  Shared Knowledge   — 跨智能体的共享知识（通过 KnowledgeMemory 持久化）

记忆流：
  用户 → Master Memory → 分配任务 → Worker Memory (独立)
                                    │
                          ┌─────────┼─────────┐
                     Worker A    Worker B    Worker C
                     (独立记忆)   (独立记忆)   (独立记忆)
                          └─────────┼─────────┘
                                    │ 结果汇总
                           Shared Knowledge (关键发现持久化)
                                    │
                               Master Memory (综合答案 → 用户)
"""
from typing import Optional
from backend.core.logger import log
from agent.memory.memory_manager import memory_manager as global_memory


class WorkerMemory:
    """子智能体工作记忆 — 任务级别的隔离上下文

    每个 Worker 拥有独立的记忆实例，包含：
    - task: 分配的子任务描述
    - context: 主智能体提供的上下文
    - conversation: 该 worker 的工具调用和中间结果
    - result: 最终结构化结果
    """

    def __init__(self, worker_name: str, task: str, context: str = ""):
        self.worker_name = worker_name
        self.task = task
        self.context = context
        self.conversation: list[dict] = []  # 工具调用轨迹
        self.result: Optional[dict] = None
        self._started = False

    def start(self):
        """开始记录工作记忆"""
        self._started = True
        self.conversation = []
        log.debug("[WorkerMemory] %s 开始, task=%s", self.worker_name, self.task[:60])

    def add_turn(self, role: str, content: str):
        """记录一轮交互"""
        self.conversation.append({"role": role, "content": content})

    def set_result(self, success: bool, message: str, data: dict = None):
        """设置最终结果"""
        self.result = {
            "success": success,
            "message": message,
            "data": data or {},
        }

    def build_system_prompt(self) -> str:
        """构建 Worker 的系统提示词（含任务上下文）"""
        parts = [
            "你是一个天枢的工作子智能体（Worker Agent）。",
            "",
            f"## 你的任务",
            self.task,
            "",
        ]
        if self.context:
            parts.extend([
                "## 主智能体提供的上下文",
                self.context,
                "",
            ])
        parts.extend([
            "## 工作规则",
            "- 专注于完成分配给你的子任务",
            "- 使用可用的工具完成任务",
            "- 完成任务后，用 FINAL_ANSWER 输出结果",
            "- 不要越权执行其他子任务",
            "- 如果遇到无法解决的问题，如实报告",
        ])
        return "\n".join(parts)

    def get_trajectory_summary(self) -> str:
        """获取工作轨迹摘要（供主智能体参考）"""
        if not self.conversation:
            return f"[Worker {self.worker_name}] 未执行任何操作"
        lines = [f"[Worker {self.worker_name}] 执行轨迹:"]
        for turn in self.conversation[-10:]:  # 只取最近 10 条
            role = "用户" if turn["role"] == "user" else "助手"
            content = turn["content"][:100]
            lines.append(f"  {role}: {content}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "worker_name": self.worker_name,
            "task": self.task,
            "has_result": self.result is not None,
            "result": self.result,
            "turn_count": len(self.conversation),
        }


class AgentMemoryManager:
    """多智能体记忆管理器 — 协调三层记忆

    参考 Hermes MemoryManager 的 provider-based facade 模式：
    - Master → 全局 ConversationMemory（长期）
    - Worker → WorkerMemory（短期，隔离）
    - Shared → 全局 KnowledgeMemory（知识沉淀）
    """

    def __init__(self):
        self._workers: dict[str, WorkerMemory] = {}
        self._shared_contexts: list[str] = []
        self.master_session_id: Optional[str] = None

    # ── Master Memory ──

    def set_session(self, session_id: str):
        """绑定主智能体的会话 ID"""
        self.master_session_id = session_id

    def save_master_turn(self, user_msg: str, asst_msg: str):
        """保存主智能体的一轮对话到全局记忆"""
        if self.master_session_id:
            global_memory.save_conversation(
                self.master_session_id, user_msg, asst_msg,
                metadata={"type": "multi_agent"}
            )

    def get_master_context(self, limit: int = 10) -> list:
        """获取主智能体的对话历史"""
        if self.master_session_id:
            return global_memory.get_context(self.master_session_id, limit)
        return []

    # ── Worker Memory ──

    def create_worker(self, name: str, task: str, context: str = "") -> WorkerMemory:
        """创建子智能体的隔离记忆"""
        worker = WorkerMemory(name, task, context)
        self._workers[name] = worker
        log.debug("[AgentMemory] 创建 Worker 记忆: %s", name)
        return worker

    def get_worker(self, name: str) -> Optional[WorkerMemory]:
        return self._workers.get(name)

    def remove_worker(self, name: str):
        """移除子智能体记忆（任务完成后清理）"""
        self._workers.pop(name, None)
        log.debug("[AgentMemory] 清理 Worker 记忆: %s", name)

    def get_all_worker_summaries(self) -> str:
        """获取所有 Worker 的结果摘要（供主智能体合成时参考）"""
        if not self._workers:
            return ""
        lines = ["## 子智能体执行结果"]
        for name, worker in self._workers.items():
            if worker.result:
                status = "✅ 成功" if worker.result["success"] else "❌ 失败"
                lines.append(f"\n### {name} ({status})")
                lines.append(worker.result["message"])
            else:
                lines.append(f"\n### {name} (⏳ 未完成)")
        return "\n".join(lines)

    # ── Shared Knowledge ──

    def share_knowledge(self, content: str, source: str = "multi_agent", importance: int = 2):
        """将关键发现写入共享知识（持久化）"""
        global_memory.save_knowledge(content, source=source, importance=importance)
        self._shared_contexts.append(content)
        log.debug("[AgentMemory] 共享知识已保存: %s", content[:60])

    def get_shared_context(self, query: str, top_k: int = 3) -> str:
        """查询共享知识（跨智能体的持久化记忆）"""
        results = global_memory.search_knowledge(query, limit=top_k)
        if not results:
            return ""
        parts = []
        for r in results:
            parts.append(f"- {r.get('content', '')[:200]}")
        return "\n".join(parts)

    # ── 报告 ──

    def get_stats(self) -> dict:
        return {
            "workers_created": len(self._workers),
            "shared_knowledge_items": len(self._shared_contexts),
            "master_session": self.master_session_id is not None,
        }


# 全局单例
agent_memory = AgentMemoryManager()
