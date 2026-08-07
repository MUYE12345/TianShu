"""
日志查看路由 — 浏览和搜索运行日志
"""
import os
from datetime import datetime
from fastapi import APIRouter, Query
from backend.core.logger import log
from backend.config import settings

router = APIRouter()

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")


@router.get("")
def list_logs():
    """列出可用的日志文件"""
    if not os.path.exists(LOG_DIR):
        return {"files": []}
    files = []
    for f in sorted(os.listdir(LOG_DIR), reverse=True)[:20]:
        fpath = os.path.join(LOG_DIR, f)
        if os.path.isfile(fpath):
            files.append({
                "name": f,
                "size_kb": round(os.path.getsize(fpath) / 1024, 1),
                "modified": datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M"),
            })
    return {"files": files}


@router.get("/tail")
def tail_log(lines: int = Query(50, description="返回行数"), keyword: str = Query("", description="过滤关键词")):
    """实时查看最新日志（从 logs/ 目录下最新的 .log 文件读取）"""
    if not os.path.exists(LOG_DIR):
        return {"lines": [], "source": "none"}

    log_files = sorted(
        [f for f in os.listdir(LOG_DIR) if f.endswith(".log")],
        reverse=True,
    )
    if not log_files:
        return {"lines": [], "source": "none"}

    latest = os.path.join(LOG_DIR, log_files[0])
    try:
        with open(latest, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        if keyword:
            filtered = [l for l in all_lines if keyword in l]
            result = filtered[-lines:]
        else:
            result = all_lines[-lines:]
        return {"lines": result, "source": log_files[0], "total": len(all_lines)}
    except Exception as e:
        return {"lines": [f"读取日志失败: {e}"], "source": "error"}
