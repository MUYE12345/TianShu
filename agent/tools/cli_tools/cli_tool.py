"""
CLI工具 — 运行自定义CLI命令

安全设计: 与 shell_execute 一致, 复用其命令白名单 + 危险模式拦截
(阻止 rm -rf / del /f /s / format / shutdown 等破坏性用法)。
"""
import subprocess
from agent.tools.registry import register_tool
from agent.tools.shell_tools.shell_tool import ALLOWED_COMMANDS, _get_base_command, _check_dangerous


def cli_execute(command: str, args: str = "", timeout: int = 30) -> str:
    """执行CLI命令(白名单 + 危险模式防护)"""
    full_cmd = f"{command} {args}".strip()
    base = _get_base_command(full_cmd)
    if not base:
        return "错误: 命令为空"
    if base not in ALLOWED_COMMANDS:
        return f"错误: 命令 '{base}' 不在允许列表中，已拒绝执行。允许的命令: {', '.join(sorted(ALLOWED_COMMANDS))}"
    reason = _check_dangerous(full_cmd)
    if reason:
        return f"错误: {reason}。命令已拒绝执行。"
    try:
        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (result.stdout or result.stderr).strip()[:5000]
    except Exception as e:
        return f"错误: {str(e)}"


register_tool(name="cli_execute", description="执行自定义CLI命令(白名单命令, 破坏性用法会被拦截)",
    parameters={"type": "object", "properties": {
        "command": {"type": "string", "description": "命令名称"},
        "args": {"type": "string", "description": "命令参数"},
        "timeout": {"type": "integer", "description": "超时秒数", "default": 30}
    }, "required": ["command"]},
    handler=cli_execute, category="cli")
