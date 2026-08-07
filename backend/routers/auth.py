"""
认证路由: 注册 / 登录 / Token刷新
"""
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.core.security import (
    hash_password, verify_password, create_access_token, decode_access_token,
    get_current_user,
)
from backend.core.logger import log
from backend.models.user import User

router = APIRouter()

# ── 注册频率限制跟踪 (生产环境建议使用 Redis + slowapi) ──
_register_attempts: dict[str, list[float]] = {}  # IP -> [timestamps]
_MAX_REGISTER_ATTEMPTS = 10
_REGISTER_WINDOW = 60  # seconds


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """用户注册

    注意: 生产环境应考虑添加 IP 级别的速率限制（如 slowapi 或 Nginx 限流）,
    当前实现仅记录异常高频注册行为以便排查。
    """
    # 记录注册尝试并检测异常高频注册
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    attempts = _register_attempts.setdefault(client_ip, [])
    attempts[:] = [t for t in attempts if now - t < _REGISTER_WINDOW]
    attempts.append(now)
    if len(attempts) > _MAX_REGISTER_ATTEMPTS:
        log.warning("异常注册行为: IP=%s 在 %ds 内注册 %d 次", client_ip, _REGISTER_WINDOW, len(attempts))
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id), "username": user.username})
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
    )


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """用户登录"""
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token({"sub": str(user.id), "username": user.username})
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(current_user: User = Depends(get_current_user)):
    """刷新Token"""
    token = create_access_token({"sub": str(current_user.id), "username": current_user.username})
    return TokenResponse(
        access_token=token,
        user_id=current_user.id,
        username=current_user.username,
    )


@router.get("/me")
def get_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取当前用户信息（含统计）"""
    from backend.models.session import ChatSession, Message
    from datetime import datetime

    today = datetime.utcnow().date()
    sessions = db.query(ChatSession).filter(ChatSession.user_id == current_user.id).count()
    msgs_today = db.query(Message).filter(
        Message.session_id.in_(
            db.query(ChatSession.id).filter(ChatSession.user_id == current_user.id)
        ),
        Message.created_at >= today,
    ).count()
    total_msgs = db.query(Message).filter(
        Message.session_id.in_(
            db.query(ChatSession.id).filter(ChatSession.user_id == current_user.id)
        ),
    ).count()

    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email or "",
        "avatar": current_user.avatar or "",
        "created_at": str(current_user.created_at)[:19] if current_user.created_at else "",
        "stats": {
            "sessions": sessions,
            "messages_today": msgs_today,
            "total_messages": total_msgs,
        },
    }

