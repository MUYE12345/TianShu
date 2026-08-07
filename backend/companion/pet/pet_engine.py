"""
桌宠引擎 — 蓝猫 Q版角色动画
渲染: tkinter Canvas 矢量绘图
"""
import random
import math
import time
from enum import Enum

try:
    import tkinter as tk
except ImportError:
    tk = None


class PetAction(Enum):
    IDLE = "idle"
    WAVE = "wave"
    THINK = "think"
    HAPPY = "happy"
    REMIND = "remind"
    SLEEP = "sleep"


class CatRenderer:
    """蓝猫绘制器 — 小清新风格"""

    # 配色
    FUR = '#E8F0FE'          # 毛色-灰蓝
    FUR_SHADOW = '#D0DCF0'   # 毛色阴影
    EAR_INNER = '#FFB5C5'    # 耳内粉色
    EYE = '#6B9FFF'           # 眼睛蓝色
    EYE_DARK = '#4A7FE0'     # 瞳孔深蓝
    EYE_WHITE = '#FFFFFF'
    NOSE = '#FF9E9E'          # 鼻子粉色
    BLUSH = '#FFD5D5'         # 腮红
    MOUTH = '#D47A7A'
    WHISKER = '#C0C8D8'      # 胡须
    BOW = '#FF8AAA'           # 蝴蝶结
    BOW_DARK = '#FF6B9A'

    @staticmethod
    def draw(canvas, action: PetAction, frame: int, width: int, height: int, time_ms: float):
        canvas.delete("pet")

        cx, cy = width // 2, height // 2 + 5   # 中心偏下一点
        r = min(width, height) // 3 + 2         # 头部大小基准

        # 呼吸浮动
        cy += math.sin(time_ms / 800) * 1.5

        # 动作偏移
        offset_x = 0
        offset_y = 0
        if action == PetAction.HAPPY:
            offset_y = -abs(math.sin(time_ms / 200) * 4)
        elif action == PetAction.WAVE:
            offset_x = math.sin(time_ms / 300) * 3 if frame % 2 == 0 else 0
        elif action == PetAction.THINK:
            offset_y = -math.sin(time_ms / 500) * 2

        tag = "pet"

        # ── 耳朵 ──
        ear_w, ear_h = int(r * 0.35), int(r * 0.55)
        for side, flip in [(-1, -1), (1, 1)]:
            ex = cx + side * int(r * 0.5)
            # 外耳
            canvas.create_polygon(
                ex - ear_w, cy - int(r * 0.5),
                ex + side * int(r * 0.15), cy - int(r * 0.5) - ear_h,
                ex + ear_w, cy - int(r * 0.5),
                fill=CatRenderer.FUR, outline=CatRenderer.FUR_SHADOW, width=1,
                smooth=True, tags=tag
            )
            # 内耳(粉色)
            canvas.create_polygon(
                ex - int(ear_w * 0.5), cy - int(r * 0.5) + 2,
                ex + side * int(r * 0.1), cy - int(r * 0.5) - int(ear_h * 0.7),
                ex + int(ear_w * 0.5), cy - int(r * 0.5) + 2,
                fill=CatRenderer.EAR_INNER, outline='', smooth=True, tags=tag
            )

        # ── 头部 ──
        head_rx, head_ry = r, int(r * 0.92)  # 扁圆，更可爱
        canvas.create_oval(cx - head_rx + offset_x, cy - head_ry + offset_y,
                         cx + head_rx + offset_x, cy + head_ry + offset_y,
                         fill=CatRenderer.FUR, outline=CatRenderer.FUR_SHADOW,
                         width=2, tags=tag)

        # ── 腮红 (先画在底层) ──
        for side in [-1, 1]:
            bx = cx + side * int(r * 0.5) + offset_x
            by = cy + int(r * 0.15) + offset_y
            canvas.create_oval(bx - int(r * 0.18), by - int(r * 0.09),
                             bx + int(r * 0.18), by + int(r * 0.09),
                             fill=CatRenderer.BLUSH, outline='', tags=tag)

        # ── 眼睛 ──
        eye_y = cy - int(r * 0.08) + offset_y
        eye_spacing = int(r * 0.32)
        blink = math.sin(time_ms / 3000) > 0.93

        for side in [-1, 1]:
            ex = cx + side * eye_spacing + offset_x
            if blink:
                # 闭眼: 一条弧线
                canvas.create_arc(ex - int(r * 0.22), eye_y - int(r * 0.05),
                                ex + int(r * 0.22), eye_y + int(r * 0.05),
                                start=0, extent=-180, style=tk.ARC,
                                outline=CatRenderer.EYE_DARK, width=2, tags=tag)
            else:
                # 眼白
                ew, eh = int(r * 0.22), int(r * 0.26)
                canvas.create_oval(ex - ew, eye_y - eh, ex + ew, eye_y + eh,
                                 fill=CatRenderer.EYE_WHITE, outline='', tags=tag)
                # 虹膜 (大眼)
                iw, ih = int(r * 0.18), int(r * 0.20)
                canvas.create_oval(ex - iw, eye_y - ih + 1, ex + iw, eye_y + ih + 1,
                                 fill=CatRenderer.EYE, outline='', tags=tag)
                # 瞳孔
                pw, ph = int(r * 0.10), int(r * 0.12)
                canvas.create_oval(ex - pw, eye_y - ph + 1, ex + pw, eye_y + ph + 1,
                                 fill=CatRenderer.EYE_DARK, outline='', tags=tag)
                # 大高光 (左上)
                hw, hh = int(r * 0.07), int(r * 0.07)
                canvas.create_oval(ex - iw + 2, eye_y - ih + 2,
                                 ex - iw + hw + 2, eye_y - ih + hh + 2,
                                 fill='#FFFFFF', outline='', tags=tag)
                # 小高光 (右下)
                canvas.create_oval(ex + iw - hw - 3, eye_y + ih - hh - 3,
                                 ex + iw - 3, eye_y + ih - 3,
                                 fill='#FFFFFF', outline='', tags=tag)

        # ── 鼻子 ──
        nx, ny = cx + offset_x, cy + int(r * 0.15) + offset_y
        ns = int(r * 0.06)
        canvas.create_polygon(
            nx, ny - ns, nx + ns, ny + int(ns * 0.5),
            nx - ns, ny + int(ns * 0.5),
            fill=CatRenderer.NOSE, outline='', smooth=False, tags=tag
        )

        # ── 嘴巴 ──
        mx, my = cx + offset_x, cy + int(r * 0.22) + offset_y
        if action == PetAction.REMIND:
            # 张嘴 (圆形)
            ms = int(r * 0.08)
            canvas.create_oval(mx - ms, my - ms, mx + ms, my + ms,
                             fill=CatRenderer.MOUTH, outline='', tags=tag)
        elif action == PetAction.SLEEP:
            # 睡觉嘴 (小弧)
            canvas.create_arc(mx - int(r * 0.06), my - 1, mx + int(r * 0.06), my + 3,
                            start=0, extent=-180, style=tk.ARC,
                            outline=CatRenderer.MOUTH, width=1, tags=tag)
        else:
            # 小猫咪嘴 (w形) 用两条线
            mw = int(r * 0.06)
            canvas.create_line(mx - mw, my, mx, my + mw, fill=CatRenderer.MOUTH, width=1.5, tags=tag)
            canvas.create_line(mx + mw, my, mx, my + mw, fill=CatRenderer.MOUTH, width=1.5, tags=tag)

        # ── 胡须 ──
        whisker_len = int(r * 0.45)
        for side in [-1, 1]:
            wx = cx + side * int(r * 0.4) + offset_x
            wy = cy + int(r * 0.1) + offset_y
            canvas.create_line(wx, wy, wx + side * whisker_len, wy - int(r * 0.08),
                             fill=CatRenderer.WHISKER, width=1, tags=tag)
            canvas.create_line(wx, wy + int(r * 0.05), wx + side * whisker_len, wy + int(r * 0.05),
                             fill=CatRenderer.WHISKER, width=1, tags=tag)
            canvas.create_line(wx, wy + int(r * 0.10), wx + side * whisker_len, wy + int(r * 0.18),
                             fill=CatRenderer.WHISKER, width=1, tags=tag)

        # ── 蝴蝶结 (右侧耳朵下方) ──
        bow_x = cx + int(r * 0.5) + offset_x
        bow_y = cy - int(r * 0.4) + offset_y
        # 左环
        canvas.create_polygon(bow_x, bow_y, bow_x - int(r * 0.18), bow_y - int(r * 0.08),
                            bow_x - int(r * 0.18), bow_y + int(r * 0.08),
                            fill=CatRenderer.BOW, outline='', smooth=True, tags=tag)
        # 右环
        canvas.create_polygon(bow_x, bow_y, bow_x + int(r * 0.18), bow_y - int(r * 0.08),
                            bow_x + int(r * 0.18), bow_y + int(r * 0.08),
                            fill=CatRenderer.BOW, outline='', smooth=True, tags=tag)
        # 中心结
        knot_s = int(r * 0.04)
        canvas.create_oval(bow_x - knot_s, bow_y - knot_s, bow_x + knot_s, bow_y + knot_s,
                         fill=CatRenderer.BOW_DARK, outline='', tags=tag)
        # 飘带
        canvas.create_line(bow_x, bow_y + knot_s, bow_x - int(r * 0.06), bow_y + int(r * 0.18),
                         fill=CatRenderer.BOW, width=1.5, tags=tag)
        canvas.create_line(bow_x, bow_y + knot_s, bow_x + int(r * 0.06), bow_y + int(r * 0.20),
                         fill=CatRenderer.BOW, width=1.5, tags=tag)

        # ── 思考气泡 ──
        if action == PetAction.THINK:
            bx = cx + r + 5 + offset_x
            by = cy - r - 5 + offset_y
            canvas.create_rectangle(bx, by, bx + 35, by + 22,
                                   fill='#FFFFFF', outline='#C8C8C8', tags=tag)
            canvas.create_oval(bx - 8, by + 18, bx, by + 26,
                             fill='#FFFFFF', outline='#C8C8C8', tags=tag)
            canvas.create_oval(bx - 12, by + 15, bx - 6, by + 21,
                             fill='#FFFFFF', outline='#C8C8C8', tags=tag)
            canvas.create_text(bx + 17, by + 11, text="?", fill='#8A8A8A', tags=tag)

        # ── 睡觉 Zzz ──
        if action == PetAction.SLEEP:
            zx, zy = cx + int(r * 0.5) + offset_x, cy - int(r * 0.5) + offset_y
            sizes = [8, 11, 14]
            for i, s in enumerate(sizes):
                canvas.create_text(zx + i * 8, zy - i * 10, text="z" if i < 2 else "Z",
                                 fill='#B0B8C8', font=('Arial', s), tags=tag)


class PetEngine:
    """桌宠动作状态机"""

    def __init__(self):
        self.current_action = PetAction.IDLE
        self.speech_text = ""
        self._frame = 0
        self._time_ms = 0
        self._last_speech = 0

    def trigger(self, action: PetAction, speech: str = ""):
        self.current_action = action
        self.speech_text = speech
        self._last_speech = time.time()

    def idle_behavior(self):
        if random.random() < 0.2:
            self.current_action = random.choice([PetAction.WAVE, PetAction.THINK, PetAction.HAPPY])
        else:
            self.current_action = PetAction.IDLE

    def update(self, time_ms: float):
        self._time_ms = time_ms
        self._frame = int(time_ms / 500) % 10

    def render(self, canvas, width: int, height: int):
        CatRenderer.draw(canvas, self.current_action, self._frame, width, height, self._time_ms)

    def get_speech(self) -> str:
        return self.speech_text
