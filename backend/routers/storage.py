"""
文件存储路由 — 上传/下载/管理

安全加固: 大小上限 + 扩展名白名单 + 唯一文件名(防同名覆盖) + 不回显绝对路径。
"""
import os as _os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from backend.config import settings
from backend.core.logger import log

router = APIRouter()

# 上传限制
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
                ".md", ".markdown", ".txt", ".csv", ".json", ".html", ".htm",
                ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".zip", ".py"}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传文件到存储目录(校验大小/扩展名, 唯一命名防覆盖)"""
    filename = file.filename or "upload"
    ext = _os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, detail=f"不支持的文件类型 {ext or '(无扩展名)'}")
    content = await file.read()
    if not content:
        raise HTTPException(400, detail="文件为空")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail=f"文件超过 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 限制")
    try:
        # 通用上传统一落到 data/uploads/(不要写 data/ 根目录, 避免污染)
        from backend.config import DATA_DIR
        upload_dir = _os.path.join(str(DATA_DIR), "uploads")
        _os.makedirs(upload_dir, exist_ok=True)
        # 唯一命名: 保留原文件名供展示, 前缀 uuid 防覆盖
        safe_name = _os.path.basename(filename)
        stored_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
        dest = _os.path.join(upload_dir, stored_name)
        with open(dest, "wb") as f:
            f.write(content)
        log.info("文件上传: %s (%d KB)", stored_name, len(content) // 1024)
        rel = _os.path.relpath(dest, upload_dir)
        return {
            "id": stored_name,
            "filename": safe_name,
            "stored_name": stored_name,
            "size": len(content),
            "url": "/static/" + rel.replace("\\", "/"),
            "status": "uploaded",
            "message": "上传成功",
        }
    except Exception as e:  # noqa: BLE001
        log.warning("文件上传失败: %s", e)
        raise HTTPException(500, detail=f"上传失败: {e}")
