"""
PDF文件工具 — 读取、生成PDF文件
"""
import os
from agent.tools.registry import register_tool
from agent.tools.file_tools.path_utils import ensure_safe_path


def read_pdf(path: str, max_pages: int = 10) -> str:
    """读取PDF文件内容"""
    try:
        safe_path = ensure_safe_path(path)
    except ValueError as e:
        return f"错误: {str(e)}"
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(safe_path)
        texts = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            texts.append(f"--- 第{i+1}页 ---\n{page.get_text()}")
        doc.close()
        return "\n".join(texts)
    except ImportError:
        return "需要安装: pip install PyMuPDF"
    except Exception as e:
        return f"错误: {str(e)}"


def pdf_to_images(path: str, dpi: int = 200, max_pages: int = 5) -> str:
    """PDF每页转PNG图片, 返回图片路径列表"""
    try:
        safe_path = ensure_safe_path(path)
    except ValueError as e:
        return f"错误: {str(e)}"
    try:
        import fitz
        doc = fitz.open(safe_path)
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        paths = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            out = os.path.join(os.getcwd(), f"pdf_page_{i+1}.png")
            page.get_pixmap(matrix=mat).save(out)
            paths.append(out)
        doc.close()
        return f"已生成{len(paths)}张图片: {', '.join(paths)}"
    except ImportError:
        return "需要安装: pip install PyMuPDF"
    except Exception as e:
        return f"错误: {str(e)}"


def get_pdf_info(path: str) -> str:
    """获取PDF元信息(页数/标题/作者)"""
    try:
        safe_path = ensure_safe_path(path)
    except ValueError as e:
        return f"错误: {str(e)}"
    try:
        import fitz
        doc = fitz.open(safe_path)
        meta = doc.metadata or {}
        info = f"页数: {doc.page_count}\n标题: {meta.get('title', '未知')}\n作者: {meta.get('author', '未知')}\n格式: {meta.get('format', '未知')}"
        doc.close()
        return info
    except ImportError:
        return "需要安装: pip install PyMuPDF"
    except Exception as e:
        return f"错误: {str(e)}"


register_tool(name="read_pdf", description="读取PDF文件文本内容",
    parameters={"type": "object", "properties": {
        "path": {"type": "string", "description": "PDF文件路径"},
        "max_pages": {"type": "integer", "description": "最大读取页数", "default": 10},
    }, "required": ["path"]},
    handler=read_pdf, category="file")

register_tool(name="pdf_to_images", description="将PDF每页转为PNG图片",
    parameters={"type": "object", "properties": {
        "path": {"type": "string", "description": "PDF文件路径"},
        "dpi": {"type": "integer", "description": "DPI", "default": 200},
        "max_pages": {"type": "integer", "description": "最大页数", "default": 5},
    }, "required": ["path"]},
    handler=pdf_to_images, category="file")

register_tool(name="get_pdf_info", description="获取PDF文件的页数/标题/作者等元信息",
    parameters={"type": "object", "properties": {
        "path": {"type": "string", "description": "PDF文件路径"},
    }, "required": ["path"]},
    handler=get_pdf_info, category="file")
