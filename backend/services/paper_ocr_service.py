"""
论文OCR服务 — PDF转文本 + 视觉模型降级识别

降级策略:
  1. 优先用 PyMuPDF 直接提取 PDF 文本层(纯 Python, 零模型依赖)
  2. 无文本层(扫描页/图片页) → 渲染成图片 → 交给主模型视觉能力识别文字
  3. 本地 Unlimited-OCR 模型因在部分机器上加载即导致进程崩溃(访问违例/内存不足),
     已从默认链路移除。如需启用请仅在内存充足且验证通过的机器上单独接入。
"""
import os
from backend.config import settings


class PaperOCRService:
    """OCR服务"""

    def __init__(self):
        self.model = None
        self.tokenizer = None

    def process_pdf(self, pdf_path: str, paper_id: int = None) -> list:
        """处理PDF: 优先提取文本层, 扫描页渲染后并行交给主模型视觉OCR降级。

        paper_id 用于图片路径隔离(按论文分目录); 无 paper_id 则不并行、不落盘隔离。
        """
        try:
            import fitz
            doc = fitz.open(pdf_path)
        except Exception as e:
            return [{"page_num": 1, "image_path": "", "ocr_text": f"[PDF打开失败: {e}]"}]

        results = []
        scan_jobs = []  # (page_num, image_path) 待视觉OCR
        for i, page in enumerate(doc):
            try:
                text = (page.get_text() or "").strip()
            except Exception:
                text = ""
            img_path = ""
            if not text:
                # 主线程渲染(避免跨线程共享 fitz page), OCR 后面并行
                img_path = self._render_page(page, paper_id, i + 1)
                scan_jobs.append((i + 1, img_path))
            results.append({"page_num": i + 1, "image_path": img_path, "ocr_text": text})
        doc.close()

        # 扫描页视觉 OCR: 并行 + 页数上限
        if scan_jobs and paper_id is not None:
            cap = settings.PAPER_OCR_MAX_PAGES or 0
            jobs = scan_jobs[:cap] if cap and len(scan_jobs) > cap else scan_jobs

            def ocr_one(job):
                pn, img = job
                return pn, self._ocr_image_via_llm(img)

            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=settings.PAPER_OCR_CONCURRENCY) as ex:
                ocred = dict(ex.map(ocr_one, jobs))
            for r in results:
                if r["page_num"] in ocred:
                    r["ocr_text"] = ocred[r["page_num"]]
        return results

    def process_pdf_visual(self, pdf_path: str, paper_id: int, dpi: int = 144) -> list:
        """渲染每页为 PNG + 提取段落框（魔搭社区式双栏）。

        返回 [{page_num, image_path, boxes:[{x0,y0,x1,y1,text}]}]，box 坐标为渲染图像素。
        """
        import fitz
        doc = fitz.open(pdf_path)
        scale = dpi / 72.0
        results = []
        for i, page in enumerate(doc):
            img_path = self._render_page_image(page, paper_id, i + 1, dpi)
            boxes = self._extract_paragraph_boxes(page, scale)
            results.append({"page_num": i + 1, "image_path": img_path, "boxes": boxes})
        doc.close()
        return results

    def _render_page_image(self, page, paper_id: int, page_num: int, dpi: int = 144) -> str:
        """把 PDF 页渲染为 PNG（存到 data/papers/_pages/{paper_id}/）。"""
        import fitz
        out_dir = os.path.join(settings.UPLOAD_DIR, "papers", "_pages", str(paper_id))
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, f"page_{page_num:03d}.png")
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        page.get_pixmap(matrix=mat).save(out)
        return out

    @staticmethod
    def _extract_paragraph_boxes(page, scale: float) -> list:
        """用 PyMuPDF 的文本块提取段落框（像素坐标，含文本）。"""
        import fitz
        boxes = []
        try:
            data = page.get_text("dict")
        except Exception:
            return boxes
        for block in data.get("blocks", []):
            if block.get("type") != 0:  # 跳过图片块
                continue
            bbox = block.get("bbox") or (0, 0, 0, 0)
            text = ""
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text += span.get("text", "")
                text += "\n"
            text = text.strip()
            if not text:
                continue
            boxes.append({
                "x0": round(bbox[0] * scale, 1),
                "y0": round(bbox[1] * scale, 1),
                "x1": round(bbox[2] * scale, 1),
                "y1": round(bbox[3] * scale, 1),
                "text": text,
            })
        return boxes

    def _render_page(self, page, paper_id: int = None, page_num: int = 0, dpi: int = 200) -> str:
        """将 PDF 页渲染为 PNG(按 paper_id 分目录, 便于删除清理, 避免跨论文覆盖)"""
        try:
            import fitz
            sub = str(paper_id) if paper_id is not None else "_shared"
            out_dir = os.path.join(settings.UPLOAD_DIR, "papers", "_ocr_images", sub)
            os.makedirs(out_dir, exist_ok=True)
            out = os.path.join(out_dir, "page_%03d.png" % page_num)
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            page.get_pixmap(matrix=mat).save(out)
            return out
        except Exception:
            return ""

    def _ocr_image_via_llm(self, image_path: str) -> str:
        """用主模型视觉能力识别图片文字(降级方案)"""
        if not image_path or not os.path.exists(image_path):
            return "[图片OCR失败: 无图片]"
        try:
            import base64
            import asyncio
            from backend.core.model_config import model_manager
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            llm = model_manager.get_main_llm()
            model_name = model_manager.get_vision_model()  # 视觉模型（默认模型可能不支持看图）
            messages = [{"role": "user", "content": [
                {"type": "text", "text": "请识别这张图片中的全部文字并原样输出, 不要添加任何解释、注释或格式标记。"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
            ]}]
            reply = asyncio.run(llm.chat(messages, model_name))
            return (reply or "").strip() or "[图片OCR失败: 模型无输出]"
        except Exception as e:
            return f"[图片OCR失败: {e}]"


paper_ocr = PaperOCRService()
