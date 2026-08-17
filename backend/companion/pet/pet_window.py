"""
桌宠窗口 — tkinter 实现（纯透明背景，无卡片边框）
"""
import time
import tkinter as tk

from backend.companion.pet.pet_engine import PetEngine, PetAction


class PetWindow:
    """Q版蓝猫桌宠悬浮窗: 纯透明, 始终置顶, 可拖拽"""

    # 气泡显示时长（秒）
    SPEECH_DURATION = 8

    def __init__(self, root=None):
        self._own_root = False
        if root is None:
            try:
                root = tk._default_root
            except Exception:
                pass
            if root is None:
                root = tk.Tk()
                root.withdraw()
                self._own_root = True
        self.root = root

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)

        TRANSPARENT = '#0F0F0F'
        self.win.attributes('-transparentcolor', TRANSPARENT)
        self.win.attributes('-toolwindow', True)

        self.W, self.H = 200, 200
        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        self.win.geometry(f"{self.W}x{self.H}+{screen_w - 240}+{screen_h - 80 - 280}")

        self.engine = PetEngine()
        self.PetAction = PetAction
        self._start_time = time.time()
        self.drag_data = {"x": 0, "y": 0}

        # 画布
        self.canvas = tk.Canvas(self.win, width=self.W, height=self.H,
                                highlightthickness=0, bg=TRANSPARENT)
        self.canvas.pack()

        # 右下角极小 Esc 提示
        self.canvas.create_text(self.W - 4, self.H - 4, text="╳",
                               fill='#D0D0D0', font=('Arial', 7),
                               anchor='se', tags="hint")

        # 事件
        self.canvas.bind('<Button-1>', self._on_press)
        self.canvas.bind('<B1-Motion>', self._on_drag)
        # 右键/Esc 只隐藏(可重开), 彻底退出请用桌面管理器的 [✕] 或 Ctrl+Alt+Q
        self.canvas.bind('<Button-3>', lambda e: self.hide())
        self.win.bind('<Escape>', lambda e: self.hide())

        self._animate()
        self._check_reminders()

    def _on_press(self, event):
        self.drag_data["x"] = event.x_root - self.win.winfo_x()
        self.drag_data["y"] = event.y_root - self.win.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self.drag_data["x"]
        y = event.y_root - self.drag_data["y"]
        self.win.geometry(f"+{x}+{y}")

    # ── 动态气泡 ──
    @staticmethod
    def _rounded_rect(canvas, x, y, w, h, r, **kwargs):
        """绘制圆角矩形（用 smooth polygon 模拟）"""
        points = [
            x + r, y, x + w - r, y,
            x + w, y + r, x + w, y + h - r,
            x + w - r, y + h, x + r, y + h,
            x, y + h - r, x, y + r,
        ]
        return canvas.create_polygon(points, smooth=True, **kwargs)

    def _draw_speech(self, text):
        """自适应圆角气泡（自动换行，带小尾巴）"""
        self.canvas.delete("speech")

        char_w = 12         # 微软雅黑 9pt 中文字实际宽度 ≈ 12px
        line_h = 18
        pad_h = 24          # 左右各 12px 内边距
        pad_v = 6

        max_w = self.W - 4  # 气泡几乎撑满窗口，留 2px 边距
        max_chars = max(1, (max_w - pad_h) // char_w)

        text = text[:24]    # 最多 24 字
        lines = [text[i:i + max_chars] for i in range(0, len(text), max_chars)]

        bw = min(max_w, max(len(l) for l in lines) * char_w + pad_h)
        bh = len(lines) * line_h + pad_v
        bx = (self.W - bw) // 2
        by = 3
        radius = 8                                  # 圆角半径

        # 圆角气泡主体
        PetWindow._rounded_rect(self.canvas, bx, by, bw, bh, radius,
                                fill='#FFF8EC', outline='#E8DCC8',
                                tags=("pet", "speech"))
        # 小三角尾巴
        tx, ty = self.W // 2, by + bh
        self.canvas.create_polygon(tx - 5, ty, tx + 5, ty, tx, ty + 6,
                                  fill='#FFF8EC', outline='#E8DCC8',
                                  tags=("pet", "speech"))
        # 文字逐行居中
        for i, line in enumerate(lines):
            self.canvas.create_text(self.W // 2, by + line_h // 2 + i * line_h,
                                   text=line, fill='#6A5A3A',
                                   font=('Microsoft YaHei', 9),
                                   tags=("pet", "speech"))

    def _animate(self):
        t = (time.time() - self._start_time) * 1000
        self.engine.update(t)
        self.engine.render(self.canvas, self.W, self.H)

        # 绘制说话气泡
        speech = self.engine.get_speech()
        elapsed = time.time() - self.engine._last_speech
        if speech and elapsed < PetWindow.SPEECH_DURATION:
            # 最后 2 秒半透明淡出（通过颜色模拟）
            alpha = 1.0
            if elapsed > PetWindow.SPEECH_DURATION - 2:
                alpha = (PetWindow.SPEECH_DURATION - elapsed) / 2
            self._draw_speech(speech[:30])

        self.win.after(50, self._animate)

    # ── 提醒 ──
    def _check_reminders(self):
        try:
            from backend.companion.engine import reminder_engine
            reminders = reminder_engine.check(user_id=1)
            if reminders:
                top = reminders[0]
                action_map = {
                    "weather": self.PetAction.WAVE,
                    "work_rest": self.PetAction.REMIND,
                    "knowledge": self.PetAction.THINK,
                    "task": self.PetAction.REMIND,
                }
                title = top.get("title", "")
                content = top.get("content", "")[:15]
                speech = f"{title} {content}".strip() if content else title[:30]
                self.engine.trigger(
                    action_map.get(top.get("type", ""), self.PetAction.REMIND),
                    speech
                )
                self.engine._last_speech = time.time()
        except Exception:
            pass
        self.win.after(30000, self._check_reminders)

    def show(self):
        self.win.deiconify()
        self.win.lift()

    def hide(self):
        """隐藏窗口(不销毁, 可随时重开)"""
        self.win.withdraw()

    def close(self):
        self.win.destroy()
        if self._own_root:
            self.root.destroy()
