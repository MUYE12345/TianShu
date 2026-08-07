"""
截屏模块 — 全屏截图 → 显示图片 → 在图片上划选（彻底避免坐标问题）
"""
import os
import tempfile
import tkinter as tk
from PIL import Image, ImageGrab, ImageTk


class ScreenshotCapture:
    """截屏: 先截全屏图片, 再在图片上划选, 裁剪返回"""

    def __init__(self, callback, root=None):
        self.callback = callback
        self.rect_id = None
        self.sx1 = self.sy1 = None
        self.cvx1 = self.cvy1 = None

        if root is None:
            try:
                root = tk._default_root
            except Exception:
                pass
            if root is None:
                root = tk.Tk()
                root.withdraw()

        # 1. 截全屏
        self.full_img = ImageGrab.grab()
        img_w, img_h = self.full_img.size

        # 2. 窗口覆盖全屏
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        # 如果图片比屏幕大就缩放（通常 scale = 1.0）
        self.scale = min(sw / img_w, sh / img_h, 1.0)
        disp_w = int(img_w * self.scale)
        disp_h = int(img_h * self.scale)

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        self.win.geometry(f"{disp_w}x{disp_h}+0+0")

        # 3. 在 canvas 上显示全屏截图
        self.canvas = tk.Canvas(self.win, width=disp_w, height=disp_h,
                                highlightthickness=0, cursor='crosshair')
        self.canvas.pack()

        # ★ 必须保存为实例属性防止垃圾回收
        if self.scale < 1.0:
            resized = self.full_img.resize((disp_w, disp_h), Image.BICUBIC)
        else:
            resized = self.full_img
        self._bg_image = ImageTk.PhotoImage(resized)
        self.canvas.create_image(0, 0, anchor='nw', image=self._bg_image)

        # 提示
        self._hint = self.canvas.create_text(
            disp_w // 2, 20,
            text="拖拽鼠标选择截图区域 ｜ Esc 取消",
            fill='#FFFFFF', font=('Microsoft YaHei', 12)
        )

        # 事件
        self.canvas.bind('<ButtonPress-1>', self._on_press)
        self.canvas.bind('<B1-Motion>', self._on_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)
        self.win.bind('<Escape>', lambda e: self._cancel())
        self.win.focus_force()

    def show(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def _cv_to_img(self, cx, cy):
        """canvas 坐标 → 原始全屏图坐标"""
        return int(cx / self.scale), int(cy / self.scale)

    def _on_press(self, event):
        self.canvas.delete(self._hint)
        self.cvx1, self.cvy1 = event.x, event.y
        self.sx1, self.sy1 = self._cv_to_img(event.x, event.y)
        self.rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline='#FF4444', width=3
        )

    def _on_drag(self, event):
        if self.rect_id:
            self.canvas.coords(self.rect_id, self.cvx1, self.cvy1, event.x, event.y)

    def _on_release(self, event):
        # 原始图坐标
        ex, ey = self._cv_to_img(event.x, event.y)
        x1, y1 = min(self.sx1, ex), min(self.sy1, ey)
        x2, y2 = max(self.sx1, ex), max(self.sy1, ey)

        if x2 - x1 < 10 or y2 - y1 < 10:
            self._cancel()
            return

        self.win.withdraw()
        self.win.update_idletasks()

        try:
            # 从全屏原图裁剪
            im = self.full_img.crop((x1, y1, x2, y2))
            debug_path = os.path.join(os.path.expanduser("~"), "Desktop", "ocr_capture.png")
            im.save(debug_path, 'PNG')
            print(f"[截图] 已保存到: {debug_path}", flush=True)

            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            im.save(tmp.name, 'PNG')
            tmp.close()
            self.callback(tmp.name)
        except Exception as e:
            print(f"[截图] 错误: {e}")
            self.callback(None)
        finally:
            try:
                self.win.destroy()
            except Exception:
                pass

    def _cancel(self):
        try:
            self.win.destroy()
        except Exception:
            pass
        self.callback(None)
