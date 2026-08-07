"""
每日热点新闻摘要生成器 — 数据库缓存版
每天只生成一次，后续请求从数据库读取
"""
import asyncio
from datetime import datetime, date
from backend.database import SessionLocal
from backend.models.news import DailyNews, HotSummary
from backend.core.model_config import model_manager
from backend.core.logger import log

SOURCE_NAMES = {
    "deep_tech": "深科技",
    "machine_heart": "机器之心",
    "qbitai": "量子位",
    "aiera": "新智元",
}

TODAY = date.today().isoformat()  # "2026-07-29"


def _run_sync_llm(llm, prompt: str, model_name: str):
    """在同步上下文调 LLM。若已在 async 循环中则返回 None(避免 asyncio.run 崩溃)。"""
    try:
        asyncio.get_running_loop()
        return None
    except RuntimeError:
        return asyncio.run(llm.chat([{"role": "user", "content": prompt}], model_name))


def generate_for_source(source: str):
    """爬虫采集后调用：为指定源生成热点摘要并直接写入缓存"""
    try:
        src = source if source else "all"
        db = SessionLocal()
        today_dt = datetime.now().date()
        news = db.query(DailyNews).filter(
            DailyNews.published_at >= today_dt,
            DailyNews.source == src,
        ).limit(20).all()

        if not news:
            return

        titles = [n.title for n in news[:10]]
        title_list = "\n".join(f"- {t}" for t in titles)
        sources_list = list(set(n.source_name or n.source for n in news))
        today_md = datetime.now().strftime("%m%d")
        src_title = SOURCE_NAMES.get(source, source or "全部源")

        prompt = (
            "你是一个资深科技编辑。请根据以下新闻标题，生成一篇今日科技热点摘要。\n\n"
            f"格式要求：\n第一行: {today_md}：主要标题概括\n"
            "第二行: 今日X条 · 分类1 N · 分类2 N\n"
            "然后用分段:\n"
            "- 标题 + 内容描述\n"
            "- 快评: 深度分析和行业洞察\n\n"
            f"今日新闻标题:\n{title_list}\n来源: {', '.join(sources_list)}\n\n"
            "请生成完整的热点摘要（不少于200字）："
        )

        from backend.config import settings
        llm = model_manager.get_main_llm()
        summary = _run_sync_llm(llm, prompt, settings.MAIN_MODEL_NAME)
        if summary is None:
            summary = f"（热点摘要需在同步上下文生成，今日共{len(news)}条新闻）"

        # 删除旧缓存，写入新缓存
        db.query(HotSummary).filter(
            HotSummary.source == src, HotSummary.date == TODAY
        ).delete()
        db.add(HotSummary(source=src, source_title=src_title, summary=summary, total=len(news), date=TODAY))
        db.commit()
        log.info("热点摘要已生成 [%s]: %d 条", src, len(news))
    except Exception as e:
        log.warning("热点摘要生成失败 [%s]: %s", source, e)
    finally:
        db.close()


def generate_daily_summary(source: str = None) -> dict:
    """获取今日热点摘要（优先从缓存读取）"""
    src = source if source and source != "all" else "all"
    src_title = SOURCE_NAMES.get(source, "全部源") if source and source != "all" else "全部源"

    db = SessionLocal()
    try:
        # 1. 尝试从缓存读取
        cached = db.query(HotSummary).filter(
            HotSummary.source == src,
            HotSummary.date == TODAY,
        ).first()
        if cached:
            return {
                "source": src,
                "source_title": src_title,
                "date": TODAY,
                "summary": cached.summary,
                "total": cached.total,
                "cached": True,
            }

        # 2. 无缓存 → 查询今日新闻
        today_dt = datetime.now().date()
        query = db.query(DailyNews).filter(DailyNews.published_at >= today_dt)
        if source and source != "all":
            query = query.filter(DailyNews.source == source)
        news = query.order_by(DailyNews.published_at.desc()).limit(20).all()

        if not news:
            return {"source": src, "source_title": src_title, "summary": "今日暂无新闻", "total": 0, "items": []}

        # 3. 调用 LLM 生成摘要
        titles = [n.title for n in news[:10]]
        sources_list = list(set(n.source_name or n.source for n in news))
        title_list = "\n".join(f"- {t}" for t in titles)
        today_md = datetime.now().strftime("%m%d")

        prompt = (
            "你是一个资深科技编辑。请根据以下新闻标题，生成一篇今日科技热点摘要。\n\n"
            f"格式要求：\n第一行: {today_md}：主要标题概括\n"
            "第二行: 今日X条 · 分类1 N · 分类2 N\n"
            "然后用分段:\n"
            "- 标题 + 内容描述\n"
            "- 快评: 深度分析和行业洞察\n\n"
            f"今日新闻标题:\n{title_list}\n来源: {', '.join(sources_list)}\n\n"
            "请生成完整的热点摘要（不少于200字）："
        )

        try:
            from backend.config import settings
            llm = model_manager.get_main_llm()
            model_name = settings.MAIN_MODEL_NAME
            summary = _run_sync_llm(llm, prompt, model_name)
            if summary is None:
                summary = f"（AI摘要需在同步上下文生成，共{len(news)}条新闻）"
        except Exception as e:
            log.warning("热点摘要生成失败: %s", e)
            summary = f"（AI摘要生成暂不可用，共{len(news)}条新闻）"

        # 4. 存入缓存
        try:
            db2 = SessionLocal()
            db2.add(HotSummary(
                source=src, source_title=src_title,
                summary=summary, total=len(news), date=TODAY,
            ))
            db2.commit()
            db2.close()
        except Exception as e:
            log.warning("热点摘要缓存写入失败: %s", e)

        return {
            "source": src,
            "source_title": src_title,
            "date": TODAY,
            "summary": summary,
            "total": len(news),
            "items": [{"title": n.title, "url": n.url, "source": n.source_name or n.source} for n in news[:8]],
        }

    finally:
        db.close()
