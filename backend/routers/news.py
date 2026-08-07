"""
新闻路由: 每日新闻(按源分组) / 时事新闻
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from agent.news_service import news_service
from backend.core.logger import log

router = APIRouter()


@router.get("/daily")
def get_daily_news(source: str = "", page: int = 1, size: int = 20, db: Session = Depends(get_db)):
    """获取每日新闻列表"""
    news = news_service.get_daily_news(db, source, page, size)
    total = news_service.count_daily_news(db, source)
    return {"items": [{"id": n.id, "title": n.title, "source": n.source_name or n.source,
                       "summary": n.ai_summary or n.summary, "content": n.content,
                       "url": n.url,
                       "published_at": str(n.published_at) if n.published_at else ""} for n in news],
            "total": total}


@router.get("/daily/hot-summary")
def get_daily_hot_summary(source: str = ""):
    """获取每日热点摘要（AI 生成）"""
    from agent.hot_summary import generate_daily_summary
    return generate_daily_summary(source=source or None)


@router.get("/daily/grouped")
def get_daily_grouped(db: Session = Depends(get_db)):
    """按媒体源分组的每日新闻（每个源最新文章 + 跨媒体热门话题）"""
    return news_service.get_daily_grouped(db)


@router.get("/daily/{news_id}")
def get_daily_news_detail(news_id: int, db: Session = Depends(get_db)):
    """获取每日新闻详情（含完整内容）"""
    news = news_service.get_daily_detail(db, news_id)
    if not news:
        return {"error": "新闻不存在"}
    return {
        "id": news.id,
        "title": news.title,
        "content": news.content,
        "ai_summary": news.ai_summary,
        "summary": news.summary,
        "source": news.source_name or news.source,
        "url": news.url,
        "published_at": str(news.published_at) if news.published_at else "",
        "keywords": news.keywords or [],
    }


@router.post("/daily/refresh")
def refresh_daily_news(db: Session = Depends(get_db)):
    """手动刷新每日新闻"""
    return news_service.refresh_daily(db)


@router.get("/current")
def get_current_news(section: str = "", page: int = 1, size: int = 20, db: Session = Depends(get_db)):
    """获取时事新闻"""
    news = news_service.get_current_news(db, section, page, size)
    return {"items": [{"id": n.id, "title": n.title, "section": n.section,
                       "summary": n.ai_summary or n.summary, "url": n.url,
                       "published_at": str(n.published_at) if n.published_at else ""} for n in news],
            "total": len(news)}


@router.get("/current/{news_id}")
def get_current_news_detail(news_id: int, db: Session = Depends(get_db)):
    """获取时事新闻详情"""
    from backend.models.news import CurrentNews
    news = db.query(CurrentNews).filter(CurrentNews.id == news_id).first()
    if not news:
        return {"error": "新闻不存在"}
    return {"id": news.id, "title": news.title, "content": news.content,
            "section": news.section, "url": news.url,
            "published_at": str(news.published_at) if news.published_at else ""}


@router.post("/current/refresh")
def refresh_current_news(db: Session = Depends(get_db)):
    """手动刷新时事新闻"""
    return news_service.refresh_current(db)
