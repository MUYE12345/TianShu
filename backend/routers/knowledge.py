"""
知识库路由 — 源头→提问→沉淀 三层架构（PRD MVP）
"""
import os
import re
import json
import uuid
import asyncio
import random
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

import threading

from backend.config import DATA_DIR as APP_DATA_DIR, settings
from backend.services.knowledge_parser import extract_text, is_previewable
from backend.services.kb_rag import kb_rag
from backend.services.kg_rag import kg_rag

router = APIRouter()

DATA_DIR = APP_DATA_DIR / "knowledge"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 插画封面 ID（前端映射为 SVG 插画；旧数据可能存的是色值，前端兜底渲染）
COVERS = ["cover-1", "cover-2", "cover-3", "cover-4", "cover-5", "cover-6"]

# PRD 3.2.4：支持上传格式白名单
ALLOWED_EXTS = {"pdf", "docx", "doc", "xls", "xlsx", "ppt", "pptx", "md", "txt",
                "markdown", "csv", "json", "html", "htm"}

# ── 内存存储（后续可改为数据库） ──
_kbs: dict = {}  # id -> kb


def _kb_path(kid: str) -> Path:
    p = DATA_DIR / kid
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_all():
    for d in DATA_DIR.iterdir():
        if d.is_dir():
            meta_file = d / "meta.json"
            if meta_file.exists():
                try:
                    # 必须显式 UTF-8：Windows 默认 GBK 解码中文会抛异常
                    kb = json.loads(meta_file.read_text(encoding="utf-8"))
                    _kbs[kb["id"]] = kb
                except: pass


def _save_kb(kb: dict):
    p = _kb_path(kb["id"])
    # 必须显式 UTF-8：Windows 默认 GBK，PDF 提取文本中的 ∗ • 等字符会 UnicodeEncodeError
    (p / "meta.json").write_text(json.dumps(kb, ensure_ascii=False, default=str), encoding="utf-8")


_load_all()


# ── API ──

@router.get("/notebooks")
def list_kbs():
    """获取所有知识库"""
    return {"items": list(_kbs.values()), "total": len(_kbs)}


@router.post("/notebooks")
def create_kb(body: dict):
    """创建知识库"""
    kid = uuid.uuid4().hex[:12]
    import random
    kb = {
        "id": kid,
        "title": body.get("title", "未命名"),
        "description": body.get("description", ""),
        "cover": body.get("cover", random.choice(COVERS)),
        "source_count": 0,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    _kbs[kid] = kb
    _save_kb(kb)
    return kb


@router.put("/notebooks/{kid}")
def update_kb(kid: str, body: dict):
    """更新知识库"""
    if kid not in _kbs:
        raise HTTPException(404)
    for k in ("title", "description", "cover"):
        if k in body:
            _kbs[kid][k] = body[k]
    _kbs[kid]["updated_at"] = datetime.now().isoformat()
    _save_kb(_kbs[kid])
    return _kbs[kid]


@router.delete("/notebooks/{kid}")
def delete_kb(kid: str):
    """删除知识库"""
    if kid not in _kbs:
        raise HTTPException(404)
    import shutil
    shutil.rmtree(_kb_path(kid), ignore_errors=True)
    _kbs.pop(kid, None)
    # 清理 RAG 索引 + 实体图(独立于知识库目录)
    kb_rag.drop_index(kid)
    kg_rag.clear(kid)
    return {"message": "已删除"}


def _register_source(kid: str, source: dict):
    sources = _kbs[kid].get("sources", [])
    sources.append(source)
    _kbs[kid]["sources"] = sources
    _kbs[kid]["source_count"] = len(sources)
    _kbs[kid]["updated_at"] = datetime.now().isoformat()
    _save_kb(_kbs[kid])


def _spawn_graph_build(kid: str, source_ids: list):
    """后台线程构建轻量实体图, 不阻塞上传/解析响应。失败隔离(仅影响图扩展)。"""
    if not settings.GRAPH_ENABLED:
        return
    try:
        t = threading.Thread(target=kg_rag.build_graph_if_needed,
                             args=(kid, source_ids), daemon=True)
        t.start()
    except Exception as e:  # noqa: BLE001
        print(f"[KB] 启动构图失败 {kid}: {e}")


def _rebuild_index(kid: str):
    """按当前已解析来源重建 RAG 索引(kb_rag.ensure_index 幂等, 来源集合变化才重建)。

    解析成功后由 _parse_source / add_text_source / delete_source 调用。
    优先读上传时的 .txt 缓存; 缺失(如粘贴文本)则回退读原始文件并 extract_text。
    索引完成后后台异步构建实体图。
    """
    try:
        sources = _kbs.get(kid, {}).get("sources", [])
        items = []
        for s in sources:
            if s.get("status") != "parsed":
                continue
            text = ""
            txt_path = _kb_path(kid) / "sources" / f"{s['id']}.txt"
            if txt_path.exists():
                try:
                    text = txt_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    text = ""
            if not text.strip():
                # 回退: 直接读原始文件(粘贴文本未生成 .txt 缓存)
                try:
                    raw = _source_filepath(kid, s)
                    if raw.exists():
                        text, _err = extract_text(raw, s.get("ext", ""))
                except Exception:
                    text = ""
            if text.strip():
                items.append({"id": s["id"], "filename": s["filename"], "text": text})
        if items:
            kb_rag.ensure_index(kid, items)
            _spawn_graph_build(kid, [i["id"] for i in items])
    except Exception as e:  # noqa: BLE001
        print(f"[KB] 重建索引失败 {kid}: {e}")


def _parse_source(kid: str, fid: str):
    """后台解析来源：提取纯文本供检索与预览，完成后置 parsed / failed"""
    if kid not in _kbs:
        return
    source = next((s for s in _kbs[kid].get("sources", []) if s["id"] == fid), None)
    if not source:
        return
    filepath = _source_filepath(kid, source)
    try:
        try:
            text, parse_err = extract_text(filepath, source.get("ext", ""))
        except Exception as e:  # noqa: BLE001
            text, parse_err = "", f"解析失败: {type(e).__name__}: {e}"
        if parse_err:
            source["status"] = "failed"
            source["parse_error"] = parse_err
        else:
            source["status"] = "parsed"
            source["text_preview"] = text[:3000]
            # 缓存提取文本，供对话/生成复用
            txt_path = _kb_path(kid) / "sources" / f"{fid}.txt"
            try:
                txt_path.write_text(text[:100000], encoding="utf-8", errors="replace")
            except Exception:
                pass
            # RAG 索引: 解析完成后重建(幂等)
            _rebuild_index(kid)
        _save_kb(_kbs[kid])
    except Exception as e:  # noqa: BLE001
        # 兜底：任何未预期异常都不让来源卡在"解析中"
        try:
            source["status"] = "failed"
            source["parse_error"] = f"解析失败: {type(e).__name__}: {e}"
            _save_kb(_kbs[kid])
        except Exception:
            pass


@router.post("/notebooks/{kid}/sources")
async def upload_source(kid: str, background_tasks: BackgroundTasks,
                        file: UploadFile = File(...)):
    """上传来源文档：格式白名单 + 50MB 限制；落盘后立即返回，后台异步解析"""
    if kid not in _kbs:
        raise HTTPException(404)
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, f"不支持的文件格式 .{ext}，支持：pdf/docx/doc/xls/xlsx/ppt/pptx/md/txt 等")

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"文件超过 {settings.MAX_UPLOAD_SIZE // (1024 * 1024)}MB 大小限制")

    fid = uuid.uuid4().hex[:8]
    save_dir = _kb_path(kid) / "sources"
    save_dir.mkdir(exist_ok=True)
    (save_dir / f"{fid}_{filename}").write_bytes(content)

    source = {
        "id": fid,
        "filename": filename,
        "ext": ext,
        "size": len(content),
        "status": "parsing",          # 解析中 → 后台解析完成后置为 parsed / failed
        "parse_error": None,
        "previewable": is_previewable(ext),
        "text_preview": "",
        "created_at": datetime.now().isoformat(),
    }
    _register_source(kid, source)
    background_tasks.add_task(_parse_source, kid, fid)
    return source


class TextSourceBody(BaseModel):
    title: str = ""
    content: str = ""


@router.post("/notebooks/{kid}/sources/text")
def add_text_source(kid: str, body: TextSourceBody):
    """粘贴文本作为来源（设计稿「粘贴文本」tab）"""
    if kid not in _kbs:
        raise HTTPException(404)
    text = (body.content or "").strip()
    if not text:
        raise HTTPException(400, "文本内容不能为空")
    if len(text.encode("utf-8")) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, "文本超过大小限制")

    fid = uuid.uuid4().hex[:8]
    title = (body.title or "").strip() or f"粘贴文本_{datetime.now().strftime('%m%d_%H%M')}"
    filename = f"{title}.md"
    save_dir = _kb_path(kid) / "sources"
    save_dir.mkdir(exist_ok=True)
    (save_dir / f"{fid}_{filename}").write_text(text, encoding="utf-8")

    source = {
        "id": fid,
        "filename": filename,
        "ext": "md",
        "size": len(text.encode("utf-8")),
        "status": "parsed",
        "parse_error": None,
        "previewable": True,
        "text_preview": text[:3000],
        "created_at": datetime.now().isoformat(),
    }
    _register_source(kid, source)
    # 粘贴文本已即时可检索, 立即建索引
    _rebuild_index(kid)
    return source


@router.get("/notebooks/{kid}/sources")
def list_sources(kid: str):
    """获取知识库来源列表"""
    if kid not in _kbs:
        raise HTTPException(404)
    return {"items": _kbs[kid].get("sources", [])}


@router.delete("/notebooks/{kid}/sources/{sid}")
def delete_source(kid: str, sid: str):
    """删除来源"""
    if kid not in _kbs:
        raise HTTPException(404)
    sources = _kbs[kid].get("sources", [])
    _kbs[kid]["sources"] = [s for s in sources if s["id"] != sid]
    _kbs[kid]["source_count"] = len(_kbs[kid]["sources"])
    _save_kb(_kbs[kid])
    # 来源集合变化, 重建 RAG 索引(保留剩余来源的块)
    _rebuild_index(kid)
    return {"message": "已删除"}


def _find_source(kid: str, sid: str) -> dict:
    """按 id 查找来源"""
    if kid not in _kbs:
        raise HTTPException(404, "知识库不存在")
    s = next((s for s in _kbs[kid].get("sources", []) if s["id"] == sid), None)
    if not s:
        raise HTTPException(404, "来源不存在")
    return s


def _source_filepath(kid: str, s: dict) -> Path:
    """来源原始文件路径（防御路径穿越）"""
    filename = Path(s["filename"]).name  # 只取文件名，丢弃可能的路径
    return _kb_path(kid) / "sources" / f"{s['id']}_{filename}"


@router.get("/notebooks/{kid}/sources/{sid}/preview")
def preview_source(kid: str, sid: str):
    """在线预览来源文件：pdf/html 直接返回文件（iframe 渲染），文本类返回提取文本"""
    s = _find_source(kid, sid)
    fp = _source_filepath(kid, s)
    if not fp.exists():
        raise HTTPException(404, "文件已丢失")

    ext = (s.get("ext") or "").lower().lstrip(".")

    # iframe 可直接渲染的格式
    if ext in ("pdf", "html", "htm"):
        return FileResponse(fp, media_type="application/pdf" if ext == "pdf" else "text/html; charset=utf-8")

    if ext in ("txt", "md", "markdown", "csv", "json"):
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"读取失败: {e}")
        return PlainTextResponse(text)

    if ext == "docx":
        text, err = extract_text(fp, ext)
        if err:
            raise HTTPException(400, err)
        return PlainTextResponse(text)

    raise HTTPException(400, "该格式暂不支持在线预览")


@router.get("/notebooks/{kid}/sources/{sid}/download")
def download_source(kid: str, sid: str):
    """下载来源原件"""
    s = _find_source(kid, sid)
    fp = _source_filepath(kid, s)
    if not fp.exists():
        raise HTTPException(404, "文件已丢失")
    safe_name = Path(s["filename"]).name
    # FileResponse 会根据 filename 自动生成 RFC5987 编码的 Content-Disposition，
    # 避免手工拼 header 导致中文文件名 latin-1 编码失败
    return FileResponse(fp, media_type="application/octet-stream", filename=safe_name)


# ── 对话历史（磁盘持久化：{kid}/chats/{chatId}.json） ──

def _chats_dir(kid: str) -> Path:
    p = _kb_path(kid) / "chats"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_chat(kid: str, cid: str) -> dict | None:
    fp = _chats_dir(kid) / f"{cid}.json"
    if not fp.exists():
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_chat(kid: str, chat: dict):
    _chats_dir(kid).mkdir(parents=True, exist_ok=True)
    fp = _chats_dir(kid) / f"{chat['id']}.json"
    fp.write_text(json.dumps(chat, ensure_ascii=False, default=str), encoding="utf-8")


def _create_chat(kid: str, title: str = "") -> dict:
    now = datetime.now().isoformat()
    chat = {
        "id": uuid.uuid4().hex[:12],
        "title": title or "新对话",
        "created_at": now,
        "updated_at": now,
        "messages": [],
        "source_ids": [],
    }
    _save_chat(kid, chat)
    return chat


@router.get("/notebooks/{kid}/chats")
def list_chats(kid: str):
    """获取知识库对话历史摘要（不含正文，按更新时间倒序）"""
    items = []
    for fp in _chats_dir(kid).glob("*.json"):
        try:
            c = json.loads(fp.read_text(encoding="utf-8"))
            items.append({
                "id": c["id"], "title": c.get("title", "新对话"),
                "created_at": c.get("created_at"), "updated_at": c.get("updated_at"),
                "message_count": len(c.get("messages", [])),
            })
        except Exception:
            continue
    items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return {"items": items, "total": len(items)}


@router.post("/notebooks/{kid}/chats")
def create_chat(kid: str, body: dict = None):
    """创建对话会话"""
    if kid not in _kbs:
        raise HTTPException(404, "知识库不存在")
    body = body or {}
    chat = _create_chat(kid, (body.get("title") or "").strip())
    return chat


@router.get("/notebooks/{kid}/chats/{cid}")
def get_chat(kid: str, cid: str):
    """获取单个会话完整消息"""
    c = _load_chat(kid, cid)
    if not c:
        raise HTTPException(404, "会话不存在")
    return c


@router.delete("/notebooks/{kid}/chats/{cid}")
def delete_chat(kid: str, cid: str):
    """删除对话会话"""
    fp = _chats_dir(kid) / f"{cid}.json"
    if not fp.exists():
        raise HTTPException(404, "会话不存在")
    fp.unlink(missing_ok=True)
    return {"message": "已删除"}


class ChatRequest(BaseModel):
    messages: list
    sourceIds: list[str] | None = None
    chatId: str | None = None


def _build_context(kid: str, source_ids: list[str] | None, limit: int = 5, max_chars: int = 2000) -> tuple[str, list]:
    """构建 RAG/生成上下文：优先用上传时缓存的提取文本，否则回退读原始文件。

    返回 (context_text, selected_sources)。
    """
    context_parts = []
    selected = []
    if kid in _kbs:
        sources = _kbs[kid].get("sources", [])
        # 过滤：来源必须已解析成功才进上下文
        selected = [s for s in sources
                    if (not source_ids or s["id"] in source_ids) and s.get("status") == "parsed"]
        selected = selected[:limit]
        for s in selected:
            # 优先读取缓存的完整提取文本（最多 max_chars），回退 text_preview
            text = ""
            txt_path = _kb_path(kid) / "sources" / f"{s['id']}.txt"
            if txt_path.exists():
                try:
                    text = txt_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    text = ""
            if not text:
                text = (s.get("text_preview") or "").strip()
            if text:
                context_parts.append(f"[{s['filename']}]\n{text[:max_chars]}")
    context = "\n\n".join(context_parts) if context_parts else "（暂无文档内容）"
    return context, selected


def _format_retrieved(chunks: list) -> str:
    """把检索到的块拼成带编号的上下文文本。"""
    parts = []
    for i, c in enumerate(chunks, 1):
        head = f"[{i}] 文件: {c.get('filename', '')}"
        if c.get("section"):
            head += f" | 章节: {c['section']}"
        parts.append(f"{head}\n{c.get('text', '')[:800]}")
    return "\n\n".join(parts)


def _prepare_chat(kid: str, req: ChatRequest) -> tuple:
    """构建知识库问答的会话 + 压缩历史。返回 (chat, user_msg, history_prefix)。

    检索/评分/综合由 rag_agent.agentic_chat 负责。
    """
    from backend.core.context_compressor import ContextCompressor

    user_msg = req.messages[-1]["content"] if req.messages else ""

    chat = None
    if req.chatId:
        chat = _load_chat(kid, req.chatId)
    if chat is None:
        chat = _create_chat(kid, user_msg[:30] or "新对话")
        chat["title"] = user_msg[:30] or "新对话"

    # 多轮: 压缩历史(滑窗+启发式摘要), 供改写/综合阶段注入
    history_prefix = ""
    hist = [m for m in chat.get("messages", [])
            if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")]
    if hist:
        try:
            compressor = ContextCompressor()
            compressed = compressor.compress_messages(hist[-12:], target_tokens=1500, window_size=8)
            text = "\n".join(f"{m.get('role','')}: {m.get('content','')}"
                             for m in compressed if m.get("content"))
            if text.strip():
                history_prefix = f"## 对话历史(供上下文参考)\n{text[:1200]}"
        except Exception:
            history_prefix = ""
    return chat, user_msg, history_prefix


@router.post("/notebooks/{kid}/chat")
async def chat_kb(kid: str, req: ChatRequest):
    """
    知识库问答（分块 RAG，SSE 流式，支持会话历史持久化 + 多轮压缩）。

    事件流:
      event: meta      data: {type:"meta", chat_id, citations}
      event: agent     data: {type:"agent", stage: rewrite|graph|grade|reflect, ...}
      event: citations data: {type:"citations", citations:[...]}   ← 检索后块级引用
      event: token     data: {type:"token", text}
      event: done      data: {type:"done", final_response, citations}
      event: error     data: {type:"error", message}
    """
    from fastapi.responses import StreamingResponse
    from backend.services.rag_agent import agentic_chat

    chat, user_msg, history_prefix = _prepare_chat(kid, req)

    async def event_stream():
        nonlocal chat
        reply = ""
        try:
            async for ev in agentic_chat(kid, req, chat, history_prefix):
                if ev["type"] == "done":
                    reply = ev.get("final_response", "") or reply
                elif ev["type"] == "error":
                    reply = ev.get("message", "") or reply
                yield f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            reply = f"（AI 回复暂不可用: {e}）"
            yield f"event: error\ndata: {json.dumps({'type': 'error', 'message': reply}, ensure_ascii=False)}\n\n"
        # 持久化(失败不阻断)
        try:
            chat["messages"].append({"role": "user", "content": user_msg})
            chat["messages"].append({"role": "assistant", "content": reply or "（无回复）"})
            chat["updated_at"] = datetime.now().isoformat()
            chat["source_ids"] = req.sourceIds or []
            _save_chat(kid, chat)
        except Exception:
            pass

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


# ── 产出（产物）：{kid}/artifacts/{aid}_{kind}.{ext} + meta.json ──

_GENERATION_EXT = {"html": "html", "mindmap": "md", "ppt": "md", "brief": "md",
                   "timeline": "json"}

GENERATION_LABEL = {
    "html": "网页报告",
    "mindmap": "思维导图",
    "ppt": "PPT 演示",
    "brief": "简报",
    "timeline": "时间轴",
}

# PRD 3.2.7.3：思维导图 4 种类型
MINDMAP_TYPES = ["概括", "时间线", "对比", "结构"]

# 网页风格 / PPT 模板（设计稿生成面板的风格卡片）
HTML_STYLES = ["简约白", "商务米色", "科技蓝紫", "深色专业"]
PPT_TEMPLATES = ["简约白", "商务深色", "科技渐变"]


def _artifacts_dir(kid: str) -> Path:
    p = _kb_path(kid) / "artifacts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_artifacts(kid: str) -> list:
    meta = _artifacts_dir(kid) / "meta.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_artifacts(kid: str, items: list):
    (_artifacts_dir(kid) / "meta.json").write_text(
        json.dumps(items, ensure_ascii=False, default=str), encoding="utf-8")


def _build_generation_prompt(kind: str, kb_title: str, context: str,
                             instruction: str, mindmap_type: str,
                             style: str = "", template: str = "") -> str:
    inst = instruction.strip() if instruction else ""
    base = f"你是知识库内容分析专家，仅基于以下资料回答，不要编造。\n\n知识库《{kb_title}》的资料内容：\n{context}\n\n"
    if kind == "html":
        style_hint = f"视觉风格：{style}。" if style in HTML_STYLES else ""
        return base + (
            "请生成一份完整、可直接保存为 .html 的独立研究报告（内联 CSS，含目录、章节、结论）。"
            f"{style_hint}"
            f"标题为《{kb_title}研究报告》。只输出 HTML 代码本身。\n"
            + (f"补充要求：{inst}" if inst else ""))
    if kind == "mindmap":
        types = {"概括": "按主题概括", "时间线": "按时间线", "对比": "按对比维度",
                 "结构": "按层级结构"}
        t = types.get(mindmap_type, "按主题概括")
        return base + (
            f"请用 Markdown 的一级/二级/三级标题层级描述一张思维导图（{t}），"
            f"根节点为《{kb_title}》，分支用 ## / ### 表示。只输出 Markdown。\n"
            + (f"补充要求：{inst}" if inst else ""))
    if kind == "ppt":
        tpl_hint = f"模板风格：{template}。" if template in PPT_TEMPLATES else ""
        return base + (
            "请用 Markdown 写一套演示文稿，每页以一级标题 `# ` 开头作为页标题，"
            f"页内用 ## / ### / - 组织要点，共 8~12 页。{tpl_hint}只输出 Markdown。\n"
            + (f"补充要求：{inst}" if inst else ""))
    if kind == "brief":
        return base + (
            "请输出一份业务简报，Markdown 格式，包含：概述、核心要点(N条)、数据/事实、行动建议、风险。"
            "全文不超过 800 字。只输出 Markdown。\n"
            + (f"补充要求：{inst}" if inst else ""))
    if kind == "timeline":
        return base + (
            "请根据资料中的时间线索，划分不同时间节点，输出 JSON 数组，"
            '每个元素为 {"date": "时间（如 2026-04 或 2026-04-15）", "title": "节点标题", '
            '"detail": "一句话说明"}，按时间升序，5~15 个节点。只输出 JSON 数组本身。\n'
            + (f"补充要求：{inst}" if inst else ""))
    return base


@router.post("/notebooks/{kid}/generate")
def generate_artifact(kid: str, body: dict):
    """生成知识产出（html / mindmap / ppt / brief）"""
    from backend.core.model_config import model_manager
    from backend.config import settings

    if kid not in _kbs:
        raise HTTPException(404, "知识库不存在")

    kind = body.get("kind", "")
    if kind not in _GENERATION_EXT:
        raise HTTPException(400, f"不支持的产出类型: {kind}")

    context, _selected = _build_context(kid, body.get("source_ids"), limit=5, max_chars=8000)
    if context == "（暂无文档内容）":
        return {"degraded": True, "error": "没有可用的已解析来源，请先上传并等待解析完成"}

    prompt = _build_generation_prompt(
        kind, _kbs[kid].get("title", "知识库"), context,
        body.get("instruction", ""), body.get("mindmap_type", ""),
        body.get("style", ""), body.get("template", ""),
    )

    try:
        llm = model_manager.get_main_llm()
        content = asyncio.run(llm.chat(
            [{"role": "user", "content": prompt}],
            settings.MAIN_MODEL_NAME, temperature=0.4, max_tokens=4096,
        ))
    except Exception as e:  # noqa: BLE001
        return {"degraded": True, "error": f"生成失败: {type(e).__name__}: {e}"}

    # 清洗 LLM 输出：去掉可能包裹的代码围栏
    content = content.strip()
    content = re.sub(r"^```(?:html|markdown|md|json)?\s*\n?", "", content)
    content = re.sub(r"\n?```\s*$", "", content)

    # 时间轴：尽量截取合法 JSON 数组，前端按节点渲染
    if kind == "timeline":
        lo, hi = content.find("["), content.rfind("]")
        if lo != -1 and hi > lo:
            candidate = content[lo:hi + 1]
            try:
                json.loads(candidate)
                content = candidate
            except Exception:
                pass  # 保留原文，前端降级展示

    aid = uuid.uuid4().hex[:8]
    ext = _GENERATION_EXT[kind]
    filename = f"{aid}_{kind}.{ext}"
    artifacts_dir = _artifacts_dir(kid)
    (artifacts_dir / filename).write_text(content, encoding="utf-8")

    artifact = {
        "id": aid,
        "kind": kind,
        "label": GENERATION_LABEL[kind],
        "title": _kbs[kid].get("title", "知识库"),
        "filename": filename,
        "url": f"/static/knowledge/{kid}/artifacts/{filename}",
        "markdown": content if ext == "md" else "",
        "style": body.get("style", ""),
        "template": body.get("template", ""),
        "mindmap_type": body.get("mindmap_type", ""),
        "created_at": datetime.now().isoformat(),
        "prompt": prompt[:200],
    }
    items = _load_artifacts(kid)
    items.append(artifact)
    _save_artifacts(kid, items)
    return artifact


@router.get("/notebooks/{kid}/artifacts")
def list_artifacts(kid: str):
    """获取知识库全部产出（倒序）"""
    items = _load_artifacts(kid)
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"items": items, "total": len(items)}


def _build_pptx(md_text: str, template: str, out_path: Path):
    """把产物 markdown（# 开头为页）转成真实 .pptx 文件"""
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor

    slides = []
    current = None
    for line in md_text.splitlines():
        if line.startswith("# "):
            current = {"title": line[2:].strip(), "bullets": []}
            slides.append(current)
        elif current is not None and line.strip("#- \t"):
            current["bullets"].append(line.lstrip("#- ").strip())
    if not slides:
        slides = [{"title": "演示文稿", "bullets": [md_text[:200]]}]

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    tpl = {
        "商务深色": ((33, 33, 33), (255, 255, 255)),
        "科技渐变": ((24, 32, 68), (235, 240, 255)),
    }.get(template, ((255, 255, 255), (26, 26, 26)))  # 简约白兜底
    bg_rgb, fg_rgb = tpl

    blank = prs.slide_layouts[6]
    for i, s in enumerate(slides):
        slide = prs.slides.add_slide(blank)
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(*bg_rgb)
        # 标题
        tb = slide.shapes.add_textbox(Inches(0.8), Inches(0.7), Inches(11.7), Inches(1.2))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = s["title"]
        p.font.size = Pt(36 if i == 0 else 30)
        p.font.bold = True
        p.font.color.rgb = RGBColor(*fg_rgb)
        # 要点
        if s["bullets"]:
            bb = slide.shapes.add_textbox(Inches(0.8), Inches(2.1), Inches(11.7), Inches(4.8))
            btf = bb.text_frame
            btf.word_wrap = True
            for j, b in enumerate(s["bullets"][:10]):
                p = btf.paragraphs[0] if j == 0 else btf.add_paragraph()
                p.text = f"• {b}"
                p.font.size = Pt(20)
                p.font.color.rgb = RGBColor(*fg_rgb)
                p.space_after = Pt(10)
    prs.save(str(out_path))


@router.get("/notebooks/{kid}/artifacts/{aid}/pptx")
def download_artifact_pptx(kid: str, aid: str):
    """把 PPT 产物（markdown）导出为真实 .pptx 下载（PRD 3.2.7.4）"""
    items = _load_artifacts(kid)
    target = next((a for a in items if a["id"] == aid), None)
    if not target:
        raise HTTPException(404, "产出不存在")
    if target.get("kind") != "ppt":
        raise HTTPException(400, "该产物不是 PPT 类型")
    md_path = _artifacts_dir(kid) / target["filename"]
    if not md_path.exists():
        raise HTTPException(404, "产物文件已丢失")
    try:
        from pptx import Presentation  # noqa: F401
    except ImportError:
        raise HTTPException(400, "服务端未安装 python-pptx，无法导出 pptx")

    out_path = _artifacts_dir(kid) / f"{aid}.pptx"
    _build_pptx(md_path.read_text(encoding="utf-8"),
                target.get("template", ""), out_path)
    return FileResponse(out_path, media_type="application/octet-stream",
                        filename=f"{target.get('title', '演示文稿')}.pptx")


@router.delete("/notebooks/{kid}/artifacts/{aid}")
def delete_artifact(kid: str, aid: str):
    """删除产出"""
    items = _load_artifacts(kid)
    target = next((a for a in items if a["id"] == aid), None)
    if not target:
        raise HTTPException(404, "产出不存在")
    try:
        (_artifacts_dir(kid) / target["filename"]).unlink(missing_ok=True)
    except Exception:
        pass
    items = [a for a in items if a["id"] != aid]
    _save_artifacts(kid, items)
    return {"message": "已删除"}
