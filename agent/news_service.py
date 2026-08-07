"""新闻服务: 聚合/摘要/去重/热门话题"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from backend.models.news import DailyNews, CurrentNews
from backend.core.model_config import model_manager
from backend.core.logger import log
from agent.crawlers.news_aggregator import NewsAggregator


class NewsService:
    def __init__(self):
        self.aggregator = NewsAggregator()

    def get_daily_news(self, db: Session, source: str = "", page: int = 1, size: int = 20) -> List[DailyNews]:
        query = db.query(DailyNews)
        if source:
            query = query.filter(DailyNews.source == source)
        return query.order_by(DailyNews.published_at.desc()).offset((page - 1) * size).limit(size).all()

    def count_daily_news(self, db: Session, source: str = "") -> int:
        query = db.query(DailyNews)
        if source:
            query = query.filter(DailyNews.source == source)
        return query.count()

    def get_daily_detail(self, db: Session, news_id: int) -> Optional[DailyNews]:
        return db.query(DailyNews).filter(DailyNews.id == news_id).first()

    def get_daily_grouped(self, db: Session) -> dict:
        """按媒体源分组的每日新闻（每个源取最新1条）"""
        today = datetime.now().date()
        news = db.query(DailyNews).filter(
            DailyNews.published_at >= today
        ).order_by(DailyNews.source, DailyNews.published_at.desc()).all()

        groups = {}
        for item in news:
            src = item.source
            if src not in groups:
                groups[src] = {
                    "source": src,
                    "source_name": item.source_name,
                    "count": 0,
                    "articles": [],
                    "latest": None,
                }
            groups[src]["articles"].append({
                "id": item.id,
                "title": item.title,
                "url": item.url,
                "summary": item.ai_summary or item.summary,
                "published_at": str(item.published_at) if item.published_at else "",
            })
            groups[src]["count"] += 1
            if not groups[src]["latest"]:
                groups[src]["latest"] = groups[src]["articles"][0]

        # 检测跨媒体热门话题：相同关键词出现在2+媒体中
        hot_topics = self._detect_hot_topics(list(groups.values()))
        return {"groups": list(groups.values()), "hot_topics": hot_topics}

    def _detect_hot_topics(self, groups: list) -> list:
        """检测跨媒体热门话题"""
        import re
        # 收集所有文章标题
        all_titles = []
        for g in groups:
            for a in g.get("articles", []):
                all_titles.append(a["title"])
        # 简单关键词匹配：标题中相同词出现在2+媒体
        words = {}
        for title in all_titles:
            for word in re.findall(r'[\w一-鿿]{2,}', title):
                if word not in words:
                    words[word] = set()
                words[word].add(title)
        # 出现频率高的词作为热门话题
        hot = [w for w, titles in words.items() if len(titles) >= 2 and len(w) >= 2]
        return hot[:5]

    def get_current_news(self, db: Session, section: str = "", page: int = 1, size: int = 20) -> List[CurrentNews]:
        query = db.query(CurrentNews)
        if section:
            query = query.filter(CurrentNews.section == section)
        return query.order_by(CurrentNews.published_at.desc()).offset((page - 1) * size).limit(size).all()

    @staticmethod
    def _dedup_new(db: Session, model, news_list: list) -> list:
        """批量查询已存在 URL, 返回未入库的新条目(避免 N+1 逐条查询)。"""
        urls = [i.url for i in news_list if i.url]
        if not urls:
            return list(news_list)
        existing = {u[0] for u in db.query(model.url).filter(model.url.in_(urls)).all()}
        return [i for i in news_list if i.url not in existing]

    def refresh_daily(self, db: Session) -> dict:
        """刷新每日新闻: 爬取→去重→保存→AI摘要"""
        news_list = self.aggregator.aggregate_daily()
        new_items = self._dedup_new(db, DailyNews, news_list)
        seen_sources = {}
        for item in new_items:
            db.add(DailyNews(
                title=item.title, url=item.url, source=item.source_type,
                source_name=item.source, summary=item.summary,
                content=item.content,
                published_at=(
                    datetime.fromisoformat(item.published_at)
                    if item.published_at else datetime.now()
                ),
            ))
            # 记录每个源最新的文章（用于每日卡片）
            seen_sources[item.source_type] = item
        count = len(new_items)
        db.commit()

        # AI摘要
        summary = ""
        if news_list:
            try:
                llm = model_manager.get_main_llm()
                summary = self.aggregator.generate_summary(news_list, llm)
                if summary:
                    first = db.query(DailyNews).order_by(DailyNews.id.desc()).first()
                    if first:
                        first.ai_summary = summary
                        db.commit()
            except Exception as e:
                log.warning("摘要生成失败: %s", e)

        # 有新新闻时, 为每个来源并行生成热点摘要(generate_for_source 内部各自 try/except)
        if count > 0:
            try:
                from agent.hot_summary import generate_for_source
                sources = list(set(item.source_type for item in new_items))
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
                    list(ex.map(generate_for_source, sources))
            except Exception:
                pass

        return {
            "message": f"刷新完成, 新增{count}条",
            "total": len(news_list),
            "summary": summary,
            "daily_digest": len(seen_sources),
        }

    def refresh_current(self, db: Session) -> dict:
        """刷新时事新闻"""
        news_list = self.aggregator.aggregate_current()
        new_items = self._dedup_new(db, CurrentNews, news_list)
        for item in new_items:
            db.add(CurrentNews(
                title=item.title, url=item.url, section=item.source_type,
                summary=item.summary, content=item.content,
                published_at=datetime.now(),
            ))
        count = len(new_items)
        db.commit()
        return {"message": f"刷新完成, 新增{count}条", "total": len(news_list)}


news_service = NewsService()
