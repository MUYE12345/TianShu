"""
统一日志工具 — 替代全局的 print() 和静默 except:pass

用法:
  from backend.core.logger import log
  log.info("消息")
  log.warning("警告")
  log.error("错误", exc_info=True)
"""
import sys
import logging
from backend.config import settings

# Windows 下 sys.stdout 默认 GBK, 日志含 emoji/中文时 StreamHandler 会抛 UnicodeEncodeError
# 统一改为 UTF-8 + errors=replace, 保证日志不因字符编码崩溃
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 创建项目根 logger
logger = logging.getLogger("intelligent_housekeeper")
logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

# 控制台 Handler
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
formatter = logging.Formatter(
    "[%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
console.setFormatter(formatter)
logger.handlers.clear()
logger.addHandler(console)

log = logger
