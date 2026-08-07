"""
论文解析路由

说明: 本项目为单用户个人应用, 端点默认匿名访问。若部署为多用户公开服务,
需为所有路由补充认证与授权中间件。"""
import os
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.config import settings
from backend.services.paper_service import paper_service
from agent.crawlers.arxiv.arxiv_client import ArxivClient

router = APIRouter()


@router.get("/list")
def list_papers(db: Session = Depends(get_db)):
    """获取所有论文列表"""
    from backend.models.paper import Paper
    papers = db.query(Paper).order_by(Paper.id.desc()).limit(50).all()
    return [{"id": p.id, "title": p.title, "source": p.source, "pages": p.pages,
             "status": p.status, "created_at": str(p.created_at)[:19] if p.created_at else ""} for p in papers]


@router.post("/upload")
def upload_paper(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """上传论文PDF"""

    # --- 文件上传校验 ---
    # 1. 检查文件扩展名
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件上传")

    # 2. 检查文件大小（< 50MB）
    MAX_SIZE = 50 * 1024 * 1024
    raw = file.file.read(MAX_SIZE + 1)  # 多读 1 字节用于判断是否超限
    if not raw:
        raise HTTPException(status_code=400, detail="上传的文件为空")
    if len(raw) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="文件大小不能超过 50MB")

    # 3. 检查 PDF 幻数（防止伪装成 .pdf 的可执行文件）
    if not raw.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="文件不是有效的 PDF 格式")

    # --- 写入临时文件 ---
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    result = paper_service.upload_paper(db, tmp_path, file.filename)
    return result



@router.post("/search")
def search_papers(body: dict):
    """搜索arXiv论文"""
    client = ArxivClient()
    query = body.get("query", "")
    author = body.get("author", "")
    if author:
        papers = client.search_by_author(author)
    else:
        papers = client.search(query)
    return [{"title": p.title, "authors": p.authors[:3], "summary": p.summary[:300],
             "published": p.published, "pdf_url": p.pdf_url} for p in papers]

@router.post("/{paper_id}/ocr")
def start_paper_ocr(paper_id: int, db: Session = Depends(get_db)):
    """手动触发论文OCR"""
    return paper_service.start_ocr(db, paper_id)


@router.post("/{paper_id}/visualize")
def visualize_paper(paper_id: int, db: Session = Depends(get_db)):
    """渲染页面图为 PNG + 提取段落框（魔搭式双栏）"""
    return paper_service.visualize_paper(db, paper_id)


@router.post("/{paper_id}/pages/{page_num}/translate")
def translate_paper_page(paper_id: int, page_num: int, db: Session = Depends(get_db)):
    """按需翻译单页（动态翻译，前端滚动到未翻译页时触发）"""
    return paper_service.translate_page(db, paper_id, page_num)


@router.get("/{paper_id}/parsed")
def get_parsed_paper(paper_id: int, db: Session = Depends(get_db)):
    """LLM解析论文内容(逐段解读)"""
    import json
    def generate():
        for event in paper_service.parse_paper(paper_id, db):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/{paper_id}")
def get_paper(paper_id: int, db: Session = Depends(get_db)):
    paper = paper_service.get_paper(db, paper_id)
    if not paper:
        return {"error": "论文不存在"}
    return paper


@router.get("/{paper_id}/pages")
def get_paper_pages(paper_id: int, db: Session = Depends(get_db)):
    return paper_service.get_paper_pages(db, paper_id)


@router.get("/{paper_id}/figures")
def get_paper_figures(paper_id: int, db: Session = Depends(get_db)):
    """获取论文图表及AI解读"""
    from backend.models.paper import PaperFigure
    figs = db.query(PaperFigure).filter(PaperFigure.paper_id == paper_id).all()
    out = []
    for f in figs:
        image_url = ""
        if f.image_path and os.path.exists(f.image_path):
            rel = os.path.relpath(f.image_path, settings.UPLOAD_DIR)
            image_url = "/static/" + rel.replace("\\", "/")
        out.append({"id": f.id, "page_num": f.page_num, "image_path": f.image_path or "",
                    "image_url": image_url, "caption": f.caption or "",
                    "llm_explanation": f.llm_explanation or ""})
    return out


@router.post("/{paper_id}/figures/{fig_id}/explain")
def explain_paper_figure(paper_id: int, fig_id: int, db: Session = Depends(get_db)):
    """AI 解读指定图表(多模态, 带所在页源文/译文上下文), 结果持久化。"""
    from backend.models.paper import PaperFigure, PaperPage
    from backend.services.paper_image_service import paper_image_service
    fig = db.query(PaperFigure).filter(PaperFigure.id == fig_id).first()
    if not fig:
        raise HTTPException(404, "图表不存在")
    # 取图表所在页的源文与译文, 作为解读上下文(辅助双屏对齐)
    source_ctx = target_ctx = ""
    page = (db.query(PaperPage).filter(
        PaperPage.paper_id == paper_id,
        PaperPage.page_num == fig.page_num,
    ).first() if fig.page_num else None)
    if page:
        source_ctx = page.ocr_text or ""
        target_ctx = page.translated_text or ""
    explanation = paper_image_service.explain_figure(
        fig.image_path or "", fig.caption or "", source_ctx, target_ctx)
    fig.llm_explanation = explanation
    db.commit()
    return {"id": fig.id, "page_num": fig.page_num, "explanation": explanation}


@router.delete("/{paper_id}")
def delete_paper(paper_id: int, db: Session = Depends(get_db)):
    success = paper_service.delete_paper(db, paper_id)
    return {"success": success}
