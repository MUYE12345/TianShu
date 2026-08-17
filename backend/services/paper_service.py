"""
论文解析服务 — 上传/OCR/解析/翻译
"""
import os, json, re, shutil, threading, asyncio
from typing import List, Optional
from sqlalchemy.orm import Session
from backend.models.paper import Paper, PaperPage, PaperFigure
from backend.services.paper_ocr_service import paper_ocr
from backend.config import settings
from backend.database import SessionLocal
from backend.core.model_config import model_manager

# 页面图尺寸缓存(避免每次请求 PIL 重读)
_IMG_SIZE_CACHE = {}


def split_paper_sections(full_text: str) -> list:
    """按常见论文章节标题分段, 返回 [(title, content), ...](标题与正文对齐, 丢弃标题前内容)。

    识别: 编号标题(1. / 3.1) + 常见章节名(独占一行)。无匹配时回退单段"全文摘要"。
    """
    if not full_text:
        return []
    heading_pattern = re.compile(
        r"(?m)^\s*((?:\d+(?:\.\d+)*\.?\s+)?(?:Abstract|Introduction|Background|Related Work|"
        r"Preliminaries|Method(?:ology)?|Experiments?|Results|Discussion|Conclusion(?:s)?|"
        r"References|Appendix(?:es)?|Acknowledgements?|Overview|Approach|Architecture|"
        r"Evaluation|Limitations?))\s*$",
        flags=re.IGNORECASE)
    parts = heading_pattern.split(full_text)
    # parts = [前文, 标题1, 正文1, 标题2, 正文2, ...]; 标题[i] 对应正文[i+1]
    titles = [parts[i] for i in range(1, len(parts), 2)]
    contents = [parts[i] for i in range(2, len(parts), 2)]
    pairs = [(t.strip(), c[:1500]) for t, c in zip(titles, contents) if c.strip()]
    if not pairs:
        pairs = [("全文摘要", full_text[:2000])]
    return pairs[:6]


class PaperService:
    """论文服务"""

    def upload_paper(self, db: Session, file_path: str, title: str = "") -> dict:
        """上传PDF(不自动OCR, 用户手动触发)"""
        upload_dir = os.path.join(settings.UPLOAD_DIR, "papers")
        os.makedirs(upload_dir, exist_ok=True)
        dest = os.path.join(upload_dir, os.path.basename(file_path))
        shutil.copy2(file_path, dest)
        # 清理临时上传文件(paper.py 用 NamedTemporaryFile(delete=False) 写入)
        try:
            if os.path.abspath(file_path) != os.path.abspath(dest) and os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass

        paper = Paper(title=title or os.path.basename(file_path), pdf_path=dest, status="pending")
        db.add(paper)
        db.commit()
        db.refresh(paper)

        return {"id": paper.id, "title": paper.title, "status": "pending", "message": "上传成功, 点击解析按钮开始OCR"}

    def start_ocr(self, db: Session, paper_id: int) -> dict:
        """手动触发OCR解析(异步)

        状态机: pending → ocr_processing(落库, 列表页显示"解析中") → ocr_done/error。
        已在处理中或已解析完成的论文不重复触发, 避免并发线程重复插入页面。
        """
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if not paper:
            return {"error": "论文不存在"}
        # 重复触发防护
        if paper.status == "ocr_processing":
            return {"id": paper_id, "status": "ocr_processing", "message": "OCR正在处理中, 请稍候"}
        if paper.status in ("ocr_done", "parsed") and paper.pages and paper.pages > 0:
            return {"id": paper_id, "status": paper.status, "message": "该论文已完成解析"}

        # 先落库"处理中", 让列表页立即显示解析中状态
        paper.status = "ocr_processing"
        db.commit()

        def _bg_ocr():
            bg_db = SessionLocal()
            try:
                self._do_ocr(bg_db, paper_id)
            finally:
                bg_db.close()
        threading.Thread(target=_bg_ocr, daemon=True).start()
        return {"id": paper_id, "status": "ocr_processing", "message": "OCR已启动, 请稍后刷新查看结果"}

    def _do_ocr(self, db: Session, paper_id: int):
        """执行OCR处理。各阶段失败都会把状态置为 error, 不再静默停在 ocr_done。"""
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if not paper:
            return
        try:
            pages = paper_ocr.process_pdf(paper.pdf_path, paper_id=paper_id)
            for p in pages:
                db.add(PaperPage(
                    paper_id=paper_id, page_num=p["page_num"],
                    image_path=p.get("image_path", ""), ocr_text=p.get("ocr_text", ""),
                ))
            paper.pages = len(pages)
            db.commit()
            # 渲染页面图 + 提取段落框（魔搭式双栏）
            self._visualize_pages(db, paper_id)
            # 提取论文图表（图片 + 标题启发式）
            self._extract_figures(db, paper_id)
            # OCR 完成后逐页翻译（后台线程内调用，主模型）
            self._translate_pages(db, paper_id)
            # 全部完成才置 ocr_done
            paper = db.query(Paper).filter(Paper.id == paper_id).first()
            if paper and paper.status != "error":
                paper.status = "ocr_done"
                db.commit()
        except Exception as e:  # noqa: BLE001
            # 状态机兜底: 失败必须可见, 不能停在 ocr_processing/ocr_done
            paper = db.query(Paper).filter(Paper.id == paper_id).first()
            if paper:
                paper.status = "error"
                db.commit()
            from backend.core.logger import log
            log.warning("[Paper] OCR 处理失败 paper=%s: %s", paper_id, e)

    def _visualize_pages(self, db: Session, paper_id: int):
        """为已有页面渲染 PNG + 提取段落框（幂等，不重复翻译）。"""
        try:
            paper = db.query(Paper).filter(Paper.id == paper_id).first()
            if not paper or not paper.pdf_path or not os.path.exists(paper.pdf_path):
                return
            visual = paper_ocr.process_pdf_visual(paper.pdf_path, paper_id)
            for v in visual:
                pg = db.query(PaperPage).filter(
                    PaperPage.paper_id == paper_id,
                    PaperPage.page_num == v["page_num"],
                ).first()
                if not pg:
                    continue
                pg.image_path = v["image_path"]
                pg.para_boxes = v["boxes"]
            db.commit()
        except Exception:
            pass  # 可视化失败不阻断

    def visualize_paper(self, db: Session, paper_id: int) -> dict:
        """手动触发可视化（渲染图片 + 段落框）。"""
        self._visualize_pages(db, paper_id)
        return {"paper_id": paper_id, "status": "visualized"}

    @staticmethod
    def _translate_text(text: str) -> str:
        """把英文论文文本翻译成中文(单次LLM调用)。失败返回空串。

        提示词要求"逐段翻译、空行分隔、段落数与原文一致", 以便前端按段落框
        索引配对译文(整页一次性翻译会因段落数不一致导致双语错位)。
        """
        from backend.core.model_config import model_manager
        llm = model_manager.get_main_llm()
        prompt = (
            "请把下面的英文论文内容翻译成通顺的中文。要求:\n"
            "- 保留专业术语，首次出现时可在括号里标注英文原文\n"
            "- **逐段翻译**: 原文的每个段落对应译文的一个段落\n"
            "- 段落之间用空行分隔，**译文段落数量必须与原文完全一致**\n"
            "- 不要合并段落，也不要拆分段落\n"
            "- 不要输出解释性文字\n\n"
            f"{text[:1200]}"
        )
        try:
            translated = asyncio.run(llm.chat(
                [{"role": "user", "content": prompt}], model_manager.main_config.model_name))
            return (translated or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _page_translatable(text: str) -> bool:
        """页面是否有可翻译文本。"""
        return bool(text and not text.startswith("[PDF打开失败") and not text.startswith("[图片OCR失败"))

    def translate_page(self, db: Session, paper_id: int, page_num: int) -> dict:
        """按需翻译单页（动态翻译），已有翻译则直接返回。"""
        pg = db.query(PaperPage).filter(
            PaperPage.paper_id == paper_id,
            PaperPage.page_num == page_num,
        ).first()
        if not pg:
            return {"error": "页面不存在"}
        if (pg.translated_text or "").strip():
            return {"page_num": page_num, "translated_text": pg.translated_text}
        text = (pg.ocr_text or "").strip()
        if not self._page_translatable(text):
            return {"page_num": page_num, "translated_text": "", "error": "该页无可翻译文本"}
        translated = self._translate_text(text)
        if not translated:
            return {"page_num": page_num, "translated_text": "", "error": "翻译失败"}
        pg.translated_text = translated
        db.commit()
        return {"page_num": page_num, "translated_text": pg.translated_text}

    def _translate_pages(self, db: Session, paper_id: int, max_pages: int = 20):
        """逐页翻译英文论文为中文（并行, 单次提交），写入 translated_text。"""
        try:
            pages = db.query(PaperPage).filter(
                PaperPage.paper_id == paper_id,
            ).order_by(PaperPage.page_num).all()
            todo = [pg for pg in pages[:max_pages]
                    if self._page_translatable((pg.ocr_text or "").strip())
                    and not (pg.translated_text or "").strip()]
            if not todo:
                return
            # 并行翻译(独立线程各自 asyncio.run), 之后统一提交
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=settings.PAPER_TRANSLATE_CONCURRENCY) as ex:
                results = list(ex.map(lambda pg: (pg.id, self._translate_text(pg.ocr_text or "")), todo))
            for pid, translated in results:
                if not translated:
                    continue
                for pg in todo:
                    if pg.id == pid:
                        pg.translated_text = translated
                        break
            db.commit()
        except Exception:
            pass

    def get_paper(self, db: Session, paper_id: int) -> Optional[dict]:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if not paper:
            return None
        return {
            "id": paper.id, "title": paper.title, "authors": paper.authors or [],
            "abstract": paper.abstract or "", "source": paper.source,
            "pages": paper.pages, "status": paper.status,
            "created_at": str(paper.created_at) if paper.created_at else "",
        }

    @staticmethod
    def _image_size(path: str):
        """读取图片尺寸(内存缓存, 避免每次请求重读)。"""
        cached = _IMG_SIZE_CACHE.get(path)
        if cached:
            return cached
        try:
            from PIL import Image
            with Image.open(path) as im:
                size = im.size
        except Exception:
            size = (0, 0)
        if len(_IMG_SIZE_CACHE) > 2048:  # 防无限膨胀
            _IMG_SIZE_CACHE.clear()
        _IMG_SIZE_CACHE[path] = size
        return size

    def get_paper_pages(self, db: Session, paper_id: int) -> List[dict]:
        pages = db.query(PaperPage).filter(PaperPage.paper_id == paper_id).order_by(PaperPage.page_num).all()
        result = []
        for p in pages:
            image_url = ""
            img_w = img_h = 0
            if p.image_path and os.path.exists(p.image_path):
                rel = os.path.relpath(p.image_path, settings.UPLOAD_DIR)
                image_url = "/static/" + rel.replace("\\", "/")
                img_w, img_h = self._image_size(p.image_path)
            result.append({
                "page_num": p.page_num,
                "image_url": image_url,
                "img_w": img_w,
                "img_h": img_h,
                "ocr_text": p.ocr_text,
                "translated_text": p.translated_text or "",
                "para_boxes": p.para_boxes or [],
            })
        return result

    @staticmethod
    def _analysis_path(paper_id: int) -> str:
        """逐段解析结果的 sidecar 缓存文件路径。"""
        return os.path.join(settings.UPLOAD_DIR, "papers", "_analysis", f"{paper_id}.json")

    def parse_paper(self, paper_id: int, db: Session):
        """LLM解析论文: 分段→AI解读（结果持久化到 sidecar 文件, 不再污染 abstract 字段）"""
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if not paper:
            return iter([{"type": "error", "message": "论文不存在"}])

        # 已解析 → 直接返回缓存结果
        cache_path = self._analysis_path(paper_id)
        if paper.status == "parsed" and os.path.exists(cache_path):
            try:
                cached = json.loads(open(cache_path, encoding="utf-8").read())
                for item in cached:
                    yield {"type": "section", "title": item.get("title", ""), "analysis": item.get("analysis", "")}
                return
            except (json.JSONDecodeError, TypeError, OSError):
                pass  # 缓存失效，重新解析

        pages = db.query(PaperPage).filter(PaperPage.paper_id == paper_id).order_by(PaperPage.page_num).all()
        if not pages:
            return iter([{"type": "error", "message": "论文尚未OCR"}])

        full_text = "\n".join([p.ocr_text or "" for p in pages])
        if len(full_text) < 50:
            return iter([{"type": "error", "message": "OCR文本为空"}])

        llm = model_manager.get_main_llm()
        model_name = model_manager.main_config.model_name

        # 分段(标题与正文对齐)
        pairs = split_paper_sections(full_text)

        def _analyze(title: str, content: str) -> dict:
            try:
                prompt = f"""你是一个专业的论文阅读助手。请用中文分析以下论文段落的内容, 包括:
1. 核心观点(1-2句话)
2. 关键方法/发现
3. 对读者的价值

论文段落标题: {title}
段落内容: {content[:1500]}

请给出简洁的分析:"""
                analysis = asyncio.run(llm.chat([{"role": "user", "content": prompt}], model_name))
                return {"title": title, "analysis": (analysis or "").strip()}
            except Exception as e:  # noqa: BLE001
                return {"title": title, "analysis": f"[分析失败: {e}]"}

        # 并行分析(独立线程, 各自 asyncio.run), 按顺序产出
        parsed_sections = []
        if len(pairs) <= 1:
            for title, content in pairs:
                parsed_sections.append(_analyze(title, content))
        else:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=settings.PAPER_ANALYSIS_CONCURRENCY) as ex:
                futures = [ex.submit(_analyze, t, c) for t, c in pairs]
                parsed_sections = [f.result() for f in futures]

        for section_data in parsed_sections:
            yield {"type": "section", **section_data}

        # 持久化到 sidecar 文件
        if parsed_sections:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(parsed_sections, f, ensure_ascii=False)
                paper.status = "parsed"
                db.commit()
            except OSError:
                pass

    def _extract_figures(self, db: Session, paper_id: int, max_figures: int = 20):
        """从 PDF 提取图片图表 + 标题(启发式), 写入 paper_figures。幂等: 已提取则跳过。"""
        try:
            paper = db.query(Paper).filter(Paper.id == paper_id).first()
            if not paper or not paper.pdf_path or not os.path.exists(paper.pdf_path):
                return
            if db.query(PaperFigure).filter(PaperFigure.paper_id == paper_id).count():
                return
            import fitz
            doc = fitz.open(paper.pdf_path)
            out_dir = os.path.join(settings.UPLOAD_DIR, "papers", "_figures", str(paper_id))
            os.makedirs(out_dir, exist_ok=True)
            added = 0
            for pno in range(len(doc)):
                if added >= max_figures:
                    break
                page = doc[pno]
                text_blocks = [(b.get("bbox"), b.get("text", ""))
                               for b in page.get_text("dict").get("blocks", [])
                               if b.get("type") == 0]
                for img_info in page.get_image_info():
                    if added >= max_figures:
                        break
                    bbox = img_info.get("bbox")
                    xref = img_info.get("xref")
                    if not bbox or not xref:
                        continue
                    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    if w < 40 or h < 40:  # 跳过装饰小图
                        continue
                    try:
                        base = doc.extract_image(xref)
                    except Exception:  # noqa: BLE001
                        continue
                    if base.get("width", 0) < 60 or base.get("height", 0) < 60:
                        continue
                    ext = (base.get("ext") or "png")
                    fname = f"fig_p{pno + 1:03d}_x{xref}.{ext}"
                    fpath = os.path.join(out_dir, fname)
                    with open(fpath, "wb") as f:
                        f.write(base["image"])
                    caption = self._figure_caption(text_blocks, bbox)
                    db.add(PaperFigure(paper_id=paper_id, page_num=pno + 1,
                                       image_path=fpath, caption=caption))
                    added += 1
            doc.close()
            db.commit()
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _figure_caption(text_blocks: list, img_bbox: tuple) -> str:
        """启发式标题: 图片下方最近且水平接近的非空文本块。"""
        candidates = [b for b in text_blocks
                      if b[0] and b[1].strip()
                      and b[0][0] >= img_bbox[0] - 60
                      and b[0][1] > img_bbox[1] - 5]
        if not candidates:
            return ""
        candidates.sort(key=lambda b: b[0][1])
        return candidates[0][1].strip()[:200]

    def delete_paper(self, db: Session, paper_id: int) -> bool:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if paper:
            if paper.pdf_path and os.path.exists(paper.pdf_path):
                os.remove(paper.pdf_path)
            # 清理派生的磁盘产物: 分析缓存 / 渲染页图 / OCR 临时图 / 图表
            for sub in ("_analysis", "_pages", "_ocr_images", "_figures"):
                d = os.path.join(settings.UPLOAD_DIR, "papers", sub, str(paper_id))
                if os.path.isdir(d):
                    shutil.rmtree(d, ignore_errors=True)
            # 清理图片尺寸缓存中该论文相关的条目(文件已删, 缓存失效)
            prefix = os.path.join(settings.UPLOAD_DIR, "papers", "_pages", str(paper_id)) + os.sep
            stale = [k for k in _IMG_SIZE_CACHE if k.startswith(prefix)]
            for k in stale:
                _IMG_SIZE_CACHE.pop(k, None)
            db.delete(paper)
            db.commit()
            return True
        return False


paper_service = PaperService()
