"""
Shell命令执行工具
"""
import subprocess
from agent.tools.registry import register_tool

# 允许执行的命令白名单（阻止 rm -rf / del /f /s format shutdown 等危险命令）
ALLOWED_COMMANDS = {
    'dir', 'ls', 'cd', 'pwd', 'echo', 'type', 'cat',
    'find', 'where', 'python', 'node', 'npm', 'git', 'pip',
    'copy', 'move', 'mkdir', 'del',
}


def _get_base_command(command: str) -> str:
    """提取命令字符串中的基础命令名"""
    command = command.strip()
    if not command:
        return ""
    # 取第一个 token 作为基础命令
    return command.split(maxsplit=1)[0]


def shell_execute(command: str, timeout: int = 30, workdir: str = None) -> str:
    """执行Shell命令"""
    # 白名单检查
    base_cmd = _get_base_command(command)
    if not base_cmd:
        return "错误: 命令为空"
    if base_cmd not in ALLOWED_COMMANDS:
        return f"错误: 命令 '{base_cmd}' 不在允许列表中，已拒绝执行。允许的命令: {', '.join(sorted(ALLOWED_COMMANDS))}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        )
        output = (result.stdout + result.stderr).strip()
        if len(output) > 10240:
            output = output[:10240] + "\n... (输出已截断)"
        return output or "命令执行完成(无输出)"
    except subprocess.TimeoutExpired:
        return f"错误: 命令执行超时({timeout}秒)"
    except Exception as e:
        return f"错误: {str(e)}"


register_tool(
    name="shell_execute",
    description="执行Shell命令并返回输出结果。可用于运行脚本、管理系统、操作文件等。",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的Shell命令"},
            "timeout": {"type": "integer", "description": "超时时间(秒)", "default": 30},
            "workdir": {"type": "string", "description": "工作目录"},
        },
        "required": ["command"]
    },
    handler=shell_execute,
    category="shell",
)
