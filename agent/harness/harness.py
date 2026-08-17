"""
Agent 工具执行安全围栏 (Tool Harness)

统一拦截所有 Agent 工具调用(注入点在 agent/tools/registry.py 的 SimpleTool.invoke),
提供五层防护:

1. 紧急熔断   emergency_stop : 一键暂停全部工具执行(事故时先按这个)
2. 风险分级   safe_mode      : 危险工具(任意命令/代码执行)默认禁止, 可开关
3. 命令校验                   复用 shell 白名单 + 危险模式正则(rm -rf / format / shutdown 等)
4. 路径围栏   path_fence     : 写文件/工作目录必须落在项目根内, 防越界写入
5. 限流+审计                  每分钟调用上限 + 全量调用记录(内存 + data/harness/audit.jsonl)

风险分级:
  safe      — 只读/查询, 始终放行
  medium    — 有副作用但非破坏(写项目内文件/网络请求), 默认放行
  dangerous — 可执行任意命令/代码/越界操作, 安全模式下禁止
"""
import json
import os
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from backend.config import DATA_DIR, PROJECT_ROOT

SAFE = "safe"
MEDIUM = "medium"
DANGEROUS = "dangerous"

# 未在表中列出的工具默认风险
DEFAULT_RISK = MEDIUM

# 工具风险表
TOOL_RISK = {
    # ── 危险: 任意命令/代码执行 ──
    "shell_execute": DANGEROUS,
    "cli_execute": DANGEROUS,
    "git_operation": DANGEROUS,
    "exec_in_sandbox": DANGEROUS,   # 无 Docker 时本地降级为直接执行 python/shell
    # ── 中等: 写文件/安装/网络 ──
    "write_md": MEDIUM,
    "write_word": MEDIUM,
    "write_excel": MEDIUM,
    "create_skill": MEDIUM,
    # ── 安全: 只读/查询 ──
    "read_md": SAFE,
    "read_word": SAFE,
    "read_excel": SAFE,
    "read_pdf": SAFE,
    "list_sheets": SAFE,
    "pdf_to_images": SAFE,
    "get_pdf_info": SAFE,
    "create_sandbox": SAFE,
    "destroy_sandbox": SAFE,
    "list_sandboxes": SAFE,
    "search_papers": SAFE,
    "search_papers_by_author": SAFE,
    "list_skill_templates": SAFE,
}

# 允许的命令白名单 — 单一来源: agent/tools/shell_tools/shell_tool.py(此处仅作导入失败的兜底)
_ALLOWED_COMMANDS_FALLBACK = {
    'dir', 'ls', 'cd', 'pwd', 'echo', 'type', 'cat',
    'find', 'where', 'python', 'node', 'npm', 'git', 'pip',
    'copy', 'move', 'mkdir',
}
try:
    from agent.tools.shell_tools.shell_tool import ALLOWED_COMMANDS
except Exception:  # noqa: BLE001
    ALLOWED_COMMANDS = set(_ALLOWED_COMMANDS_FALLBACK)

# ── 敏感文件路径(内容级限制: 读写删一律禁止) ──
SENSITIVE_PATH_PATTERNS = [
    r"(^|[/\\])\.env([\w.\-]*)$",          # .env / .env.local / .env.production
    r"\.(db|sqlite|sqlite3|db-wal|db-shm)$",  # 数据库(含用户哈希/API Key)
    r"\.(key|pem|p12|pfx|jks|jks)$",       # 私钥/证书
    r"(^|[/\\])\.git([/\\]|$)",            # git 元数据(config 含凭据)
    r"(^|[/\\])(secrets?|credentials?|passwords?)([/\\]|$)",  # 凭据类目录
    r"\.(pypirc|netrc|npmrc)$",            # 凭据配置文件
    r"(^|[/\\])model_providers",           # 模型配置(含 API Key 的表/文件)
    r"(^|[/\\])marketplace\.json$",        # 市场状态(可能含 MCP 配置)
]

# 写工具 → 允许的扩展名(防止用写工具篡改代码/配置文件)
WRITE_EXT_ALLOW = {
    "write_md": {".md", ".markdown", ".txt"},
    "write_word": {".docx", ".doc"},
    "write_excel": {".xlsx", ".xls", ".csv"},
}


def _trunc(value, limit):
    s = str(value)
    return s[:limit] + "…" if len(s) > limit else s


def _safe_args(args, limit=300):
    try:
        return json.dumps(args, ensure_ascii=False, default=str)[:limit]
    except Exception:
        return _trunc(args, limit)


class ToolHarness:
    """工具执行安全围栏(全局单例)"""

    def __init__(self):
        self._lock = threading.Lock()
        # ── 策略 ──
        self.safe_mode = True          # 危险工具默认禁止
        self.emergency_stop = False    # 熔断: 阻止所有工具
        self.path_fence = True         # 写路径限制在项目根内
        self.blocked_tools = set()     # 额外禁用名单
        self.max_calls_per_minute = 60
        # ── 运行状态 ──
        self._calls = deque()          # 近 60s 调用时间戳(限流)
        self._audit = deque(maxlen=500)  # 内存审计环形缓冲
        self.stats = {"checked": 0, "executed": 0, "blocked": 0}
        self.audit_file = DATA_DIR / "harness" / "audit.jsonl"
        try:
            self.audit_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001
            pass

    # ══════════════ 校验 ══════════════

    def check(self, name: str, args: dict = None, category: str = None):
        """执行前校验, 返回 (allowed: bool, reason: str)"""
        args = args or {}
        with self._lock:
            self.stats["checked"] += 1
            # 1. 紧急熔断
            if self.emergency_stop:
                return False, "紧急熔断已开启: 所有工具执行已被暂停"
            # 2. 禁用名单
            if name in self.blocked_tools:
                return False, f"工具 [{name}] 已被安全策略禁用"
            # 3. 风险分级(用户上传的工具包一律视为危险)
            risk = TOOL_RISK.get(name, DEFAULT_RISK)
            if category == "user_uploaded":
                risk = DANGEROUS
            if self.safe_mode and risk == DANGEROUS:
                return False, (f"工具 [{name}] 属于危险操作(可执行任意命令/代码), "
                               f"安全模式下已禁止。可在「设置→安全围栏」关闭安全模式后重试")
            # 4. 限流
            now = time.time()
            while self._calls and now - self._calls[0] > 60:
                self._calls.popleft()
            if len(self._calls) >= self.max_calls_per_minute:
                return False, f"工具调用过于频繁(每分钟上限 {self.max_calls_per_minute} 次), 请稍后再试"
            self._calls.append(now)

        # 5. 命令级校验(始终生效, 与 safe_mode 无关)
        if name in ("shell_execute", "cli_execute"):
            cmd = f"{args.get('command', '')} {args.get('args', '')}".strip()
            ok, reason = self._check_command(cmd)
            if not ok:
                return False, reason
        # 6. 路径围栏
        if self.path_fence:
            reason = self._check_paths(args, name)
            if reason:
                return False, reason
        return True, ""

    def _check_command(self, cmd: str):
        """命令白名单 + 危险模式检查(复用 shell_tool 实现)"""
        if not cmd.strip():
            return False, "命令为空"
        try:
            from agent.tools.shell_tools.shell_tool import _get_base_command, _check_dangerous
        except Exception:  # noqa: BLE001
            return True, ""  # shell_tool 不可用时不额外拦截
        base = _get_base_command(cmd)
        if not base:
            return False, "命令为空"
        if base not in ALLOWED_COMMANDS:
            return False, (f"命令 '{base}' 不在白名单, 已拒绝。允许: "
                           f"{', '.join(sorted(ALLOWED_COMMANDS))}")
        reason = _check_dangerous(cmd)
        if reason:
            return False, f"危险命令被拦截: {reason}"
        return True, ""

    def _check_paths(self, args: dict, name: str):
        """路径围栏 + 内容级限制:
        - 目标路径必须位于项目根目录内(防越界)
        - 敏感文件(.env/.db/.key/.pem/.git 凭据等)禁止读写
        - 写工具只允许写对应扩展名(防篡改代码/配置)
        """
        import re as _re
        root = os.path.abspath(str(PROJECT_ROOT))
        prefix = root.rstrip(os.sep) + os.sep

        def _verify(p, label):
            if not p:
                return None
            try:
                abs_p = os.path.abspath(os.path.expanduser(str(p)))
            except Exception:  # noqa: BLE001
                return f"路径围栏: {label} 参数非法: {p}"
            if abs_p != root and not abs_p.startswith(prefix):
                return (f"路径围栏: {label} 指向项目目录之外({abs_p}), 已拒绝。"
                        f"可在「设置→安全围栏」关闭路径围栏")
            # 内容级限制: 敏感路径禁止访问(读写删)
            norm = abs_p.replace("\\", "/")
            for pat in SENSITIVE_PATH_PATTERNS:
                if _re.search(pat, norm, _re.IGNORECASE):
                    return f"内容限制: {label} 命中敏感文件规则({pat}), 禁止访问"
            # 写工具扩展名校验
            allow_exts = WRITE_EXT_ALLOW.get(name)
            if allow_exts is not None:
                ext = os.path.splitext(abs_p)[1].lower()
                if ext not in allow_exts:
                    return (f"内容限制: 工具 [{name}] 只能写 {sorted(allow_exts)} 文件, "
                            f"目标扩展名 {ext or '(无)'} 已拒绝")
            return None

        if name in ("shell_execute", "cli_execute"):
            return _verify(args.get("workdir"), "工作目录")
        if name == "git_operation":
            r = _verify(args.get("workdir"), "工作目录")
            if r:
                return r
            params = args.get("params") or {}
            return _verify(params.get("dir"), "克隆目标目录")
        if name in ("write_md", "write_word", "write_excel", "read_md",
                    "read_word", "read_excel", "read_pdf", "pdf_to_images",
                    "get_pdf_info", "list_sheets"):
            return _verify(args.get("path"), "文件路径")
        return None

    # ══════════════ 审计 ══════════════

    def record(self, name: str, args: dict = None, ok: bool = True,
               reason: str = "", result: str = ""):
        """记录一次工具调用(内存 + JSONL 文件)"""
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "tool": name,
            "ok": bool(ok),
            "reason": _trunc(reason or "", 200),
            "args": _safe_args(args or {}, 300),
            "result": _trunc(result or "", 300),
        }
        with self._lock:
            self._audit.append(entry)
            self.stats["executed" if ok else "blocked"] += 1
        try:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001
            pass

    # ══════════════ 策略控制 ══════════════

    def set_safe_mode(self, enabled: bool):
        with self._lock:
            self.safe_mode = bool(enabled)

    def set_emergency_stop(self, enabled: bool):
        with self._lock:
            self.emergency_stop = bool(enabled)

    def set_path_fence(self, enabled: bool):
        with self._lock:
            self.path_fence = bool(enabled)

    def block_tool(self, name: str, blocked: bool):
        with self._lock:
            if blocked:
                self.blocked_tools.add(name)
            else:
                self.blocked_tools.discard(name)

    def status(self) -> dict:
        with self._lock:
            try:
                from agent.tools.sandbox.sandbox_tool import docker_available
                docker_ok = docker_available()
            except Exception:  # noqa: BLE001
                docker_ok = False
            return {
                "safe_mode": self.safe_mode,
                "emergency_stop": self.emergency_stop,
                "path_fence": self.path_fence,
                "docker_available": docker_ok,
                "blocked_tools": sorted(self.blocked_tools),
                "max_calls_per_minute": self.max_calls_per_minute,
                "stats": dict(self.stats),
                "risk_table": {k: v for k, v in sorted(TOOL_RISK.items())},
                "sensitive_patterns": list(SENSITIVE_PATH_PATTERNS),
                "audit_file": str(self.audit_file),
            }

    def recent_audit(self, n: int = 50) -> list:
        with self._lock:
            return list(self._audit)[-n:]


# 全局单例
tool_harness = ToolHarness()
