"""
会话管理路由 — 会话 CRUD + 消息查询
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.core.security import get_optional_user
from backend.models.user import User
from backend.models.session import ChatSession, Message

router = APIRouter()


@router.get("")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """获取当前用户的所有会话列表"""
    uid = current_user.id if current_user else 1
    sessions = db.query(ChatSession).filter(
        ChatSession.user_id == uid,
        ChatSession.is_active == True,
    ).order_by(ChatSession.updated_at.desc()).all()

    result = []
    for s in sessions:
        last_msg = db.query(Message).filter(
            Message.session_id == s.id,
        ).order_by(Message.id.desc()).first()
        result.append({
            "id": s.id,
            "title": s.title,
            "model_name": s.model_name,
            "preview": last_msg.content[:100] if last_msg else "",
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })
    return result


@router.post("")
def create_session(
    title: str = Query("", description="会话标题（可选）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """创建新会话"""
    uid = current_user.id if current_user else 1
    session = ChatSession(user_id=uid, title=title or "新对话")
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


@router.put("/{session_id}")
def update_session_title(
    session_id: int,
    body: dict = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """更新会话标题"""
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体必须为 JSON 对象")
    uid = current_user.id if current_user else 1
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == uid,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    new_title = body.get("title")
    if not new_title or not new_title.strip():
        raise HTTPException(status_code=400, detail="标题不能为空")

    session.title = new_title.strip()
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return {
        "id": session.id,
        "title": session.title,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


@router.delete("/{session_id}")
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """删除会话（级联删除关联消息）"""
    uid = current_user.id if current_user else 1
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == uid,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    db.delete(session)
    db.commit()
    return {"success": True, "message": "会话已删除"}


@router.get("/{session_id}/messages")
def get_session_messages(
    session_id: int,
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(50, ge=1, le=200, description="每页条数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_user),
):
    """获取指定会话的消息列表（分页）"""
    uid = current_user.id if current_user else 1

    # 验证会话归属
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == uid,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    messages = db.query(Message).filter(
        Message.session_id == session_id,
    ).order_by(Message.id).offset((page - 1) * size).limit(size).all()

    return [{
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "tool_calls": m.tool_calls or [],
        "agent_info": m.agent_info or {},
        "task_info": m.task_info or {},
        "files": m.files or [],
        "token_count": m.token_count,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    } for m in messages]
