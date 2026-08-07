"""
CLI工具 — 运行自定义CLI命令
"""
import subprocess
from agent.tools.registry import register_tool


def cli_execute(command: str, args: str = "", timeout: int = 30) -> str:
    """执行CLI命令"""
    full_cmd = f"{command} {args}".strip()
    try:
        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (result.stdout or result.stderr).strip()[:5000]
    except Exception as e:
        return f"错误: {str(e)}"


register_tool(name="cli_execute", description="执行自定义CLI命令",
    parameters={"type": "object", "properties": {
        "command": {"type": "string", "description": "命令名称"},
        "args": {"type": "string", "description": "命令参数"},
        "timeout": {"type": "integer", "description": "超时秒数", "default": 30}
    }, "required": ["command"]},
    handler=cli_execute, category="cli")
