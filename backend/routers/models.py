"""
模型提供商管理路由 — CRUD + 启停 + 测试 + 设为默认
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import update

from backend.database import get_db
from backend.core.logger import log
from backend.core.security import get_current_user
from backend.models.model_provider import ModelProvider
from pydantic import BaseModel, Field

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────

class ModelProviderCreate(BaseModel):
    name: str = ""
    provider: str = "openai"
    api_base: str
    api_key: str = ""
    model_name: str
    model_type: str = "llm"
    thinking_mode: bool = False
    thinking_budget: int = 4000
    vision_support: bool = False
    embedding_dimensions: int | None = None
    temperature: float = 0.7
    max_tokens: int = 8192


class ModelProviderUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    model_type: str | None = None
    thinking_mode: bool | None = None
    thinking_budget: int | None = None
    vision_support: bool | None = None
    embedding_dimensions: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    is_active: bool | None = None


class ModelProviderResponse(BaseModel):
    id: int
    name: str
    provider: str
    api_base: str
    api_key: str = ""
    model_name: str
    model_type: str
    thinking_mode: bool
    thinking_budget: int
    vision_support: bool
    embedding_dimensions: int | None
    temperature: str
    max_tokens: int
    is_active: bool
    is_default: bool
    created_at: str | None = None

    model_config = {"from_attributes": True}


class ModelDefaultsUpdate(BaseModel):
    default_chat_id: int | None = None
    default_review_id: int | None = None
    default_embedding_id: int | None = None
    default_multimodal_id: int | None = None


def _to_response(p: ModelProvider) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "provider": p.provider,
        "api_base": p.api_base,
        "api_key": _mask_key(p.api_key),
        "model_name": p.model_name,
        "model_type": p.model_type,
        "thinking_mode": p.thinking_mode,
        "thinking_budget": p.thinking_budget,
        "vision_support": p.vision_support,
        "embedding_dimensions": p.embedding_dimensions,
        "temperature": str(p.temperature),
        "max_tokens": p.max_tokens,
        "is_active": p.is_active,
        "is_default": p.is_default,
        "created_at": str(p.created_at) if p.created_at else None,
    }


def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return key
    return key[:4] + "****" + key[-4:]


# ── Routes ───────────────────────────────────────────────

@router.get("")
def list_models(db: Session = Depends(get_db)):
    """获取所有模型提供商"""
    models = db.query(ModelProvider).order_by(ModelProvider.is_default.desc(), ModelProvider.created_at).all()
    # seed from .env if empty
    if not models:
        _seed_from_env(db)
        models = db.query(ModelProvider).order_by(ModelProvider.is_default.desc(), ModelProvider.created_at).all()
    return [_to_response(m) for m in models]


@router.get("/defaults")
def get_model_defaults(db: Session = Depends(get_db)):
    """获取各功能默认模型 ID"""
    models = db.query(ModelProvider).filter(ModelProvider.is_active).all()
    if not models:
        _seed_from_env(db)
        models = db.query(ModelProvider).filter(ModelProvider.is_active).all()

    chat = next((m for m in models if m.model_type == "llm" and m.is_default and m.is_active), None)
    if not chat:
        chat = next((m for m in models if m.model_type == "llm" and m.is_active), None)

    review = next((m for m in models if m.model_type == "llm" and m.id != (chat.id if chat else 0) and m.is_active), None)
    embedding = next((m for m in models if m.model_type == "embedding" and m.is_active), None)
    multimodal = next((m for m in models if m.model_type == "llm" and m.vision_support and m.is_active), None)

    return {
        "default_chat_id": chat.id if chat else None,
        # 无独立审查/多模态模型时返回 0，前端显示"同对话模型"
        "default_review_id": review.id if review else 0,
        "default_embedding_id": embedding.id if embedding else 0,
        "default_multimodal_id": multimodal.id if multimodal else 0,
    }


@router.post("")
def create_model(req: ModelProviderCreate, current_user = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """创建模型提供商"""
    model = ModelProvider(
        name=req.name.strip() or req.model_name.strip(),
        provider=req.provider,
        api_base=req.api_base.strip(),
        api_key=req.api_key.strip(),
        model_name=req.model_name.strip(),
        model_type=req.model_type,
        thinking_mode=req.thinking_mode if req.model_type == "llm" else False,
        thinking_budget=req.thinking_budget,
        vision_support=req.vision_support if req.model_type == "llm" else False,
        embedding_dimensions=req.embedding_dimensions if req.model_type == "embedding" else None,
        temperature=str(req.temperature),
        max_tokens=req.max_tokens,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    log.info(f"模型已创建: {model.name} ({model.model_name})")
    return _to_response(model)


@router.put("/{model_id}")
def update_model(model_id: int, req: ModelProviderUpdate,
                 current_user = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """更新模型提供商"""
    model = db.query(ModelProvider).filter(ModelProvider.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    payload = req.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(model, field, value)

    # auto-sync name with model_name if name was auto-derived
    if "model_name" in payload and model.name == model.model_name:
        pass  # keep name

    db.commit()
    db.refresh(model)
    log.info(f"模型已更新: id={model_id}")
    return _to_response(model)


@router.delete("/{model_id}")
def delete_model(model_id: int, current_user = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """删除模型提供商"""
    model = db.query(ModelProvider).filter(ModelProvider.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    db.delete(model)
    db.commit()
    log.info(f"模型已删除: id={model_id}")
    return {"status": "deleted"}


@router.post("/{model_id}/toggle")
def toggle_model(model_id: int, current_user = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """切换模型启用/停用"""
    model = db.query(ModelProvider).filter(ModelProvider.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    model.is_active = not model.is_active
    db.commit()
    db.refresh(model)
    return _to_response(model)


@router.post("/{model_id}/set-default")
def set_default_model(model_id: int, current_user = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """设为默认对话模型（LLM类型互斥）"""
    model = db.query(ModelProvider).filter(ModelProvider.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    if model.model_type != "llm":
        raise HTTPException(status_code=400, detail="只能将 LLM 类型设为默认")
    if not model.is_active:
        raise HTTPException(status_code=400, detail="请先启用该模型")

    # 取消同类型的其他默认
    db.execute(
        update(ModelProvider)
        .where(ModelProvider.model_type == "llm", ModelProvider.id != model_id)
        .values(is_default=False)
    )
    model.is_default = True
    db.commit()
    db.refresh(model)
    log.info(f"默认模型已切换: {model.name}")
    return _to_response(model)


@router.post("/{model_id}/test")
def test_model(model_id: int, current_user = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """测试模型连接"""
    model = db.query(ModelProvider).filter(ModelProvider.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    import httpx
    import os

    try:
        # 清除代理变量
        proxy_vars = {}
        for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
            if key in os.environ:
                proxy_vars[key] = os.environ.pop(key)

        try:
            if model.model_type == "embedding":
                return {"status": "ok", "message": "Embedding 测试暂时跳过"}

            headers = {"Authorization": f"Bearer {model.api_key}", "Content-Type": "application/json"}
            with httpx.Client(timeout=15) as client:
                resp = client.post(
                    f"{model.api_base}/chat/completions",
                    headers=headers,
                    json={
                        "model": model.model_name,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 5,
                    },
                )
            if resp.status_code < 400:
                return {"status": "ok", "message": "连接成功"}
            return {"status": "error", "message": f"API 返回 {resp.status_code}: {resp.text[:200]}"}
        finally:
            os.environ.update(proxy_vars)
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Seed ─────────────────────────────────────────────────

def _seed_from_env(db: Session):
    """从 .env 配置自动创建初始模型记录（仅首次，删除后不再自动重建）"""
    from backend.config import settings, DATA_DIR

    marker = DATA_DIR / ".models_seeded"
    if marker.exists():
        return  # 已播种过：用户可能主动删空了模型，禁止重新播种

    models_to_create = []

    if settings.MAIN_MODEL_API_KEY and settings.MAIN_MODEL_NAME:
        models_to_create.append(ModelProvider(
            name=settings.MAIN_MODEL_NAME,
            provider=settings.MAIN_MODEL_PROVIDER,
            api_base=settings.MAIN_MODEL_API_BASE,
            api_key=settings.MAIN_MODEL_API_KEY,
            model_name=settings.MAIN_MODEL_NAME,
            model_type="llm",
            thinking_mode=settings.MAIN_MODEL_THINKING_MODE,
            thinking_budget=settings.MAIN_MODEL_THINKING_BUDGET,
            temperature=str(settings.MAIN_MODEL_TEMPERATURE),
            max_tokens=settings.MAIN_MODEL_MAX_TOKENS,
            is_default=True,
        ))

    if settings.REVIEW_MODEL_API_KEY and settings.REVIEW_MODEL_NAME:
        # 避免重复：审查模型可能配置了和主体相同的模型
        already = any(
            m.model_name == settings.REVIEW_MODEL_NAME and m.api_base == settings.REVIEW_MODEL_API_BASE
            for m in models_to_create
        )
        if not already:
            models_to_create.append(ModelProvider(
                name=settings.REVIEW_MODEL_NAME,
                provider=settings.REVIEW_MODEL_PROVIDER,
                api_base=settings.REVIEW_MODEL_API_BASE,
                api_key=settings.REVIEW_MODEL_API_KEY,
                model_name=settings.REVIEW_MODEL_NAME,
                model_type="llm",
                thinking_mode=settings.REVIEW_MODEL_THINKING_MODE,
                temperature=str(settings.REVIEW_MODEL_TEMPERATURE),
                max_tokens=4096,
                is_default=False,
            ))

    for m in models_to_create:
        db.add(m)

    if models_to_create:
        db.commit()
        marker.write_text("1", encoding="utf-8")
        log.info(f"从 .env 种子 {len(models_to_create)} 个模型到数据库")
