"""论文图片解读服务 — 使用多模态LLM理解论文图表

TODO: 未来需要实现源文与译文的段落级对齐。
   - 在论文双屏显示场景中，图片解读结果应当同时与源文段落和其对应译文段落对齐展示。
   - 需要支持根据段落ID或锚点将图片分析结果映射到源文与译文的对应位置。
"""
from backend.core.model_config import model_manager


class PaperImageService:
    """论文图片解读

    Future: 支持源文与译文段落级对齐。
      每个图片解读结果应当关联到原文段落ID和对应的译文段落ID，
      以便在前端双屏显示中实现左右两侧同时高亮对齐。
    """

    def explain_figure(self, image_path: str, caption: str = "",
                       source_context: str = "", target_context: str = "") -> str:
        """
        解读论文中的图片/图表(带所在页源文/译文上下文)

        source_context: 图片所在页的英文原文(供 LLM 理解图表上下文)
        target_context: 图片所在页的中文译文(供前端双屏对齐参考)
        """
        try:
            llm = model_manager.get_main_llm()

            import base64
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()

            prompt = f"请分析这张论文图片的内容。图表标题: {caption}"
            if source_context:
                prompt += f"\n\n所在页英文原文(供上下文参考, 不要照抄):\n{source_context[:800]}"
            if target_context:
                prompt += f"\n\n所在页中文译文(供上下文参考):\n{target_context[:800]}"
            messages = [
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ]}
            ]
            import asyncio
            result = asyncio.run(llm.chat(messages, model_manager.main_config.model_name))
            return (result or "").strip()
        except Exception as e:  # noqa: BLE001
            return f"[图片解读暂不可用: {e}]"


paper_image_service = PaperImageService()
