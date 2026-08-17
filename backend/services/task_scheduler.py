"""
定时任务调度器 — 消费 scheduled_tasks 表的 cron 表达式, 到点自动执行 Agent

补齐「Cron 可视化但无自动执行循环」的架构缺口:
- 启动时从 DB 加载 recurring 任务, 用 APScheduler CronTrigger(5/6 字段) 注册
- 到点在守护线程中执行 agent_service.run(prompt, f"task_{id}"), 消费事件流
- 执行后回写 last_fired_at; 任务增删/cron 变更时调用 reload() 刷新调度表
"""
import asyncio
import threading
from datetime import datetime

from backend.core.logger import log


class TaskScheduler:
    """scheduled_tasks 表的后台调度器(单例)"""

    def __init__(self):
        self.scheduler = None
        self._started = False
        self._lock = threading.Lock()

    def start(self):
        if self._started:
            return
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            self.scheduler = BackgroundScheduler()
            self._register_tasks()
            self.scheduler.start()
            self._started = True
            log.info("[任务调度] 已启动, scheduled_tasks 定时任务自动执行已启用")
        except ImportError:
            log.warning("[任务调度] APScheduler 未安装, 定时任务自动执行不可用")
        except Exception as e:  # noqa: BLE001
            log.warning("[任务调度] 调度器启动失败: %s", e)

    # ── 注册 ──

    def _register_tasks(self):
        from backend.database import SessionLocal
        from backend.models.task import ScheduledTask
        db = SessionLocal()
        try:
            tasks = db.query(ScheduledTask).filter(
                ScheduledTask.recurring.is_(True)).all()
            for t in tasks:
                self._add_job(t.id, t.cron, t.prompt)
        except Exception as e:  # noqa: BLE001
            log.warning("[任务调度] 加载定时任务失败: %s", e)
        finally:
            db.close()

    def _add_job(self, task_id: int, cron_expr: str, prompt: str):
        try:
            from apscheduler.triggers.cron import CronTrigger
            trigger = CronTrigger.from_crontab(cron_expr)
            self.scheduler.add_job(
                lambda: self._spawn_run(task_id, prompt),
                trigger,
                id=f"task_{task_id}",
                replace_existing=True,
                misfire_grace_time=300,
            )
            log.info("[任务调度] 已注册任务 %s: cron=%s", task_id, cron_expr)
        except Exception as e:  # noqa: BLE001
            log.warning("[任务调度] 任务 %s 的 cron '%s' 无法解析, 跳过: %s",
                        task_id, cron_expr, e)

    # ── 执行 ──

    def _spawn_run(self, task_id: int, prompt: str):
        """守护线程中运行 Agent 任务(不阻塞调度线程), 完成后回写 last_fired_at"""
        def _drain():
            try:
                from agent.agent_service import agent_service

                async def _consume():
                    async for _ev in agent_service.run(prompt, f"task_{task_id}"):
                        pass
                asyncio.run(_consume())
            except Exception as e:  # noqa: BLE001
                log.warning("[任务调度] 任务 %s 执行异常: %s", task_id, e)
            finally:
                self._mark_fired(task_id)

        threading.Thread(target=_drain, daemon=True).start()

    def _mark_fired(self, task_id: int):
        try:
            from backend.database import SessionLocal
            from backend.models.task import ScheduledTask
            db = SessionLocal()
            try:
                t = db.query(ScheduledTask).filter(
                    ScheduledTask.id == task_id).first()
                if t:
                    t.last_fired_at = datetime.now()
                    db.commit()
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            pass

    # ── 刷新/停止 ──

    def reload(self):
        """任务增删或 cron 变更后同步调度表(幂等)"""
        with self._lock:
            if self.scheduler is None:
                return
            from backend.database import SessionLocal
            from backend.models.task import ScheduledTask
            db = SessionLocal()
            try:
                tasks = db.query(ScheduledTask).all()
            finally:
                db.close()
            recurring_ids = {t.id for t in tasks if t.recurring}
            # 移除已删除/不再 recurring 的任务
            for job in list(self.scheduler.get_jobs()):
                if job.id.startswith("task_"):
                    tid = int(job.id.split("_", 1)[1])
                    if tid not in recurring_ids:
                        try:
                            self.scheduler.remove_job(job.id)
                        except Exception:  # noqa: BLE001
                            pass
            # 新增/更新
            for t in tasks:
                if not t.recurring:
                    continue
                job_id = f"task_{t.id}"
                job = self.scheduler.get_job(job_id)
                if job is None:
                    self._add_job(t.id, t.cron, t.prompt)
                else:
                    # cron 表达式变了 → 替换
                    try:
                        from apscheduler.triggers.cron import CronTrigger
                        new_trigger = CronTrigger.from_crontab(t.cron)
                    except Exception:  # noqa: BLE001
                        continue
                    if str(job.trigger) != str(new_trigger):
                        self.scheduler.reschedule_job(job_id, trigger=new_trigger)
                        log.info("[任务调度] 任务 %s cron 已更新为 %s", t.id, t.cron)

    def stop(self):
        if self.scheduler and self._started:
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:  # noqa: BLE001
                pass
            self._started = False
            log.info("[任务调度] 已停止")


task_scheduler = TaskScheduler()
