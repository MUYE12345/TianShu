"""
Agent 执行引擎 — 统一转发到 LangGraph(run_agent)

所有请求都走 LangGraph(plan → execute → reflect); 专家/多智能体模式由
run_agent 内部的多智能体编排处理。RAG 上下文在此检索并注入。
"""
from backend.core.logger import log
from agent.rag_engine import rag_engine


class AgentService:
    async def run(self, user_input: str, session_id: str,
                  chat_history: list = None, multi_agent: bool = False,
                  expert_mode: bool = False, thinking_mode: bool = False,
                  agent_system_prompt: str = ""):
        """执行对话请求, 产出 SSE 事件流。

        agent_system_prompt: 所选智能体的角色提示词(来自「智能体管理」), 空串表示默认天枢Agent。
        """
        from agent.langgraph_agent import run_agent
        # RAG 上下文: 检索 Wiki+知识+对话, 失败返回空串不影响主流程
        rag_context = ""
        try:
            rag_context = rag_engine.retrieve(user_input, top_k=5) or ""
        except Exception:  # noqa: BLE001
            rag_context = ""
        async for event in run_agent(
            user_input, session_id, chat_history,
            expert_mode=expert_mode or multi_agent,
            thinking_mode=thinking_mode,
            rag_context=rag_context,
            agent_system_prompt=agent_system_prompt,
        ):
            yield event


agent_service = AgentService()
