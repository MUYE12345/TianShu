"""
Excel文件工具 — 读取、生成、修改 .xlsx 文件
"""
import os
from agent.tools.registry import register_tool
from agent.tools.file_tools.path_utils import ensure_safe_path


def read_excel(path: str, sheet: str = "", max_rows: int = 100) -> str:
    """读取Excel文件为CSV格式文本"""
    try:
        safe_path = ensure_safe_path(path)
    except ValueError as e:
        return f"错误: {str(e)}"
    try:
        import pandas as pd
        if sheet:
            df = pd.read_excel(safe_path, sheet_name=sheet, nrows=max_rows)
        else:
            df = pd.read_excel(safe_path, nrows=max_rows)
        return df.to_csv(index=False)
    except ImportError:
        return "需要安装: pip install pandas openpyxl"
    except Exception as e:
        return f"错误: {str(e)}"


def write_excel(path: str, data: str, sheet_name: str = "Sheet1") -> str:
    """写入Excel文件

    Args:
        path: 文件路径
        data: CSV格式数据(第一行为列名, 后续为数据行)
        sheet_name: 工作表名
    """
    try:
        safe_path = ensure_safe_path(path)
    except ValueError as e:
        return f"错误: {str(e)}"
    try:
        import pandas as pd
        from io import StringIO
        df = pd.read_csv(StringIO(data))
        mode = "a" if os.path.exists(safe_path) else "w"
        with pd.ExcelWriter(safe_path, engine="openpyxl", mode=mode) as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        return f"文件已保存: {safe_path} ({len(df)}行)"
    except ImportError:
        return "需要安装: pip install pandas openpyxl"
    except Exception as e:
        return f"错误: {str(e)}"


def list_sheets(path: str) -> str:
    """列出Excel文件中的所有工作表"""
    try:
        safe_path = ensure_safe_path(path)
    except ValueError as e:
        return f"错误: {str(e)}"
    try:
        import pandas as pd
        xls = pd.ExcelFile(safe_path)
        return f"工作表: {', '.join(xls.sheet_names)}"
    except Exception as e:
        return f"错误: {str(e)}"


register_tool(name="read_excel", description="读取Excel(.xlsx)文件内容, 返回CSV格式文本",
    parameters={"type": "object", "properties": {
        "path": {"type": "string", "description": "文件路径"},
        "sheet": {"type": "string", "description": "工作表名(可选)", "default": ""},
        "max_rows": {"type": "integer", "description": "最大行数", "default": 100},
    }, "required": ["path"]},
    handler=read_excel, category="file")

register_tool(name="write_excel", description="创建或修改Excel(.xlsx)文件, 输入CSV格式数据",
    parameters={"type": "object", "properties": {
        "path": {"type": "string", "description": "文件路径"},
        "data": {"type": "string", "description": "CSV格式数据(首行为列名)"},
        "sheet_name": {"type": "string", "description": "工作表名", "default": "Sheet1"},
    }, "required": ["path", "data"]},
    handler=write_excel, category="file")

register_tool(name="list_sheets", description="列出Excel文件的所有工作表",
    parameters={"type": "object", "properties": {
        "path": {"type": "string", "description": "文件路径"},
    }, "required": ["path"]},
    handler=list_sheets, category="file")
