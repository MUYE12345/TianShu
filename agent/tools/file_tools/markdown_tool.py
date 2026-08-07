"""
Markdown文件工具
"""
import os
from agent.tools.registry import register_tool
from agent.tools.file_tools.path_utils import ensure_safe_path


def read_md(path: str) -> str:
    """读取Markdown文件"""
    try:
        safe_path = ensure_safe_path(path)
    except ValueError as e:
        return f"错误: {str(e)}"
    if not os.path.exists(safe_path):
        return f"文件不存在: {path}"
    with open(safe_path, "r", encoding="utf-8") as f:
        return f.read()


def write_md(path: str, content: str) -> str:
    """写入Markdown文件"""
    try:
        safe_path = ensure_safe_path(path)
    except ValueError as e:
        return f"错误: {str(e)}"
    os.makedirs(os.path.dirname(safe_path) or ".", exist_ok=True)
    with open(safe_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"文件已保存: {safe_path}"


register_tool(name="read_md", description="读取Markdown(.md)文件内容",
    parameters={"type": "object", "properties": {
        "path": {"type": "string", "description": "文件路径"}
    }, "required": ["path"]},
    handler=read_md, category="file")

register_tool(name="write_md", description="写入Markdown(.md)文件",
    parameters={"type": "object", "properties": {
        "path": {"type": "string", "description": "文件路径"},
        "content": {"type": "string", "description": "文件内容"}
    }, "required": ["path", "content"]},
    handler=write_md, category="file")
