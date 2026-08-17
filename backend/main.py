"""
Tianshu — FastAPI 应用入口

启动: uvicorn backend.main:app --reload --port 8000
"""
import os, sys, time, threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.core.logger import log
from backend.database import init_db
from backend.core.exceptions import register_exception_handlers
from backend.core.model_config import model_manager
from agent.mcp_service import mcp_service
from agent.memory.memory_manager import memory_manager
from agent.notification.scheduler import push_scheduler


def _load_model_config_from_db():
    """从数据库加载模型配置，覆盖 .env 默认值"""
    try:
        from backend.database import SessionLocal
        db = SessionLocal()
        try:
            model_manager.reload_from_db(db)
            log.info("[模型] 已从数据库加载模型配置")
        finally:
            db.close()
    except Exception as e:
        log.warning("[模型] 从数据库加载失败，使用 .env 兜底: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    init_db()
    _load_model_config_from_db()
    mcp_service.initialize()
    memory_manager.initialize()
    # 恢复市场持久化安装/启用状态(工具/MCP/SKILL)
    try:
        from backend.services.marketplace_state import apply_marketplace_state
        apply_marketplace_state()
    except Exception as e:
        log.warning("市场状态恢复失败(忽略): %s", e)
    push_scheduler.start()  # 启动每日新闻推送定时器
    # 飞书长连接模式(免公网): 配置 FEISHU_LONG_CONNECTION=true + APP_ID/SECRET 后,
    # 本地连飞书网关, 用户在飞书里发消息即可触发 agent
    if settings.FEISHU_LONG_CONNECTION:
        try:
            from agent.notification.feishu.bot import feishu_bot
            feishu_bot.start_long_connection()
        except Exception as e:  # noqa: BLE001
            log.warning("飞书长连接启动失败: %s", e)
    # 桌面应用(划屏翻译/桌宠): 默认不启动; LAUNCH_DESKTOP_APPS=true 时随服务端拉起
    if settings.LAUNCH_DESKTOP_APPS:
        try:
            _launch_desktop_apps()
        except Exception as e:  # noqa: BLE001
            log.warning("桌面应用启动失败(可另跑 run_desktop.py): %s", e)
    log.info("%s v0.1.0 启动成功", settings.APP_NAME)
    log.info("数据库: %s", settings.DATABASE_URL)

    # ── 安全检查 ──
    if settings.JWT_SECRET == "change-this-in-production":
        log.warning("=" * 60)
        log.warning("安全警告: JWT_SECRET 仍为默认值 'change-this-in-production'!")
        log.warning("请在 .env 中设置 JWT_SECRET 为足够长的随机字符串以保障生产环境安全。")
        log.warning("=" * 60)

    cors_val = settings.CORS_ORIGINS.strip()
    if not cors_val or cors_val == "*":
        log.warning("=" * 60)
        log.warning("安全警告: CORS_ORIGINS 当前设为 '%s'，表示允许所有来源跨域访问！", cors_val if cors_val else "(空)")
        log.warning("请在 .env 中设置 CORS_ORIGINS 为具体的前端地址，例如: http://localhost:5173")
        log.warning("=" * 60)

    yield
    push_scheduler.stop()
    log.info("应用关闭")


def _launch_desktop_apps():
    """后台线程启动桌面应用（tkinter 轻量版, 桌面管理器提供重开/退出策略）
    """
    def _start():
        try:
            from backend.desktop_manager import DesktopManager
            mgr = DesktopManager("all")
            mgr.show_window("translate")
            mgr.show_window("pet")
            mgr.run()
        except ImportError as e:
            log.info("跳过桌面应用（tkinter 不可用: %s）", e)
        except Exception as e:
            log.warning("桌面启动失败: %s", e)

    threading.Thread(target=_start, daemon=True).start()
    log.info("[桌面] 后台线程已启动（可独立运行: python run_desktop.py）")


def create_app() -> FastAPI:
    """应用工厂"""
    app = FastAPI(
        title=settings.APP_NAME,
        description="个人AI辅助工具 — 天枢",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── 中间件 ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 异常处理器 ──
    register_exception_handlers(app)

    # ── 路由 ──
    from backend.routers import (
        auth, news, paper, wiki, chat, session,
        settings as settings_router,
        notification, companion, memory, storage, tasks,
        plan, mcp, skills, tools, logs,
        agent, cron, tool_marketplace,
        feishu, models as models_router,
        harness as harness_router,
    )

    app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
    app.include_router(news.router, prefix="/api/news", tags=["新闻"])
    app.include_router(paper.router, prefix="/api/paper", tags=["论文"])
    app.include_router(wiki.router, prefix="/api/wiki", tags=["Wiki"])
    app.include_router(chat.router, prefix="/api/chat", tags=["问答"])
    app.include_router(session.router, prefix="/api/sessions", tags=["会话"])
    app.include_router(settings_router.router, prefix="/api/settings", tags=["设置"])
    app.include_router(models_router.router, prefix="/api/models", tags=["模型"])
    app.include_router(notification.router, prefix="/api/notify", tags=["推送"])
    app.include_router(companion.router, prefix="/api/companion", tags=["陪伴"])
    app.include_router(memory.router, prefix="/api/memory", tags=["记忆"])
    app.include_router(storage.router, prefix="/api/storage", tags=["存储"])
    app.include_router(plan.router, prefix="/api/plans", tags=["规划"])
    app.include_router(mcp.router, prefix="/api/mcp", tags=["MCP"])
    app.include_router(skills.router, prefix="/api/skills", tags=["SKILL"])
    app.include_router(tasks.router, prefix="/api/tasks", tags=["任务"])
    app.include_router(tools.router, prefix="/api/tools", tags=["工具"])
    app.include_router(logs.router, prefix="/api/logs", tags=["日志"])
    app.include_router(agent.router, prefix="/api/agents", tags=["智能体"])
    app.include_router(cron.router, prefix="/api/cron", tags=["定时任务"])
    app.include_router(tool_marketplace.router, prefix="/api/tool-marketplace", tags=["工具市场"])
    app.include_router(feishu.router, prefix="/api/feishu", tags=["飞书"])
    from backend.routers.upload import router as upload_router
    app.include_router(upload_router, prefix="/api/upload", tags=["上传"])
    from backend.routers.knowledge import router as knowledge_router
    app.include_router(knowledge_router, prefix="/api/knowledge", tags=["知识库"])
    from backend.routers.teams import router as teams_router
    app.include_router(teams_router, prefix="/api/teams", tags=["编排团队"])
    from backend.routers.harness import router as harness_router
    app.include_router(harness_router, prefix="/api/harness", tags=["安全围栏"])

    # ── 静态文件 ──
    # 只暴露上传目录 (data/uploads), 绝不挂载整个 data/ (含 housekeeper.db/API Key, 会直接泄露)
    from backend.config import DATA_DIR
    upload_dir = settings.UPLOAD_DIR if settings.UPLOAD_DIR and str(settings.UPLOAD_DIR).lower() != str(DATA_DIR).lower() else str(DATA_DIR / "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=upload_dir), name="static")

    # ── 根路径 ──
    @app.get("/")
    def root():
        return {
            "app": settings.APP_NAME,
            "version": "0.1.0",
            "docs": "/docs",
        }

    @app.get("/health")
    def health():
        """健康检查端点（用于容器编排和监控）"""
        health_status = {"status": "ok", "app": settings.APP_NAME, "version": "0.1.0"}

        # 数据库健康检查
        try:
            from backend.database import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            db.close()
        except Exception:
            health_status["database"] = "unhealthy"
            health_status["status"] = "degraded"
        else:
            health_status["database"] = "ok"

        # 模型配置检查
        model_ok = bool(settings.MAIN_MODEL_API_KEY and settings.MAIN_MODEL_API_KEY != "YOUR_DEEPSEEK_API_KEY_HERE")
        health_status["model_configured"] = model_ok

        return health_status

    return app


app = create_app()
