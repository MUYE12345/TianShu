"""
对话服务 — 会话管理/消息管理
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from backend.models.session import ChatSession, Message


class ChatService:
    """对话服务"""

    def create_session(self, db: Session, user_id: int) -> ChatSession:
        session = ChatSession(user_id=user_id, title="新对话")
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def list_sessions(self, db: Session, user_id: int) -> List[dict]:
        sessions = db.query(ChatSession).filter(
            ChatSession.user_id == user_id,
            ChatSession.is_active == True
        ).order_by(ChatSession.updated_at.desc()).all()

        result = []
        for s in sessions:
            last_msg = db.query(Message).filter(
                Message.session_id == s.id
            ).order_by(Message.id.desc()).first()
            result.append({
                "id": s.id,
                "title": s.title,
                "preview": last_msg.content[:50] if last_msg else "",
                "created_at": s.created_at.isoformat() if s.created_at else "",
            })
        return result

    def get_messages(self, db: Session, session_id: int, page: int = 1, size: int = 50) -> List[dict]:
        messages = db.query(Message).filter(
            Message.session_id == session_id
        ).order_by(Message.id).offset((page-1)*size).limit(size).all()

        return [{
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "tool_calls": m.tool_calls or [],
            "created_at": m.created_at.isoformat() if m.created_at else "",
        } for m in messages]

    def save_message(self, db: Session, session_id: int, role: str, content: str,
                     tool_calls: list = None) -> Message:
        msg = Message(
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls or [],
        )
        db.add(msg)
        # 更新会话
        db.query(ChatSession).filter(ChatSession.id == session_id).update(
            {"updated_at": datetime.utcnow()}
        )
        db.commit()
        db.refresh(msg)
        return msg


chat_service = ChatService()
