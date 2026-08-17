"""
知识引擎路由 — 统一检索 + Wiki同步
"""
from fastapi import APIRouter, Depends
from backend.config import settings
from backend.core.security import get_current_user

router = APIRouter()


@router.get("/search")
def search_knowledge(q: str = "", limit: int = 8):
    """统一知识检索: Wiki+知识+对话 三级检索"""
    from agent.knowledge_engine import knowledge_engine
    return knowledge_engine.search(q, limit)


@router.get("/stats")
def knowledge_stats():
    """知识库统计"""
    from agent.knowledge_engine import knowledge_engine
    return knowledge_engine.memory_manager.get_stats()


@router.post("/sync/wiki")
def sync_wiki_to_memory(current_user = Depends(get_current_user)):
    """将Wiki页面同步到记忆索引"""
    from agent.knowledge_engine import knowledge_engine
    count = knowledge_engine.sync_all_wiki_to_memory()
    return {"message": f"已同步 {count} 个知识点", "count": count}


@router.post("/sync/wiki/{slug}")
def sync_single_wiki(slug: str, current_user = Depends(get_current_user)):
    """同步单个Wiki页面到记忆"""
    from agent.knowledge_engine import knowledge_engine
    count = knowledge_engine.sync_wiki_to_memory(slug)
    return {"message": f"已同步 {count} 个知识点", "count": count}


@router.post("/rebuild/embeddings")
def rebuild_embeddings(current_user = Depends(get_current_user)):
    """重建所有知识嵌入"""
    from agent.memory.memory_manager import memory_manager
    memory_manager.initialize()
    memory_manager.rebuild_embeddings()
    return {"message": "嵌入重建完成"}


@router.post("/ingest")
def ingest_document(current_user = Depends(get_current_user), file_path: str = "", file_type: str = "auto"):
    """文档摄入: 解析→Wiki→记忆"""
    from agent.knowledge_engine import knowledge_engine
    return knowledge_engine.ingest_document(file_path, file_type)


@router.get("/consolidate")
def consolidate_to_wiki(q: str = ""):
    """从记忆中发现知识点, 建议创建Wiki"""
    from agent.knowledge_engine import knowledge_engine
    return knowledge_engine.consolidate_to_wiki(q)
