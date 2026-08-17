"""
Shell命令执行工具

安全设计:
1. 命令白名单: 只允许 ALLOWED_COMMANDS 中的基础命令(阻止 rm/format/shutdown 等)
2. 危险模式拦截: 对白名单命令的**参数组合**做二次校验, 拦截破坏性用法
   (如 `del /f /s`、`rd /s /q`、`python -c "import os; os.remove..."` 等),
   因为仅校验首 token 无法挡住 `del /f /s /q C:\` 这类参数化破坏。
3. 删除类命令路径保护: 禁止对系统关键目录执行删除。
4. 风险边界说明: 本工具信任由用户配置的模型, 无法静态防住所有恶意模型输出
   (如 `python` 可执行任意代码); 这里的目标是挡住明显的破坏性 shell 用法,
   并把高危命令(rm/format/shutdown/mkfs/diskpart)从白名单彻底排除。
"""
import re
import subprocess
from agent.tools.registry import register_tool

# 允许执行的命令白名单（阻止 rm -rf / del /f /s format shutdown 等危险命令）
ALLOWED_COMMANDS = {
    'dir', 'ls', 'cd', 'pwd', 'echo', 'type', 'cat',
    'find', 'where', 'python', 'node', 'npm', 'git', 'pip',
    'copy', 'move', 'mkdir',
    # 'del' 已从白名单移除: 参数组合风险过高(del /f /s /q 可递归清盘),
    # 需要删除文件请使用 file_tools 或明确、受限的调用
}

# 无论基础命令是什么, 命中这些模式一律拒绝（覆盖 cmd 与 bash 两种语法）
DANGEROUS_PATTERNS = [
    # 递归/强制删除类 (cmd)
    re.compile(r'\bdel\s+[/\w]*[fsq]', re.IGNORECASE),
    re.compile(r'\brd\s+[/\w]*[sq]', re.IGNORECASE),
    re.compile(r'\berase\s+[/\w]*[fsq]', re.IGNORECASE),
    # 递归/强制删除类 (bash)
    re.compile(r'\brm\s+(-\w*\s*)*[-]?r', re.IGNORECASE),   # rm -r / rm --recursive
    re.compile(r'\brm\s+(-\w*\s*)*[-]?f', re.IGNORECASE),   # rm -f
    re.compile(r'\brmdir\s+[/\w]*[sq]', re.IGNORECASE),
    # 磁盘/系统破坏
    re.compile(r'\bformat\b', re.IGNORECASE),
    re.compile(r'\bmkfs\b', re.IGNORECASE),
    re.compile(r'\bdiskpart\b', re.IGNORECASE),
    re.compile(r'\bshutdown\b', re.IGNORECASE),
    re.compile(r'\breboot\b', re.IGNORECASE),
    re.compile(r'\bhibernate\b', re.IGNORECASE),
    re.compile(r'\brestart\s+-s', re.IGNORECASE),
    re.compile(r'\btaskkill\b', re.IGNORECASE),
    # 写入系统关键区域
    re.compile(r'(?:echo|printf|copy|move|type|cat)\s+.*?(?:>>|>)\s*["\']?(?:C:\\|/|\\\\)\s*(?:Windows|Program\s*Files|System32|Users|/etc|/bin|/usr|/var|/boot)', re.IGNORECASE),
    # python/node 内联执行破坏代码
    re.compile(r'\bpython[^\n]*\b(?:os\.system|os\.remove|shutil\.rmtree|subprocess)\b', re.IGNORECASE),
    re.compile(r'\bnode[^\n]*\b(?:child_process|fs\.unlinkSync|fs\.rmSync)\b', re.IGNORECASE),
    # npm/pip/git 危险组合
    re.compile(r'\bnpm\s+(?:uninstall\s+-g\s+--force|cache\s+clean\s+--force)', re.IGNORECASE),
    re.compile(r'\bpip\s+uninstall\s+-y\s+(?:pip|setuptools|wheel)', re.IGNORECASE),
    re.compile(r'\bgit\s+clean\s+-\w*f', re.IGNORECASE),
]

# 删除类命令禁止作用的关键路径（路径前缀匹配, 大小写不敏感）
FORBIDDEN_DELETE_PATHS = [
    'c:\\windows', 'c:\\program files', 'c:\\programdata', 'c:\\system volume information',
    'c:\\users\\default', '/etc', '/bin', '/sbin', '/usr', '/var', '/boot', '/root',
]

# 匹配删除类命令及其目标路径: `del C:\Windows\...` / `rm /etc/...`
_DELETE_CMD = re.compile(r'^\s*(?:del|rm|rd|erase|rmdir)\b', re.IGNORECASE)
_PATH_TOKEN = re.compile(r'["\']?([A-Za-z]:\\[^\s"\']+|/[^\s"\']+)["\']?', re.IGNORECASE)


def _get_base_command(command: str) -> str:
    """提取命令字符串中的基础命令名"""
    command = command.strip()
    if not command:
        return ""
    # 取第一个 token 作为基础命令
    return command.split(maxsplit=1)[0]


def _check_dangerous(command: str) -> str | None:
    """检查命令是否命中危险模式或删除关键路径。命中返回拒绝原因, 否则 None。"""
    for pat in DANGEROUS_PATTERNS:
        if pat.search(command):
            return f"危险命令模式被拦截: {pat.pattern}"
    # 删除类命令的路径保护
    if _DELETE_CMD.match(command):
        for m in _PATH_TOKEN.finditer(command):
            target = m.group(1).rstrip('/\\ ').lower()
            if not target:
                continue
            for forbidden in FORBIDDEN_DELETE_PATHS:
                if target == forbidden or target.startswith(forbidden):
                    return f"拒绝删除系统关键路径: {m.group(1)}"
    return None


def shell_execute(command: str, timeout: int = 30, workdir: str = None) -> str:
    """执行Shell命令"""
    # 白名单检查
    base_cmd = _get_base_command(command)
    if not base_cmd:
        return "错误: 命令为空"
    if base_cmd not in ALLOWED_COMMANDS:
        return f"错误: 命令 '{base_cmd}' 不在允许列表中，已拒绝执行。允许的命令: {', '.join(sorted(ALLOWED_COMMANDS))}"

    # 危险模式/路径二次检查
    reason = _check_dangerous(command)
    if reason:
        return f"错误: {reason}。命令已拒绝执行。"

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
    description="执行Shell命令并返回输出结果。可用于运行脚本、查看目录、文件操作(非删除)等。删除文件请使用受限的文件工具。",
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
