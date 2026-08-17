"""
沙箱工具 — Docker 容器安全执行环境(仅 Docker, 无本地直接执行回退)
支持: 创建/执行/销毁沙箱, Python/Shell 代码隔离运行

安全说明: 代码/命令执行一律在 Docker 容器内(--network=none --cap-drop=ALL
--security-opt=no-new-privileges)。Docker 不可用时返回错误, 绝不降级到宿主机
直接执行, 防止危险操作落在本机。
"""
import uuid
import subprocess
from typing import Optional
from agent.tools.registry import register_tool

# 内存沙箱存储
_sandboxes: dict[str, dict] = {}

# Docker镜像
DEFAULT_IMAGE = "python:3.11-slim"
LOCAL_IMAGES = ["alpine:latest", "python:3-slim", "python:3.11-slim", "busybox:latest"]


def docker_available() -> bool:
    """Docker daemon 是否可用(供安全围栏/界面展示)"""
    try:
        result = subprocess.run(["docker", "ps"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _find_local_image() -> Optional[str]:
    """查找本地可用的Docker镜像(按优先级)"""
    try:
        result = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
            capture_output=True, text=True, timeout=5,
            encoding="utf-8", errors="replace",
        )
        available = set(result.stdout.strip().split("\n"))
        for img in LOCAL_IMAGES:
            if img in available:
                return img
        for img in available:
            if "python" in img or "alpine" in img:
                return img
    except Exception:  # noqa: BLE001
        pass
    return None


def create_sandbox(image: str = DEFAULT_IMAGE, name: str = "") -> str:
    """
    创建Docker沙箱(仅 Docker 模式)

    Args:
        image: Docker镜像名
        name: 沙箱名称(自动生成UUID)

    Returns:
        沙箱ID字符串
    """
    sandbox_id = name or f"sandbox_{uuid.uuid4().hex[:8]}"

    if not docker_available():
        return ("沙箱不可用: 未检测到 Docker。代码/命令执行必须在 Docker 中进行(安全策略), "
                "请先启动 Docker Desktop 后重试。")

    local_img = _find_local_image() or image
    try:
        container_name = f"ik_sandbox_{sandbox_id}"
        subprocess.run(
            ["docker", "run", "-d", "--pull=never", "--rm", "--name", container_name,
             "--cap-drop=ALL", "--security-opt=no-new-privileges",
             "--network=none", local_img, "sleep", "infinity"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        )
        _sandboxes[sandbox_id] = {
            "id": sandbox_id, "container": container_name,
            "image": local_img, "mode": "docker", "status": "ready",
        }
        return sandbox_id
    except Exception as e:  # noqa: BLE001
        return f"沙箱创建失败(Docker): {e}"


def exec_in_sandbox(sandbox_id: str, code: str, language: str = "python") -> str:
    """
    在Docker沙箱中执行代码(无 Docker 则拒绝, 绝不本地直跑)

    Args:
        sandbox_id: 沙箱ID
        code: 要执行的代码
        language: python/shell

    Returns:
        执行输出
    """
    sb = _sandboxes.get(sandbox_id)
    if not sb:
        sb_id = create_sandbox()
        sb = _sandboxes.get(sb_id)

    if not sb or sb["mode"] != "docker" or not sb.get("container"):
        return ("错误: 沙箱不在 Docker 模式。安全策略要求代码执行必须在 Docker 中, "
                "请先启动 Docker 并重新创建沙箱。")
    return _exec_docker(sb["container"], code, language)


def _exec_docker(container: str, code: str, language: str) -> str:
    """Docker沙箱执行"""
    try:
        if language == "python":
            cmd = ["docker", "exec", "-i", container, "python3", "-c", code]
        elif language == "shell":
            cmd = ["docker", "exec", "-i", container, "sh", "-c", code]
        else:
            return f"不支持的语言: {language}"

        result = subprocess.run(cmd, capture_output=True, timeout=30)
        raw = result.stdout or result.stderr
        try:
            output = raw.decode("utf-8")
        except UnicodeDecodeError:
            output = raw.decode("gbk", errors="replace")
        return output[:5000] if output.strip() else "(无输出)"
    except subprocess.TimeoutExpired:
        return "错误: 执行超时(30秒)"
    except Exception as e:  # noqa: BLE001
        return f"错误: {str(e)}"


def destroy_sandbox(sandbox_id: str) -> str:
    """销毁沙箱"""
    sb = _sandboxes.pop(sandbox_id, None)
    if not sb:
        return f"沙箱不存在: {sandbox_id}"

    if sb.get("container"):
        try:
            subprocess.run(["docker", "rm", "-f", sb["container"]],
                          capture_output=True, timeout=10)
        except Exception:  # noqa: BLE001
            pass
    return f"沙箱已销毁: {sandbox_id}"


def list_sandboxes() -> str:
    """列出所有活跃沙箱"""
    if not _sandboxes:
        return "无活跃沙箱"
    return "\n".join([
        f"  {s['id']}: [{s['mode']}] {s['status']} (image: {s.get('image', '?')})"
        for s in _sandboxes.values()
    ])


# 注册工具
register_tool(
    name="create_sandbox",
    description="创建安全的 Docker 沙箱环境用于执行代码(需要 Docker)。返回沙箱ID。",
    parameters={"type": "object", "properties": {
        "image": {"type": "string", "description": "Docker镜像名", "default": "python:3.11-slim"},
        "name": {"type": "string", "description": "沙箱名称(可选)"},
    }},
    handler=create_sandbox, category="sandbox",
)

register_tool(
    name="exec_in_sandbox",
    description="在指定 Docker 沙箱中执行Python或Shell代码(需要 Docker), 隔离运行环境, 返回执行结果。",
    parameters={"type": "object", "properties": {
        "sandbox_id": {"type": "string", "description": "沙箱ID"},
        "code": {"type": "string", "description": "要执行的代码"},
        "language": {"type": "string", "enum": ["python", "shell"], "description": "语言", "default": "python"},
    }, "required": ["sandbox_id", "code"]},
    handler=exec_in_sandbox, category="sandbox",
)

register_tool(
    name="destroy_sandbox",
    description="销毁 Docker 沙箱环境, 释放资源。",
    parameters={"type": "object", "properties": {
        "sandbox_id": {"type": "string", "description": "沙箱ID"},
    }, "required": ["sandbox_id"]},
    handler=destroy_sandbox, category="sandbox",
)

register_tool(
    name="list_sandboxes",
    description="列出所有活跃沙箱及其状态。",
    parameters={"type": "object", "properties": {}},
    handler=list_sandboxes, category="sandbox",
)
