"""
编排团队路由 — 持久化用户搭建的编排拓扑(AgentTeam)

此前编排团队仅存前端 localStorage, 刷新即丢; 现提供 CRUD 落库。
挂载于 /api/teams。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from backend.database import get_db
from backend.models.agent_team import AgentTeam

router = APIRouter()


class TeamBody(BaseModel):
    name: str = "未命名团队"
    mode: str = "subagent"
    nodes: list = []
    prompt: str = ""


@router.get("")
def list_teams(db: Session = Depends(get_db)):
    """获取全部编排团队(倒序)"""
    teams = db.query(AgentTeam).order_by(AgentTeam.updated_at.desc()).all()
    return {"items": [t.to_dict() for t in teams], "total": len(teams)}


@router.post("")
def create_team(body: TeamBody, db: Session = Depends(get_db)):
    """保存一个编排团队"""
    if not body.nodes:
        raise HTTPException(400, "团队不能为空")
    team = AgentTeam(
        name=(body.name or "未命名团队").strip()[:100],
        mode=body.mode or "subagent",
        nodes=body.nodes or [],
        prompt=body.prompt or "",
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return team.to_dict()


@router.put("/{team_id}")
def update_team(team_id: int, body: TeamBody, db: Session = Depends(get_db)):
    """更新编排团队(覆盖名称/模式/节点/指令)"""
    team = db.query(AgentTeam).filter(AgentTeam.id == team_id).first()
    if not team:
        raise HTTPException(404, "团队不存在")
    team.name = (body.name or "未命名团队").strip()[:100]
    team.mode = body.mode or "subagent"
    team.nodes = body.nodes or []
    team.prompt = body.prompt or ""
    db.commit()
    db.refresh(team)
    return team.to_dict()


@router.delete("/{team_id}")
def delete_team(team_id: int, db: Session = Depends(get_db)):
    """删除编排团队"""
    team = db.query(AgentTeam).filter(AgentTeam.id == team_id).first()
    if not team:
        raise HTTPException(404, "团队不存在")
    db.delete(team)
    db.commit()
    return {"message": "已删除"}
