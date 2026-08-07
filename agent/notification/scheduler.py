"""定时推送调度器 — 天气7点推送 / 新闻9点推送 / 支持容器化"""
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from backend.core.logger import log
from backend.config import settings
from agent.notification.notifier_base import NotifyContent
from agent.notification.feishu.notifier import FeishuNotifier
from agent.notification.qq_mail.notifier import QQMailNotifier


class PushScheduler:
    """定时推送调度器

    两个独立的 cron 任务:
      07:00 — 天气推送（出门前看天气+穿衣建议）
      09:00 — 新闻推送（上班后看科技资讯）

    在 .env 中可分别配置推送时间。
    需在应用启动时调用 start() 激活。
    """

    def __init__(self):
        self.notifiers = {
            "feishu": FeishuNotifier(),
            "qqmail": QQMailNotifier(),
        }
        self.scheduler = None
        self._started = False
        # Fix 3: 防止任务重叠执行的锁，每个任务类型独立一把锁
        self._locks = {
            "weather": threading.Lock(),
            "news": threading.Lock(),
            "crawl": threading.Lock(),
        }
        self._executor = ThreadPoolExecutor(max_workers=3)

    # ── 超时与重试工具 ──

    def _run_with_timeout(self, func, job_name, timeout=60):
        """Fix 1: 在子线程中执行函数, 超时则取消并返回 False"""
        future = self._executor.submit(func)
        try:
            future.result(timeout=timeout)
            return True
        except FuturesTimeout:
            log.warning("定时任务 [%s] 执行超时 (%ds), 任务已取消", job_name, timeout)
            future.cancel()
            return False
        except Exception as e:
            log.warning("定时任务 [%s] 执行异常: %s", job_name, e)
            return False

    def _schedule_retry(self, job_name, retry_func):
        """Fix 2: 5分钟后一次性重试 (通过 APScheduler date trigger)"""
        if self.scheduler is None:
            log.warning("定时任务 [%s] 无法重试: 调度器未就绪", job_name)
            return
        run_time = datetime.now() + timedelta(minutes=5)
        try:
            self.scheduler.add_job(
                retry_func,
                "date",
                run_date=run_time,
                id=f"{job_name}_retry",
                replace_existing=True,
            )
            log.info("定时任务 [%s] 将在5分钟后重试", job_name)
        except Exception as e:
            log.warning("定时任务 [%s] 调度重试失败: %s", job_name, e)

    def start(self):
        """启动多个 APScheduler cron 任务"""
        if self._started:
            return
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            self.scheduler = BackgroundScheduler()

            # ── 任务1: 天气推送（默认 07:00） ──
            wh, wm = settings.WEATHER_PUSH_TIME.split(":")
            self.scheduler.add_job(
                self.push_weather, "cron",
                hour=int(wh), minute=int(wm),
                id="weather_push",
                replace_existing=True,
            )

            # ── 任务2: 新闻推送（默认 09:00） ──
            nh, nm = settings.NEWS_PUSH_TIME.split(":")
            self.scheduler.add_job(
                self.push_news, "cron",
                hour=int(nh), minute=int(nm),
                id="news_push",
                replace_existing=True,
            )

            # ── 任务3: 新闻爬取（9, 12, 15, 17, 20, 24时） ──
            self.scheduler.add_job(
                self.crawl_news, "cron",
                hour="9,12,15,17,20,0", minute=5,
                id="news_crawl",
                replace_existing=True,
            )

            self.scheduler.start()
            self._started = True
            log.info("定时任务已启动: 天气 %s / 新闻 %s / 爬虫 9,12,15,17,20,24时",
                     settings.WEATHER_PUSH_TIME, settings.NEWS_PUSH_TIME)
        except ImportError:
            log.warning("APScheduler 未安装, 定时推送不可用 (pip install apscheduler)")
        except Exception as e:
            log.warning("推送调度器启动失败: %s", e)

    def stop(self):
        """停止所有定时任务"""
        if self.scheduler and self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False
            log.info("推送定时器已停止")
        self._executor.shutdown(wait=False)

    # ── 天气推送 ──

    def push_weather(self):
        """天气推送（07:00）：今日天气 + 穿衣/带伞建议（含超时、重试、防重叠）"""
        if not self._locks["weather"].acquire(blocking=False):
            log.info("天气推送: 上一任务仍在执行, 跳过本次触发")
            return
        try:
            success = self._run_with_timeout(self._do_push_weather, "weather_push")
            if not success:
                self._schedule_retry("weather_push", self._retry_push_weather)
        finally:
            self._locks["weather"].release()

    def _retry_push_weather(self):
        """天气推送重试（无锁检查 / 不重复调度重试，仅带超时保护）"""
        self._run_with_timeout(self._do_push_weather, "weather_push_retry")

    def _do_push_weather(self):
        """天气推送实际逻辑"""
        try:
            weather = self._get_weather()
            if not weather or not weather.get("text"):
                log.info("天气推送: 暂无天气数据")
                return

            city = weather.get("city", "北京")
            today = datetime.now().strftime("%Y-%m-%d")
            suggestion = weather.get("suggestion", {})

            content = NotifyContent(
                title=f"🌤 早安！{today} {city}天气",
                summary=f"{city} {weather['text']} {weather.get('temp', '')}",
                weather=weather,
            )

            for name, notifier in self.notifiers.items():
                try:
                    notifier.send(content)
                    log.info("天气推送成功 [%s]", name)
                except Exception as e:
                    log.warning("天气推送失败 [%s]: %s", name, e)

        except Exception as e:
            log.warning("天气推送异常: %s", e)
            raise  # 让上层 _run_with_timeout 感知失败

    # ── 新闻推送 ──

    def push_news(self):
        """新闻推送（09:00）：按媒体源分组 + 科技时事（含超时、防重叠）"""
        if not self._locks["news"].acquire(blocking=False):
            log.info("新闻推送: 上一任务仍在执行, 跳过本次触发")
            return
        try:
            self._run_with_timeout(self._do_push_news, "news_push")
        finally:
            self._locks["news"].release()

    def _do_push_news(self):
        """新闻推送实际逻辑"""
        try:
            from backend.database import SessionLocal
            from agent.news_service import news_service as ns

            db = SessionLocal()
            try:
                grouped = ns.get_daily_grouped(db)
                groups = grouped.get("groups", [])
                hot = grouped.get("hot_topics", [])
                today = datetime.now().strftime("%Y-%m-%d")

                # 构建推送内容：每源1条
                articles = []
                summary_parts = []
                for g in groups:
                    latest = g.get("latest")
                    if latest:
                        articles.append({"title": latest["title"], "url": latest["url"]})
                        summary_parts.append(f"📰 {g['source_name'] or g['source']} 1篇")

                # 热门话题标注
                if hot:
                    summary_parts.insert(0, f"🔥 热门话题: {'/'.join(hot[:3])}")

                content = NotifyContent(
                    title=f"📰 {today} 科技新闻速递",
                    summary=" | ".join(summary_parts) if summary_parts else "今日暂无新闻",
                    articles=articles[:10],
                )

                for name, notifier in self.notifiers.items():
                    try:
                        notifier.send(content)
                        log.info("新闻推送成功 [%s]: %d 源", name, len(groups))
                    except Exception as e:
                        log.warning("新闻推送失败 [%s]: %s", name, e)

                # 科技时事
                tech = ns.get_current_news(db, section="technology")
                if tech:
                    tech_content = NotifyContent(
                        title="📡 科技时事速递",
                        articles=[{"title": n.title, "url": n.url} for n in tech[:5]],
                    )
                    for name, notifier in self.notifiers.items():
                        try:
                            notifier.send(tech_content)
                        except Exception:
                            pass

            finally:
                db.close()

        except Exception as e:
            log.warning("新闻推送异常: %s", e)
            raise

    # ── 新闻爬取（9,12,15,17,20,24时定时执行） ──

    def crawl_news(self):
        """定时爬取新闻（检查新文章，增量更新）（含超时、防重叠）"""
        if not self._locks["crawl"].acquire(blocking=False):
            log.info("新闻爬取: 上一任务仍在执行, 跳过本次触发")
            return
        try:
            self._run_with_timeout(self._do_crawl_news, "news_crawl")
        finally:
            self._locks["crawl"].release()

    def _do_crawl_news(self):
        """新闻爬取实际逻辑"""
        try:
            from backend.database import SessionLocal
            from agent.news_service import news_service as ns

            db = SessionLocal()
            try:
                result = ns.refresh_daily(db)
                current = ns.refresh_current(db)
                if result.get("total", 0) > 0:
                    log.info("定时爬取: 每日新闻 %d 条, 时事 %s",
                             result["total"], current.get("message", ""))
            finally:
                db.close()
        except Exception as e:
            log.warning("定时爬取异常: %s", e)
            raise

    # ── 工具方法 ──

    def _get_weather(self) -> dict:
        """获取今日天气"""
        try:
            from agent.mcp.weather.weather_mcp import weather_handler
            import json
            data = json.loads(weather_handler("北京"))
            if "error" in data:
                return {}
            current = data.get("current", {})
            suggestion = data.get("suggestion", {})
            return {
                "city": data.get("city", "北京"),
                "temp": current.get("temp", ""),
                "text": current.get("text", ""),
                "suggestion": suggestion,
            }
        except Exception as e:
            log.warning("获取天气失败: %s", e)
            return {}

    # ── 手动触发 ──

    def push_now(self, push_type: str = "all") -> dict:
        """手动触发推送

        Args:
            push_type: "weather" / "news" / "all"
        """
        results = {}
        try:
            if push_type in ("weather", "all"):
                self.push_weather()
                results["weather"] = "ok"
            if push_type in ("news", "all"):
                self.push_news()
                results["news"] = "ok"
        except Exception as e:
            results["error"] = str(e)
        return results


push_scheduler = PushScheduler()
