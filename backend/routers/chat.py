"""
问答对话路由 — SSE流式输出 + JWT用户认证 + 客户端断开检测
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.core.security import get_current_user, get_optional_user
from backend.core.logger import log
from backend.models.user import User
from backend.models.session import ChatSession, Message
from backend.services.chat_service import chat_service
from agent.agent_service import agent_service

router = APIRouter()


@router.post("/sessions")
def create_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """创建新会话"""
    uid = current_user.id if current_user else 1
    session = chat_service.create_session(db, user_id=uid)
    return {"id": session.id, "title": session.title}


@router.get("/sessions")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """会话列表"""
    uid = current_user.id if current_user else 1
    return chat_service.list_sessions(db, user_id=uid)


@router.get("/sessions/{session_id}/messages")
def get_messages(
    session_id: int,
    page: int = 1,
    size: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """获取历史消息"""
    return chat_service.get_messages(db, session_id, page, size)


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: int,
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """
    发送消息, SSE流式返回

    支持客户端断开检测：当用户停止生成或关闭页面时，服务器端自动终止 Agent 循环。

    SSE事件格式:
      event: token\ndata: {"text":"正在"}
      event: tool_start\ndata: {"name":"web_search","args":{...}}
      event: tool_result\ndata: {"name":"web_search","result":"..."}
      event: done\ndata: {"final_response":"..."}
    """
    content = body.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="消息不能为空")

    async def event_stream():
        try:
            messages = chat_service.get_messages(db, session_id)

            expert_mode = body.get("expert_mode", False)
            thinking_mode = body.get("thinking_mode", False)

            # 所选智能体的角色提示词(来自「智能体管理」): agent_id → Agent.system_prompt
            agent_system_prompt = ""
            try:
                agent_id = body.get("agent_id")
                if agent_id:
                    from backend.models.agent import Agent
                    agent = db.query(Agent).filter(Agent.id == int(agent_id)).first()
                    if agent and agent.enabled and agent.system_prompt:
                        agent_system_prompt = agent.system_prompt
            except Exception:
                agent_system_prompt = ""

            async for event in agent_service.run(
                content, str(session_id), messages,
                expert_mode=expert_mode,
                thinking_mode=thinking_mode,
                agent_system_prompt=agent_system_prompt,
            ):
                # 检测客户端是否断开连接
                if await request.is_disconnected():
                    log.info("客户端断开连接，终止生成 (session=%s)", session_id)
                    break

                yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

                if event["type"] == "done":
                    chat_service.save_message(db, session_id, "user", content)
                    chat_service.save_message(db, session_id, "assistant",
                                              event.get("final_response", ""))
        except Exception as e:
            log.warning("SSE 流异常 (session=%s): %s", session_id, e)
            # 把错误透传给前端，避免"静默无回复"
            yield (f"event: error\n"
                   f"data: {json.dumps({'type': 'error', 'message': f'回答失败: {type(e).__name__}: {e}'}, ensure_ascii=False)}\n\n")

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """删除会话"""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.delete(session)
    db.commit()
    log.info("会话已删除: id=%d", session_id)
    return {"success": True, "message": "会话已删除"}


@router.post("/sessions/{session_id}/stop")
def stop_generation(session_id: int):
    """停止生成（兼容接口，前端优先使用 AbortController）"""
    return {"success": True, "message": "已发送停止信号"}
