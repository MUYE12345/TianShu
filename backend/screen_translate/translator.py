"""翻译引擎 — 调用主体模型进行翻译"""
from backend.core.model_config import model_manager


class Translator:
    """翻译引擎"""

    def translate_image(self, image_path: str, target_lang: str = "中文") -> list:
        """直接读取截图图片, 用多模态模型一次完成识别+逐行翻译(跳过本地OCR).

        本地 Unlimited-OCR 模型在本机加载即崩溃进程, 因此优先走此路径:
        图片 → 支持图片输入的主模型 → 识别原文 + 逐行翻译。

        返回: [{"source": "原文", "translated": "译文"}]  (无 bbox 坐标)
        """
        import base64
        import asyncio
        try:
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
        except Exception as e:
            return [{"source": "", "translated": f"[图片读取失败: {e}]"}]

        llm = model_manager.get_main_llm()
        # 图片翻译必须用支持视觉的模型（默认模型可能是纯文本的 deepseek 等）
        model_name = model_manager.get_vision_model()
        prompt = (f"请识别这张截图中的全部文字, 并逐行翻译为{target_lang}。\n"
                  "严格按以下格式输出, 每行一条, 不要添加任何解释或编号:\n"
                  "[原文] => [译文]")
        messages = [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
        ]}]

        try:
            reply = asyncio.run(llm.chat(messages, model_name))
        except Exception as e:
            return [{"source": "", "translated": f"[翻译失败: {e}]"}]

        lines = []
        for raw in (reply or "").split("\n"):
            line = raw.strip()
            if not line:
                continue
            if "=>" in line:
                src, tgt = line.split("=>", 1)
                src = src.strip().strip("[]").strip()
                tgt = tgt.strip().strip("[]").strip()
                lines.append({"source": src, "translated": tgt})
            else:
                lines.append({"source": "", "translated": line})
        return lines

    def translate(self, text_lines: list, target_lang: str = "中文") -> list:
        """
        逐行翻译

        参数:
            text_lines: [{"text": "Hello", "bbox": {}}]
            target_lang: 目标语言

        返回:
            [{"source": "Hello", "translated": "你好", "bbox": {}}]
        """
        texts = [t.get("text", "") for t in text_lines if t.get("text")]
        if not texts:
            return []

        try:
            llm = model_manager.get_main_llm()
            text = "\n".join(texts)
            result = llm.invoke(
                f"将以下文本逐行翻译为{target_lang}, 保持每行对应:\n{text}"
            )
            # DirectLLM.invoke() 直接返回字符串
            translated_lines = result.strip().split("\n")

            output = []
            for i, t in enumerate(text_lines):
                src = t.get("text", "")
                trans = translated_lines[i] if i < len(translated_lines) else ""
                output.append({"source": src, "translated": trans, "bbox": t.get("bbox", {})})
            return output
        except Exception as e:
            return [{"source": t["text"], "translated": f"[翻译失败: {e}]", "bbox": t.get("bbox", {})}
                    for t in text_lines]
