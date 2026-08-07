"""
路径安全检查工具
提供 ensure_safe_path 函数，防止路径遍历攻击
"""
import os


def ensure_safe_path(path: str, project_root: str = None) -> str:
    """验证并规范化路径，防止路径遍历攻击

    拒绝包含 '..' 的路径，以及指向项目目录之外的绝对路径。

    Args:
        path: 要检查的文件路径（相对或绝对）
        project_root: 项目根目录，默认使用当前工作目录

    Returns:
        规范化后的安全绝对路径

    Raises:
        ValueError: 如果路径不安全
    """
    if not path:
        raise ValueError("路径不能为空")

    if project_root is None:
        project_root = os.getcwd()

    project_root = os.path.abspath(project_root)

    # 检查是否包含路径遍历（..）
    norm_path = path.replace("/", os.sep).replace("\\", os.sep)
    parts = norm_path.split(os.sep)
    if ".." in parts:
        raise ValueError(f"路径包含 '..' 遍历操作，已拒绝: {path}")

    # 解析为绝对路径
    abs_path = os.path.abspath(path)

    # 检查是否在项目根目录内
    prefix = project_root.rstrip(os.sep) + os.sep
    if abs_path != project_root and not abs_path.startswith(prefix):
        raise ValueError(f"路径指向项目目录之外，已拒绝: {path}")

    return abs_path
