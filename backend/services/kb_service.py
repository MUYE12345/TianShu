"""
知识库业务服务 — 集中事务 + 权限 + 存储(SQLite)

背景: 此前知识库全部逻辑内联在 routers/knowledge.py, 依赖 JSON 文件 + 内存 dict,
无事务/无权限/并发竞态。本服务:
- 元数据/来源/会话/产物/分块全部落 SQLite(ORM: backend/models/kb.py)
- 权限模型: admin(每库唯一, 可迁移)/ editor / viewer
- 大文件(原件/产物)仍落盘, DB 存路径
- 兼容旧 API 响应结构(路由层保持路径不变)

文档: docs/KB_DATABASE_MIGRATION.md
"""
import os
import re
import json
import uuid
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.config import DATA_DIR as APP_DATA_DIR, settings
from backend.services.knowledge_parser import extract_text, is_previewable
from backend.services.kb_rag import kb_rag
from backend.services.kg_rag import kg_rag

# 知识库数据根目录(原件/产物文件落盘位置, 与旧结构一致)
KB_ROOT = APP_DATA_DIR / "knowledge"
KB_ROOT.mkdir(parents=True, exist_ok=True)

# 插画封面 ID(与前端 covers.js 映射一致)
COVERS = ["cover-1", "cover-2", "cover-3", "cover-4", "cover-5", "cover-6"]

# PRD 3.2.4: 支持上传格式白名单
ALLOWED_EXTS = {"pdf", "docx", "doc", "xls", "xlsx", "ppt", "pptx", "md", "txt",
                "markdown", "csv", "json", "html", "htm"}

# 角色等级(数值越大权限越高)
ROLE_LEVEL = {"viewer": 1, "editor": 2, "admin": 3}


def _kb_path(kid: str) -> Path:
    p = KB_ROOT / kid
    p.mkdir(parents=True, exist_ok=True)
    return p


def _source_dir(kid: str) -> Path:
    d = _kb_path(kid) / "sources"
    d.mkdir(exist_ok=True)
    return d


def _artifacts_dir(kid: str) -> Path:
    """产物落盘到 data/uploads/knowledge/{kid}/artifacts(静态目录只挂 uploads,
    使 /static/knowledge/... URL 可达, 同时不暴露 data/knowledge 下的来源原件)。"""
    d = APP_DATA_DIR / "uploads" / "knowledge" / kid / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ═══════════════════════════════════════
# 权限
# ═══════════════════════════════════════

class KbService:
    """知识库服务(单例)"""

    # ── 权限校验 ──
    @staticmethod
    def require_member(db: Session, kid: str, user_id: int, min_role: str = "viewer"):
        """校验用户是否是知识库成员且角色 >= min_role。返回 KbMember。

        未登录(user_id=0)视为匿名: 仅允许访问 is_public 知识库(viewer 级)。
        """
        from backend.models.kb import KbNotebook, KbMember
        nb = db.query(KbNotebook).filter(KbNotebook.id == kid).first()
        if not nb:
            raise HTTPException(404, "知识库不存在")

        if user_id and user_id > 0:
            m = db.query(KbMember).filter(
                KbMember.kb_id == kid, KbMember.user_id == user_id).first()
            if m:
                if ROLE_LEVEL.get(m.role, 1) >= ROLE_LEVEL.get(min_role, 1):
                    return m
                raise HTTPException(403, f"需要更高权限({min_role})")
            # 非成员: 公开知识库可读
            if nb.is_public and ROLE_LEVEL.get(min_role, 1) <= 1:
                return None
            raise HTTPException(403, "您不是该知识库成员, 无权访问")
        else:
            # 匿名
            if nb.is_public and ROLE_LEVEL.get(min_role, 1) <= 1:
                return None
            raise HTTPException(401, "请先登录")

    @staticmethod
    def get_role(db: Session, kid: str, user_id: int) -> Optional[str]:
        """查询用户在知识库中的角色(非成员返回 None)"""
        if not user_id or user_id <= 0:
            return None
        from backend.models.kb import KbMember
        m = db.query(KbMember).filter(
            KbMember.kb_id == kid, KbMember.user_id == user_id).first()
        return m.role if m else None

    # ═══════════ 知识库 CRUD ═══════════
    def list_kbs(self, db: Session, user_id: int) -> dict:
        """我的知识库 + 共享给我的 + 公开知识库(全部知识)"""
        from backend.models.kb import KbNotebook, KbMember
        q = db.query(KbNotebook).order_by(KbNotebook.updated_at.desc())
        notebooks = q.all()

        items = []
        for nb in notebooks:
            role = self.get_role(db, nb.id, user_id)
            # 过滤: 成员 / 公开库可见; 其余不可见
            if role is None and not nb.is_public:
                continue
            d = nb.to_dict()
            d["my_role"] = role or ("viewer" if nb.is_public else None)
            d["owner_name"] = self._user_name(db, nb.owner_id)
            items.append(d)
        return {"items": items, "total": len(items)}

    @staticmethod
    def _user_name(db: Session, user_id: int) -> str:
        if not user_id:
            return ""
        from backend.models.user import User
        u = db.query(User).filter(User.id == user_id).first()
        return u.username if u else ""

    def create_kb(self, db: Session, user_id: int, body: dict) -> dict:
        """创建知识库(创建者自动成为唯一 admin)"""
        from backend.models.kb import KbNotebook, KbMember
        kid = uuid.uuid4().hex[:12]
        nb = KbNotebook(
            id=kid,
            title=(body.get("title") or "未命名")[:200],
            description=(body.get("description") or "")[:500],
            cover=body.get("cover") or "cover-1",
            owner_id=user_id,
            is_public=bool(body.get("is_public", False)),
        )
        db.add(nb)
        db.flush()
        db.add(KbMember(kb_id=kid, user_id=user_id, role="admin"))
        db.commit()
        db.refresh(nb)
        d = nb.to_dict()
        d["my_role"] = "admin"
        return d

    def update_kb(self, db: Session, kid: str, user_id: int, body: dict) -> dict:
        """更新知识库元数据(editor 及以上)"""
        from backend.models.kb import KbNotebook
        self.require_member(db, kid, user_id, "editor")
        nb = db.query(KbNotebook).filter(KbNotebook.id == kid).first()
        for k in ("title", "description", "cover", "is_public"):
            if k in body and body[k] is not None:
                setattr(nb, k, body[k] if k != "is_public" else bool(body[k]))
        nb.updated_at = datetime.now()
        db.commit()
        db.refresh(nb)
        d = nb.to_dict()
        d["my_role"] = self.get_role(db, kid, user_id)
        return d

    def delete_kb(self, db: Session, kid: str, user_id: int) -> dict:
        """删除知识库(仅 admin)"""
        from backend.models.kb import KbNotebook, KbMember, KbSource, KbArtifact
        self.require_member(db, kid, user_id, "admin")
        nb = db.query(KbNotebook).filter(KbNotebook.id == kid).first()
        if not nb:
            raise HTTPException(404, "知识库不存在")
        # 清理 RAG 索引 + 实体图(独立于知识库目录)
        kb_rag.drop_index(kid)
        kg_rag.clear(kid)
        # ORM 级联删除来源/成员/会话/消息/产物(外键已启用)
        db.delete(nb)
        db.commit()
        # 清理磁盘文件(原件/产物/文本缓存)
        import shutil as _sh
        _sh.rmtree(_kb_path(kid), ignore_errors=True)
        return {"message": "已删除"}

    # ═══════════ 来源 ═══════════
    def list_sources(self, db: Session, kid: str, user_id: int) -> dict:
        from backend.models.kb import KbSource
        self.require_member(db, kid, user_id, "viewer")
        sources = db.query(KbSource).filter(KbSource.kb_id == kid).order_by(
            KbSource.created_at).all()
        return {"items": [s.to_dict() for s in sources], "total": len(sources)}

    def _source_filepath(self, kid: str, s) -> Path:
        """来源原件路径(防御路径穿越)"""
        filename = Path(s.filename).name
        return _source_dir(kid) / f"{s.id}_{filename}"

    def upload_source(self, db: Session, kid: str, user_id: int,
                      filename: str, content: bytes, background_tasks=None) -> dict:
        """上传来源文档: 格式白名单 + 50MB 限制; 落盘后后台异步解析"""
        self.require_member(db, kid, user_id, "editor")
        ext = os.path.splitext(filename or "unknown")[1].lower().lstrip(".")
        if ext not in ALLOWED_EXTS:
            raise HTTPException(400, f"不支持的文件格式 .{ext}，支持：pdf/docx/doc/xls/xlsx/ppt/pptx/md/txt 等")
        if len(content) > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(413, f"文件超过 {settings.MAX_UPLOAD_SIZE // (1024 * 1024)}MB 大小限制")

        from backend.models.kb import KbSource
        fid = uuid.uuid4().hex[:8]
        safe_name = Path(filename).name
        save_dir = _source_dir(kid)
        (save_dir / f"{fid}_{safe_name}").write_bytes(content)

        src = KbSource(
            id=fid, kb_id=kid, filename=safe_name, ext=ext, size=len(content),
            status="parsing", previewable=is_previewable(ext),
            file_path=f"sources/{fid}_{safe_name}",
        )
        db.add(src)
        db.commit()
        db.refresh(src)
        if background_tasks is not None:
            background_tasks.add_task(self.parse_source, db, kid, fid)
        return src.to_dict()

    def add_text_source(self, db: Session, kid: str, user_id: int, body) -> dict:
        """粘贴文本作为来源(设计稿「粘贴文本」tab)"""
        self.require_member(db, kid, user_id, "editor")
        text = (body.content or "").strip()
        if not text:
            raise HTTPException(400, "文本内容不能为空")
        if len(text.encode("utf-8")) > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(413, "文本超过大小限制")

        from backend.models.kb import KbSource
        fid = uuid.uuid4().hex[:8]
        title = (body.title or "").strip() or f"粘贴文本_{datetime.now().strftime('%m%d_%H%M')}"
        # 防目录穿越: 标题可能含 ../ 或 \ 等路径字符, 一律替换为下划线
        safe_title = title.replace("\\", "_").replace("/", "_")
        filename = f"{safe_title}.md"
        save_dir = _source_dir(kid)
        (save_dir / f"{fid}_{filename}").write_text(text, encoding="utf-8")

        src = KbSource(
            id=fid, kb_id=kid, filename=filename, ext="md",
            size=len(text.encode("utf-8")), status="parsed",
            previewable=True, text_preview=text[:3000], text_cache=text,
            file_path=f"sources/{fid}_{filename}",
        )
        db.add(src)
        db.commit()
        self.rebuild_index(db, kid)  # 粘贴文本已即时可检索
        return src.to_dict()

    def delete_source(self, db: Session, kid: str, sid: str, user_id: int) -> dict:
        """删除来源(editor 及以上); 级联清理索引与向量"""
        from backend.models.kb import KbSource
        self.require_member(db, kid, user_id, "editor")
        src = db.query(KbSource).filter(KbSource.kb_id == kid, KbSource.id == sid).first()
        if not src:
            raise HTTPException(404, "来源不存在")
        fp = self._source_filepath(kid, src)
        try:
            if fp.exists():
                fp.unlink()
        except Exception:
            pass
        db.delete(src)
        db.commit()
        self.rebuild_index(db, kid)
        return {"message": "已删除"}

    # ── 后台解析 ──
    def parse_source(self, db: Session, kid: str, fid: str):
        """后台解析来源(独立 session, 由 BackgroundTasks 调用)"""
        try:
            from backend.database import SessionLocal
            bg = SessionLocal()
            try:
                self._do_parse(bg, kid, fid)
            finally:
                bg.close()
        except Exception as e:  # noqa: BLE001
            print(f"[KB] 后台解析异常 {kid}/{fid}: {e}")

    def _do_parse(self, db: Session, kid: str, fid: str):
        from backend.models.kb import KbSource
        src = db.query(KbSource).filter(KbSource.kb_id == kid, KbSource.id == fid).first()
        if not src:
            return
        fp = self._source_filepath(kid, src)
        try:
            try:
                text, parse_err = extract_text(fp, src.ext or "")
            except Exception as e:  # noqa: BLE001
                text, parse_err = "", f"解析失败: {type(e).__name__}: {e}"
            if parse_err:
                src.status = "failed"
                src.parse_error = parse_err
            else:
                src.status = "parsed"
                src.text_preview = text[:3000]
                src.text_cache = text[:100000]
                # 兼容旧路径: 同时写 .txt 缓存(供旧代码/预览复用)
                try:
                    (_source_dir(kid) / f"{fid}.txt").write_text(
                        text[:100000], encoding="utf-8", errors="replace")
                except Exception:
                    pass
                db.commit()
                self.rebuild_index(db, kid)
        except Exception as e:  # noqa: BLE001
            try:
                src.status = "failed"
                src.parse_error = f"解析失败: {type(e).__name__}: {e}"
            except Exception:
                pass
        db.commit()

    # ── 索引/图 ──
    def rebuild_index(self, db: Session, kid: str):
        """按当前已解析来源重建 RAG 索引(kb_rag 增量, 来源集合变化才重建)"""
        from backend.models.kb import KbSource
        try:
            sources = db.query(KbSource).filter(
                KbSource.kb_id == kid, KbSource.status == "parsed").all()
            items = []
            for s in sources:
                text = (s.text_cache or "").strip()
                if not text:
                    fp = self._source_filepath(kid, s)
                    if fp.exists():
                        t, _e = extract_text(fp, s.ext or "")
                        text = t or ""
                if text.strip():
                    items.append({"id": s.id, "filename": s.filename, "text": text})
            if items:
                kb_rag.ensure_index(kid, items)
                self._spawn_graph_build(kid, [i["id"] for i in items])
        except Exception as e:  # noqa: BLE001
            print(f"[KB] 重建索引失败 {kid}: {e}")

    @staticmethod
    def _spawn_graph_build(kid: str, source_ids: list):
        """后台线程构建轻量实体图, 不阻塞上传/解析响应。失败隔离。"""
        if not settings.GRAPH_ENABLED:
            return
        try:
            t = threading.Thread(target=kg_rag.build_graph_if_needed,
                                 args=(kid, source_ids), daemon=True)
            t.start()
        except Exception as e:  # noqa: BLE001
            print(f"[KB] 启动构图失败 {kid}: {e}")

    # ═══════════ 预览 / 下载 ═══════════
    def get_source_path(self, db: Session, kid: str, sid: str, user_id: int) -> tuple:
        """获取来源原件路径与扩展名(预览/下载共用)"""
        from backend.models.kb import KbSource
        self.require_member(db, kid, user_id, "viewer")
        src = db.query(KbSource).filter(KbSource.kb_id == kid, KbSource.id == sid).first()
        if not src:
            raise HTTPException(404, "来源不存在")
        fp = self._source_filepath(kid, src)
        if not fp.exists():
            raise HTTPException(404, "文件已丢失")
        return fp, (src.ext or "").lower().lstrip("."), src.filename

    def get_source_text(self, db: Session, kid: str, sid: str, user_id: int) -> str:
        """获取来源提取文本(文本类预览)"""
        from backend.models.kb import KbSource
        self.require_member(db, kid, user_id, "viewer")
        src = db.query(KbSource).filter(KbSource.kb_id == kid, KbSource.id == sid).first()
        if not src:
            raise HTTPException(404, "来源不存在")
        if src.text_cache:
            return src.text_cache
        fp = self._source_filepath(kid, src)
        if not fp.exists():
            raise HTTPException(404, "文件已丢失")
        text, err = extract_text(fp, src.ext or "")
        if err:
            raise HTTPException(400, err)
        return text

    # ═══════════ 会话 ═══════════
    def list_chats(self, db: Session, kid: str, user_id: int) -> dict:
        from backend.models.kb import KbChat
        self.require_member(db, kid, user_id, "viewer")
        chats = db.query(KbChat).filter(KbChat.kb_id == kid).order_by(
            KbChat.updated_at.desc()).all()
        items = []
        for c in chats:
            d = c.to_dict()
            d["message_count"] = len(c.messages or [])
            items.append(d)
        return {"items": items, "total": len(items)}

    def create_chat(self, db: Session, kid: str, user_id: int, title: str = "") -> dict:
        from backend.models.kb import KbChat
        self.require_member(db, kid, user_id, "viewer")
        chat = KbChat(id=uuid.uuid4().hex[:12], kb_id=kid,
                      title=(title or "新对话")[:200])
        db.add(chat)
        db.commit()
        db.refresh(chat)
        return chat.to_dict()

    def get_chat(self, db: Session, kid: str, cid: str, user_id: int) -> dict:
        from backend.models.kb import KbChat
        self.require_member(db, kid, user_id, "viewer")
        chat = db.query(KbChat).filter(KbChat.kb_id == kid, KbChat.id == cid).first()
        if not chat:
            raise HTTPException(404, "会话不存在")
        return chat.to_dict(with_messages=True)

    def delete_chat(self, db: Session, kid: str, cid: str, user_id: int) -> dict:
        from backend.models.kb import KbChat
        self.require_member(db, kid, user_id, "viewer")
        chat = db.query(KbChat).filter(KbChat.kb_id == kid, KbChat.id == cid).first()
        if not chat:
            raise HTTPException(404, "会话不存在")
        db.delete(chat)
        db.commit()
        return {"message": "已删除"}

    # ═══════════ 产物 ═══════════
    def list_artifacts(self, db: Session, kid: str, user_id: int) -> dict:
        from backend.models.kb import KbArtifact
        self.require_member(db, kid, user_id, "viewer")
        arts = db.query(KbArtifact).filter(KbArtifact.kb_id == kid).order_by(
            KbArtifact.created_at.desc()).all()
        items = []
        for a in arts:
            d = a.to_dict()
            # 产物经 /static 服务(文件在 data/uploads/knowledge/..., 静态目录只挂 uploads)
            d["url"] = f"/static/knowledge/{kid}/artifacts/{d['filename']}"
            if d["kind"] in ("mindmap", "ppt", "brief"):
                d["markdown"] = self._artifact_markdown(kid, a)
            items.append(d)
        return {"items": items, "total": len(items)}

    def _artifact_markdown(self, kid: str, a) -> str:
        try:
            fp = _artifacts_dir(kid) / (a.filename or "")
            if fp.exists():
                return fp.read_text(encoding="utf-8")
        except Exception:
            pass
        return ""

    def get_artifact(self, db: Session, kid: str, aid: str, user_id: int) -> Optional[dict]:
        from backend.models.kb import KbArtifact
        self.require_member(db, kid, user_id, "viewer")
        a = db.query(KbArtifact).filter(KbArtifact.kb_id == kid, KbArtifact.id == aid).first()
        if not a:
            raise HTTPException(404, "产物不存在")
        d = a.to_dict()
        d["url"] = f"/static/knowledge/{kid}/artifacts/{d['filename']}"
        if d["kind"] in ("mindmap", "ppt", "brief"):
            d["markdown"] = self._artifact_markdown(kid, a)
        return d

    def delete_artifact(self, db: Session, kid: str, aid: str, user_id: int) -> dict:
        from backend.models.kb import KbArtifact
        self.require_member(db, kid, user_id, "editor")
        a = db.query(KbArtifact).filter(KbArtifact.kb_id == kid, KbArtifact.id == aid).first()
        if not a:
            raise HTTPException(404, "产物不存在")
        try:
            fp = _artifacts_dir(kid) / (a.filename or "")
            if fp.exists():
                fp.unlink()
            pptx = _artifacts_dir(kid) / f"{a.id}.pptx"
            if pptx.exists():
                pptx.unlink()
        except Exception:
            pass
        db.delete(a)
        db.commit()
        return {"message": "已删除"}

    # ═══════════ 成员 / 共享 ═══════════
    def list_members(self, db: Session, kid: str, user_id: int) -> dict:
        from backend.models.kb import KbMember
        self.require_member(db, kid, user_id, "viewer")
        members = db.query(KbMember).filter(KbMember.kb_id == kid).all()
        items = []
        for m in members:
            d = m.to_dict()
            d["username"] = self._user_name(db, m.user_id)
            items.append(d)
        return {"items": items, "total": len(items)}

    def add_member(self, db: Session, kid: str, user_id: int, body: dict) -> dict:
        """添加成员并指定角色(仅 admin); role 不能为 admin(唯一, 用 transfer 迁移)"""
        from backend.models.kb import KbMember
        from backend.models.user import User
        self.require_member(db, kid, user_id, "admin")
        target_uid = body.get("user_id") or 0
        role = (body.get("role") or "viewer").strip().lower()
        if role not in ("editor", "viewer"):
            raise HTTPException(400, "仅可添加 editor/viewer 角色; 管理员需通过 transfer 迁移")
        if not target_uid:
            raise HTTPException(400, "user_id 不能为空")
        u = db.query(User).filter(User.id == target_uid).first()
        if not u:
            raise HTTPException(404, "用户不存在")
        exists = db.query(KbMember).filter(
            KbMember.kb_id == kid, KbMember.user_id == target_uid).first()
        if exists:
            exists.role = role
            db.commit()
            db.refresh(exists)
            return exists.to_dict()
        m = KbMember(kb_id=kid, user_id=target_uid, role=role)
        db.add(m)
        db.commit()
        db.refresh(m)
        return m.to_dict()

    def update_member_role(self, db: Session, kid: str, user_id: int,
                           target_uid: int, role: str) -> dict:
        """修改成员角色(仅 admin); 禁止降级唯一 admin, 禁止直接设 admin"""
        from backend.models.kb import KbMember
        self.require_member(db, kid, user_id, "admin")
        role = (role or "").strip().lower()
        if role not in ("editor", "viewer", "admin"):
            raise HTTPException(400, "非法角色")
        m = db.query(KbMember).filter(
            KbMember.kb_id == kid, KbMember.user_id == target_uid).first()
        if not m:
            raise HTTPException(404, "该用户不是知识库成员")
        if m.role == "admin":
            raise HTTPException(400, "管理员角色唯一, 请使用「转移管理员」迁移")
        if role == "admin":
            raise HTTPException(400, "不能直接设置管理员, 请使用「转移管理员」")
        m.role = role
        db.commit()
        db.refresh(m)
        return m.to_dict()

    def remove_member(self, db: Session, kid: str, user_id: int, target_uid: int) -> dict:
        """移除成员(仅 admin); 不能移除唯一 admin"""
        from backend.models.kb import KbMember
        self.require_member(db, kid, user_id, "admin")
        m = db.query(KbMember).filter(
            KbMember.kb_id == kid, KbMember.user_id == target_uid).first()
        if not m:
            raise HTTPException(404, "该用户不是知识库成员")
        if m.role == "admin":
            raise HTTPException(400, "不能移除唯一管理员; 请先转移管理员")
        db.delete(m)
        db.commit()
        return {"message": "已移除"}

    def transfer_admin(self, db: Session, kid: str, user_id: int, body: dict) -> dict:
        """迁移管理员: 目标成员升为 admin, 原 admin 降为 editor(始终唯一)。

        数据库部分唯一索引(uq_kb_members_admin)兜底并发安全。
        """
        from backend.models.kb import KbMember
        from backend.models.user import User
        self.require_member(db, kid, user_id, "admin")
        target_uid = body.get("user_id") or 0
        if not target_uid:
            raise HTTPException(400, "user_id 不能为空")
        if target_uid == user_id:
            raise HTTPException(400, "已是当前管理员")
        u = db.query(User).filter(User.id == target_uid).first()
        if not u:
            raise HTTPException(404, "用户不存在")
        # 目标未加入则自动以 editor 加入
        target = db.query(KbMember).filter(
            KbMember.kb_id == kid, KbMember.user_id == target_uid).first()
        if not target:
            target = KbMember(kb_id=kid, user_id=target_uid, role="editor")
            db.add(target)
            db.flush()
        current_admin = db.query(KbMember).filter(
            KbMember.kb_id == kid, KbMember.role == "admin").first()
        try:
            # 事务: 新 admin → 旧 admin 降级 → 提交
            target.role = "admin"
            if current_admin:
                current_admin.role = "editor"
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(409, "管理员迁移失败(并发冲突), 请重试")
        return {"message": "管理员已转移", "new_admin": target_uid,
                "old_admin": user_id}


# 全局单例
kb_service = KbService()
