"""
智能体管理路由 — 完整 CRUD + 数据库持久化（参考 tz2.0 AgentForge 设计）
"""
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from backend.database import get_db
from backend.models.agent import Agent

router = APIRouter()


class OrchestrateBody(BaseModel):
    task: str = ""
    mode: str = "subagent"
    nodes: list = []


@router.post("/orchestrate")
async def orchestrate(body: OrchestrateBody, db: Session = Depends(get_db)):
    """运行用户定义的团队编排（真实 LLM 执行），SSE 流式返回。

    事件: agent_turn / plan / token / done / error
    """
    if not body.task.strip():
        raise HTTPException(400, "任务不能为空")
    if not body.nodes:
        raise HTTPException(400, "请先搭建团队")

    # 解析每个节点的 system_prompt：优先取智能体记录里的，其次节点自带
    resolved = []
    for n in body.nodes:
        system_prompt = n.get("system_prompt") or ""
        cid = n.get("companionId")
        if cid:
            try:
                cid_int = int(cid)
            except (TypeError, ValueError):
                cid_int = None
            if cid_int:
                agent = db.query(Agent).filter(Agent.id == cid_int).first()
                if agent and agent.system_prompt:
                    system_prompt = agent.system_prompt
        resolved.append({
            "id": n.get("id") or "",
            "name": n.get("name") or "智能体",
            "role": n.get("role") or "sub",
            "task": n.get("task") or "",
            "system_prompt": system_prompt,
        })

    async def event_stream():
        queue = asyncio.Queue()

        async def run():
            try:
                from backend.services.orchestration_service import run_orchestration
                await run_orchestration(body.task, body.mode, resolved, queue)
            except Exception as e:  # noqa: BLE001
                await queue.put({"type": "error", "message": f"{type(e).__name__}: {e}"})
            finally:
                await queue.put(None)

        runner = asyncio.create_task(run())
        while True:
            ev = await queue.get()
            if ev is None:
                break
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        await runner

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


DEFAULT_AGENTS = [
    {"name": "前端工程师", "description": "精通 HTML/CSS/JavaScript/Vue/React，负责前端页面开发与问题排查", "category": "开发", "system_prompt": "你是一个资深前端工程师，精通 Vue 3、React、TypeScript、CSS 等前端技术。请专业地回答前端相关问题。"},
    {"name": "后端工程师", "description": "精通 Python/FastAPI/数据库设计，负责后端 API 开发与系统架构", "category": "开发", "system_prompt": "你是一个资深后端工程师，精通 Python、FastAPI、SQLAlchemy、数据库设计等后端技术。请专业地回答后端相关问题。"},
    {"name": "数据分析师", "description": "精通 Pandas/数据可视化/统计分析，擅长从数据中发现洞察", "category": "分析", "system_prompt": "你是一个专业的数据分析师，精通数据清洗、统计分析、可视化和机器学习。请专业地回答数据分析相关问题。"},
    {"name": "DevOps 工程师", "description": "精通 Docker/K8s/CI/CD，负责部署、监控和运维", "category": "开发", "system_prompt": "你是一个经验丰富的 DevOps 工程师，精通 Docker、Kubernetes、CI/CD、云服务等。请专业地回答运维相关问题。"},
    {"name": "产品设计师", "description": "精通 UI/UX 设计，擅长产品交互和视觉设计", "category": "设计", "system_prompt": "你是一个资深产品设计师，精通 UI/UX 设计、交互设计、设计系统和用户研究。请专业地回答设计相关问题。"},
    {"name": "测试工程师", "description": "精通自动化测试/质量保障，擅长编写测试用例和测试框架", "category": "开发", "system_prompt": "你是一个专业的测试工程师，精通自动化测试、性能测试、测试用例设计。请专业地回答测试相关问题。"},
    {"name": "AI 研究员", "description": "精通大模型/机器学习/NLP，关注前沿 AI 技术", "category": "分析", "system_prompt": "你是一个 AI 研究员，精通机器学习、深度学习、自然语言处理和大模型技术。请专业地回答 AI 相关问题。"},
    {"name": "项目管理", "description": "精通敏捷开发/任务管理/团队协作，负责项目进度和质量", "category": "自动化", "system_prompt": "你是一个经验丰富的项目经理，精通敏捷开发、任务跟踪和团队协作。请专业地回答项目管理相关问题。"},
]


def _get_default_model_id(db: Session) -> int:
    """获取默认 LLM 模型 ID，如果没有则尝试从 .env 创建"""
    from backend.models.model_provider import ModelProvider
    default = db.query(ModelProvider).filter(ModelProvider.is_default, ModelProvider.is_active).first()
    if default:
        return default.id
    active = db.query(ModelProvider).filter(ModelProvider.is_active).first()
    if active:
        return active.id
    # 尝试从 .env 种子
    from backend.routers.models import _seed_from_env
    _seed_from_env(db)
    default = db.query(ModelProvider).filter(ModelProvider.is_default, ModelProvider.is_active).first()
    return default.id if default else 0


def _seed_default_agents(db: Session):
    """如果数据库为空，插入默认智能体（关联模型管理中的默认模型）"""
    if db.query(Agent).count() == 0:
        model_id = _get_default_model_id(db)
        for a in DEFAULT_AGENTS:
            db.add(Agent(name=a["name"], description=a["description"], category=a["category"],
                        model_id=model_id, temperature=0.7, max_tokens=4096,
                        system_prompt=a["system_prompt"], enabled=True, config={}))
        db.commit()
        print(f"[智能体] 已插入 {len(DEFAULT_AGENTS)} 个默认智能体（模型ID: {model_id}）")


def _agent_to_dict(a: Agent, db: Session) -> dict:
    """智能体转字典，含关联模型信息（model_id 缺失时回退到默认模型）"""
    from backend.models.model_provider import ModelProvider
    model_name = a.model or ""
    provider = ""
    if a.model_id and a.model_id > 0:
        mp = db.query(ModelProvider).filter(ModelProvider.id == a.model_id).first()
        if mp:
            model_name = mp.model_name
            provider = mp.provider
    else:
        # 未绑定模型：展示当前默认 LLM，保证与"设置→模型"一致
        default = db.query(ModelProvider).filter(
            ModelProvider.model_type == "llm",
            ModelProvider.is_default,
            ModelProvider.is_active,
        ).first()
        if default:
            model_name = default.model_name
            provider = default.provider
    return {
        "id": a.id, "name": a.name, "description": a.description,
        "category": a.category, "model": model_name, "model_id": a.model_id,
        "provider": provider, "temperature": a.temperature,
        "max_tokens": a.max_tokens, "system_prompt": a.system_prompt,
        "enabled": a.enabled, "config": a.config or {},
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("")
def list_agents(db: Session = Depends(get_db)):
    """获取所有智能体"""
    _seed_default_agents(db)
    # 修复历史数据：未绑定模型的智能体自动绑定到默认 LLM，保证与"设置→模型"一致
    from backend.models.model_provider import ModelProvider
    default = db.query(ModelProvider).filter(
        ModelProvider.model_type == "llm",
        ModelProvider.is_default,
        ModelProvider.is_active,
    ).first()
    if default:
        repaired = False
        for a in db.query(Agent).filter(Agent.model_id == 0).all():
            a.model_id = default.id
            a.model = default.model_name
            repaired = True
        if repaired:
            db.commit()
    agents = db.query(Agent).order_by(Agent.created_at.desc()).all()
    return {
        "items": [_agent_to_dict(a, db) for a in agents],
        "total": len(agents),
    }


@router.get("/{agent_id}")
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    """获取单个智能体"""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "智能体不存在")
    return agent


@router.post("")
def create_agent(body: dict, db: Session = Depends(get_db)):
    """创建智能体"""
    from backend.models.model_provider import ModelProvider
    model_id = body.get("model_id", 0) or 0
    # 未指定模型时落到默认 LLM，避免产生空模型智能体
    if not model_id:
        default = db.query(ModelProvider).filter(
            ModelProvider.model_type == "llm",
            ModelProvider.is_default,
            ModelProvider.is_active,
        ).first()
        model_id = default.id if default else 0
    model_name = ""
    if model_id:
        mp = db.query(ModelProvider).filter(ModelProvider.id == model_id).first()
        if mp:
            model_name = mp.model_name
    agent = Agent(
        name=body.get("name", "新智能体"),
        description=body.get("description", ""),
        category=body.get("category", "通用"),
        model_id=model_id,
        model=model_name,
        temperature=body.get("temperature", 0.7),
        max_tokens=body.get("max_tokens", 4096),
        system_prompt=body.get("system_prompt", ""),
        enabled=body.get("enabled", True),
        config=body.get("config", {}),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return {"message": "创建成功", "agent": {"id": agent.id, "name": agent.name}}


@router.put("/{agent_id}")
def update_agent(agent_id: int, body: dict, db: Session = Depends(get_db)):
    """更新智能体"""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "智能体不存在")
    for field in ["name", "description", "category", "model_id", "temperature",
                  "max_tokens", "system_prompt", "enabled", "config"]:
        if field in body:
            setattr(agent, field, body[field])
    db.commit()
    return {"message": "更新成功"}


@router.delete("/{agent_id}")
def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    """删除智能体"""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "智能体不存在")
    db.delete(agent)
    db.commit()
    return {"message": "删除成功"}


@router.post("/{agent_id}/toggle")
def toggle_agent(agent_id: int, db: Session = Depends(get_db)):
    """切换智能体启用/禁用"""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "智能体不存在")
    agent.enabled = not agent.enabled
    db.commit()
    return {"message": "状态已切换", "enabled": agent.enabled}
