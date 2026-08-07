"""
Wiki笔记路由
"""
import os, tempfile
from pathlib import Path
from fastapi import APIRouter, Query, Depends, UploadFile, File
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.config import DATA_DIR
from backend.services.wiki_service import wiki_service
from backend.services.knowledge_parser import extract_text

router = APIRouter()

# 上传解析文章的临时目录
WIKI_TMP = DATA_DIR / "wiki" / "_tmp"
WIKI_TMP.mkdir(parents=True, exist_ok=True)


@router.post("/analyze")
async def analyze_article(file: UploadFile = File(...)):
    """上传一篇文章(pdf/docx/md/txt 等)，解析为 wiki：根来源页 + 各章节子页，并生成链接。"""
    filename = (file.filename or "文章").strip()
    content = await file.read()
    ext = os.path.splitext(filename)[1].lower().lstrip(".")

    # 写入临时文件，复用 knowledge_parser 提取文本
    import uuid
    tmp_path = WIKI_TMP / f"up_{uuid.uuid4().hex[:8]}{os.path.splitext(filename)[1]}"
    tmp_path.write_bytes(content)
    try:
        text, parse_err = extract_text(tmp_path, ext)
    finally:
        tmp_path.unlink(missing_ok=True)

    if parse_err:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=parse_err)
    if not (text or "").strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="未能从文件中提取到文本内容")

    result = wiki_service.analyze_article(filename, text)
    return {"ok": True, "root": result["root"], "children": result["children"],
            "created": result["created"]}


@router.get("/pages")
def list_pages(page_type: str = ""):
    pages = wiki_service.list_pages(page_type=page_type or None)
    return {"items": pages, "total": len(pages)}


@router.get("/pages/{slug}")
def read_page(slug: str):
    page = wiki_service.read_page(slug)
    if not page:
        return {"error": "页面不存在"}
    return page


@router.post("/pages")
def create_page(title: str = Query(...), content: str = "", page_type: str = "concept", tags: str = ""):
    tags_list = tags.split(",") if tags else []
    return wiki_service.create_page(title, content, page_type, tags_list)


@router.put("/pages/{slug}")
def update_page(slug: str, content: str = "", tags: str = "", db: Session = Depends(get_db)):
    tags_list = tags.split(",") if tags else []
    result = wiki_service.update_page(slug, content, tags_list, db=db)
    if not result:
        return {"error": "页面不存在"}
    return result


@router.get("/pages/{slug}/versions")
def list_versions(slug: str, db: Session = Depends(get_db)):
    versions = wiki_service.list_versions(slug, db)
    return {"items": versions, "total": len(versions)}


@router.post("/pages/{slug}/versions/{version_id}/restore")
def restore_version(slug: str, version_id: int, db: Session = Depends(get_db)):
    result = wiki_service.restore_version(slug, version_id, db=db)
    if not result:
        return {"error": "版本不存在或页面不存在"}
    return result


@router.delete("/pages/{slug}")
def delete_page(slug: str):
    return {"success": wiki_service.delete_page(slug)}


@router.get("/graph")
def get_graph():
    return wiki_service.get_graph_data()
