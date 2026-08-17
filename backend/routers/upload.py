"""统一上传路由 — 工具/MCP/技能 上传/注册/删除"""
import os
import re
import json
import zipfile
import tempfile
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends

from backend.config import DATA_DIR
from backend.core.security import get_current_user

router = APIRouter()

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(DATA_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ── 安全辅助 ─────────────────────────────────────────────

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_\-\.]+$")


def _safe_name(name: str, field: str = "名称") -> str:
    """校验名称只含字母/数字/_-., 拒绝路径分隔符与 '..' (防目录穿越)"""
    name = (name or "").strip()
    if not name or name in (".", "..") or not _SAFE_NAME_RE.match(name):
        raise HTTPException(400, detail=f"{field}不合法: 仅允许字母/数字/_-., 不能含路径字符")
    return name


def _safe_extract(zf: zipfile.ZipFile, target: str):
    """zip-slip 防护: 拒绝包含 '..' / 绝对路径 / 盘符的压缩项, 再安全解压"""
    for member in zf.namelist():
        norm = member.replace("\\", "/")
        if norm.startswith("/") or (len(norm) > 1 and norm[1] == ":"):
            raise HTTPException(400, detail=f"压缩包包含非法绝对路径项: {member}")
        parts = [p for p in norm.split("/") if p not in ("", ".")]
        if any(p == ".." for p in parts):
            raise HTTPException(400, detail=f"压缩包包含非法路径项(..): {member}")
    zf.extractall(target)


# ═══════════════════════════════════════
# 工具上传 — Python 脚本
# ═══════════════════════════════════════

def _build_schema_from_fn(fn) -> dict:
    """从函数签名自动构建 JSON Schema"""
    import inspect
    sig = inspect.signature(fn)
    properties = {}
    required = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        # 尝试获取类型注解
        param_type = "string"
        if param.annotation != inspect.Parameter.empty:
            type_map = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "list": "array", "dict": "object"}
            type_name = getattr(param.annotation, "__name__", str(param.annotation))
            param_type = type_map.get(type_name, "string")
        properties[name] = {"type": param_type, "description": f"参数 {name}"}
        if param.default == inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def _register_from_ns(ns: dict, tool_name: str, description: str = "") -> int:
    """从命名空间中注册可调用工具"""
    import inspect
    from agent.tools.registry import register_tool
    registered = 0
    for fn_name, fn in ns.items():
        if not callable(fn) or fn_name.startswith("_"):
            continue
        # 跳过内置类型
        if isinstance(fn, (type, type(print), type(len))):
            continue
        try:
            schema = _build_schema_from_fn(fn)
            fn_desc = description or f"用户上传工具: {tool_name}.{fn_name}"
            doc = getattr(fn, "__doc__", "") or ""
            if doc:
                fn_desc += f" - {doc.strip()[:100]}"
            register_tool(
                name=f"{tool_name}_{fn_name}",
                description=fn_desc,
                parameters=schema,
                handler=fn,
                category="user_uploaded",
            )
            registered += 1
        except Exception:
            pass
    return registered


@router.post("/tools")
async def upload_tool(current_user = Depends(get_current_user),
                      file: UploadFile = File(...), name: str = Form("")):
    """上传工具包（.zip 含多个 .py + CLAUDE.md，或单 .py 文件）"""
    filename = file.filename or ""
    content = await file.read()

    if filename.endswith(".zip"):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, filename)
            with open(zip_path, "wb") as f:
                f.write(content)
            with zipfile.ZipFile(zip_path, "r") as zf:
                _safe_extract(zf, tmp)

            desc = ""
            claude_path = os.path.join(tmp, "CLAUDE.md")
            if os.path.exists(claude_path):
                with open(claude_path, encoding="utf-8") as f:
                    desc = f.read()[:300]

            py_files = [os.path.join(r, f) for r, _, fs in os.walk(tmp) for f in fs if f.endswith(".py")]
            if not py_files:
                raise HTTPException(400, "ZIP 中未找到 .py 文件")

            tool_name = _safe_name(name or filename.replace(".zip", ""), "工具名")
            save_dir = UPLOAD_DIR / "tools" / tool_name
            shutil.rmtree(save_dir, ignore_errors=True)
            shutil.copytree(tmp, save_dir)

            total = 0
            for py_path in py_files:
                with open(py_path, encoding="utf-8") as f:
                    try:
                        ns = {}
                        exec(compile(f.read(), py_path, "exec"), ns)
                        total += _register_from_ns(ns, tool_name, desc)
                    except Exception:
                        pass
            return {"message": f"工具包 {tool_name} 已安装，注册 {total} 个工具", "name": tool_name}

    elif filename.endswith(".py"):
        tool_name = _safe_name(name or filename.replace(".py", ""), "工具名")
        save_dir = UPLOAD_DIR / "tools" / tool_name
        save_dir.mkdir(parents=True, exist_ok=True)
        (save_dir / filename).write_bytes(content)

        ns = {}
        exec(compile(content, filename, "exec"), ns)
        total = _register_from_ns(ns, tool_name)
        return {"message": f"工具 {tool_name} 上传成功，注册 {total} 个工具", "name": tool_name}

    else:
        raise HTTPException(400, "仅支持 .py 或 .zip 文件")


# ═══════════════════════════════════════
# MCP 上传 — stdio/http/sse 配置
# ═══════════════════════════════════════

@router.post("/mcp")
async def upload_mcp(current_user = Depends(get_current_user), body: dict = None):
    """注册 MCP 服务器连接"""
    mcp_type = body.get("type", "stdio")
    if mcp_type not in ("stdio", "http", "sse"):
        raise HTTPException(400, "type 必须为 stdio/http/sse")

    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(400, "name 必填")

    entry = {
        "name": name,
        "type": mcp_type,
        "enabled": True,
        "status": "unknown",
    }

    if mcp_type == "stdio":
        cmd = body.get("command", "").strip()
        if not cmd:
            raise HTTPException(400, "stdio 模式需要 command")
        entry["command"] = cmd
        entry["args"] = body.get("args", [])
        entry["env"] = body.get("env", {})

    elif mcp_type in ("http", "sse"):
        url = body.get("url", "").strip()
        if not url:
            raise HTTPException(400, f"{mcp_type} 模式需要 url")
        entry["url"] = url

    # 保存到 mcp_service
    try:
        from agent.mcp_service import mcp_service
        mcp_service.register_server(name, entry)
    except Exception as e:
        raise HTTPException(500, f"MCP 注册失败: {e}")

    return {"message": f"MCP 服务器 {name} 已注册", "entry": entry}


# ═══════════════════════════════════════
# 技能上传 — ZIP/SKILL.md
# ═══════════════════════════════════════

@router.post("/skills")
async def upload_skill(current_user = Depends(get_current_user),
                       file: UploadFile = File(...)):
    """上传技能包（.md / .zip）"""
    filename = file.filename or ""
    content = await file.read()

    if filename.endswith(".zip"):
        # 解压 ZIP，查找 SKILL.md
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, filename)
            with open(zip_path, "wb") as f:
                f.write(content)
            with zipfile.ZipFile(zip_path, "r") as zf:
                _safe_extract(zf, tmp)

            # 查找 SKILL.md 或 CLAUDE.md
            skill_md = None
            for root, _, files in os.walk(tmp):
                for f in files:
                    if f.lower() in ("skill.md", "claude.md"):
                        skill_md = os.path.join(root, f)
                        break
                if skill_md:
                    break

            if not skill_md:
                raise HTTPException(400, "ZIP 中未找到 SKILL.md 或 CLAUDE.md")

            with open(skill_md, encoding="utf-8") as f:
                md_content = f.read()

            # 提取元数据
            skill_name = _safe_name(
                _parse_skill_name(md_content) or os.path.splitext(filename)[0], "技能名")

            # 安装到 skills 目录: 复制整个技能包(scripts/references/assets + SKILL.md),
            # 而不是只写 SKILL.md —— 保证目录是完整的技能包
            skill_md_dir = os.path.dirname(skill_md)
            skills_dir = Path("agent/skills") / skill_name
            if skills_dir.exists():
                shutil.rmtree(skills_dir, ignore_errors=True)
            shutil.copytree(skill_md_dir, skills_dir, dirs_exist_ok=True)

    elif filename.endswith(".md"):
        md_content = content.decode("utf-8")
        skill_name = _safe_name(
            _parse_skill_name(md_content) or filename.replace(".md", ""), "技能名")
        skills_dir = Path("agent/skills") / skill_name
        skills_dir.mkdir(parents=True, exist_ok=True)
        (skills_dir / "SKILL.md").write_text(md_content, encoding="utf-8")

    else:
        raise HTTPException(400, "仅支持 .md 或 .zip 文件")

    # 重载 skill_manager, 让新技能立即生效(不必重启后端)
    try:
        from agent.skills.skill_manager import skill_manager
        skill_manager.reload()
    except Exception:  # noqa: BLE001
        pass
    return {"message": f"技能 {skill_name} 安装成功", "name": skill_name}


def _parse_skill_name(markdown: str) -> str | None:
    """从 YAML frontmatter 或首行提取技能名称"""
    import re
    # 尝试 YAML frontmatter
    m = re.search(r"^---\s*\nname:\s*(.+)\n", markdown)
    if m:
        return m.group(1).strip()
    # 回退: 取第一行标题
    first = markdown.strip().split("\n")[0]
    return first.replace("#", "").strip()[:40] or None


# ═══════════════════════════════════════
# 删除 — 真实移除已上传资源
# ═══════════════════════════════════════

@router.delete("/tools/{tool_name}")
def delete_tool(tool_name: str, current_user = Depends(get_current_user)):
    """删除上传的工具: 反注册其 handler + 删除保存的文件。"""
    name = _safe_name(tool_name, "工具名")
    # 反注册注册表中所有以 {name}_ 开头的工具
    from agent.tools.registry import _TOOL_REGISTRY, unregister_tool
    removed = [k for k in list(_TOOL_REGISTRY.keys()) if k == name or k.startswith(f"{name}_")]
    for k in removed:
        unregister_tool(k)
    # 删除保存的源文件目录
    save_dir = UPLOAD_DIR / "tools" / name
    if save_dir.exists():
        shutil.rmtree(save_dir, ignore_errors=True)
    return {"message": f"工具 {name} 已删除", "removed": removed}


# 内置技能目录, 不可删除(由代码自带)
_BUILTIN_SKILL_DIRS = {"current-news", "daily-news", "paper-analyzer", "skill-creator", "wiki-creator"}


@router.delete("/skills/{skill_name}")
def delete_skill(skill_name: str, current_user = Depends(get_current_user)):
    """删除上传/社区技能: 移除整个技能包目录(scripts/references/assets/SKILL.md)并重载。"""
    name = _safe_name(skill_name, "技能名")
    if name in _BUILTIN_SKILL_DIRS:
        raise HTTPException(400, detail=f"内置技能 {name} 不可删除")
    from agent.skills.skill_manager import skill_manager
    skills_dir = Path("agent/skills") / name
    if not skills_dir.exists():
        raise HTTPException(404, detail=f"技能不存在: {name}")
    shutil.rmtree(skills_dir, ignore_errors=True)
    skill_manager.reload()
    return {"message": f"技能包 {name} 已删除(整个目录)"}


@router.delete("/mcp/{name}")
def delete_mcp_server(name: str, current_user = Depends(get_current_user)):
    """删除已注册的外部 MCP 服务器(反注册其工具 + 删配置)。"""
    if not (name or "").strip():
        raise HTTPException(400, detail="服务器名不能为空")
    from agent.mcp_service import mcp_service
    ok = mcp_service.remove_server(name.strip())
    if not ok:
        raise HTTPException(404, detail=f"MCP 服务器不存在: {name}")
    return {"message": f"MCP 服务器 {name} 已删除"}
