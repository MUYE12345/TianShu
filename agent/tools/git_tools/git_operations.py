"""
Git操作工具
"""
import os
import subprocess
from agent.tools.registry import register_tool

GIT_COMMANDS = {
    "clone": "git clone {repo} {dir}",
    "add": "git add {paths}",
    "commit": 'git commit -m "{message}"',
    "push": "git push",
    "pull": "git pull",
    "status": "git status",
    "log": "git log --oneline -{count}",
    "branch": "git branch -a",
    "checkout": "git checkout {branch}",
    "diff": "git diff",
    "init": "git init",
}


def _get_project_root() -> str:
    """获取项目根目录

    优先从 backend.config 设置中获取，否则使用当前工作目录。
    """
    try:
        from backend.config import settings
        upload_dir = getattr(settings, 'UPLOAD_DIR', '')
        if upload_dir:
            abs_upload = os.path.abspath(upload_dir)
            return os.path.abspath(os.path.join(abs_upload, ".."))
    except Exception:
        pass
    return os.path.abspath(os.getcwd())


PROJECT_ROOT = _get_project_root()


def _ensure_path_in_project(path: str) -> str:
    """验证路径在项目目录内，防止路径遍历"""
    if not path:
        return None  # None 表示使用默认目录
    abs_path = os.path.abspath(path)
    prefix = PROJECT_ROOT.rstrip(os.sep) + os.sep
    if abs_path != PROJECT_ROOT and not abs_path.startswith(prefix):
        raise ValueError(f"路径 '{path}' 指向项目目录之外，已拒绝")
    return abs_path


def git_handler(action: str, params: dict = None, workdir: str = None) -> str:
    """执行Git操作"""
    params = params or {}
    cmd_template = GIT_COMMANDS.get(action)
    if not cmd_template:
        return f"不支持的Git操作: {action}"

    # 验证工作目录在项目内
    try:
        safe_workdir = _ensure_path_in_project(workdir) if workdir else PROJECT_ROOT
    except ValueError as e:
        return f"错误: {str(e)}"

    # 对于 clone 操作，验证目标目录在项目内
    clone_dir = params.get("dir", "")
    if action == "clone" and clone_dir:
        try:
            _ensure_path_in_project(clone_dir)
        except ValueError as e:
            return f"错误: {str(e)}"

    # 填充参数
    cmd = cmd_template.format(
        repo=params.get("repo", ""),
        dir=params.get("dir", ""),
        paths=" ".join(params.get("paths", ["."])),
        message=params.get("message", "update"),
        count=params.get("count", "10"),
        branch=params.get("branch", "main"),
    )

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=safe_workdir, timeout=60)
        return (result.stdout or result.stderr).strip()
    except Exception as e:
        return f"Git错误: {str(e)}"


register_tool(
    name="git_operation",
    description="执行Git操作: clone/add/commit/push/pull/status/log/branch/checkout/diff/init",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(GIT_COMMANDS.keys()),
                "description": "Git操作类型"
            },
            "params": {"type": "object", "description": "操作参数字典"},
            "workdir": {"type": "string", "description": "仓库所在目录"},
        },
        "required": ["action"]
    },
    handler=git_handler,
    category="git",
)
