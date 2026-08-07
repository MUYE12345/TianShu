"""
桌面悬浮窗 — tkinter 玻璃花瓣质感
截图使用 tkinter + PIL（无需 PyQt5）
"""
import tkinter as tk


class FloatingWindow:
    """悬浮窗: 始终置顶, 可拖拽, 双击触发截屏"""

    def __init__(self, root=None):
        self.root = root
        if self.root is None:
            try:
                self.root = tk._default_root
            except Exception:
                pass
            if self.root is None:
                self._own_root = tk.Tk()
                self._own_root.withdraw()
                self.root = self._own_root
        else:
            self._own_root = None

        self.win = tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        TRANSPARENT = '#0F0F0F'
        self.win.attributes('-transparentcolor', TRANSPARENT)
        self.win.attributes('-toolwindow', True)

        SIZE = 50
        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        self.win.geometry(f"{SIZE}x{SIZE}+{screen_w - 80}+{screen_h - 80 - 160}")

        self.canvas = tk.Canvas(self.win, width=SIZE, height=SIZE,
                                highlightthickness=0, bg=TRANSPARENT)
        self.canvas.pack()

        c = SIZE // 2

        # 外圈光晕
        self.canvas.create_oval(c - 24, c - 24, c + 24, c + 24,
                                fill='#F0F6FF', outline='')
        # 主层
        self.canvas.create_oval(c - 22, c - 22, c + 22, c + 22,
                                fill='#D8ECFF', outline='#FFFFFF', width=1.5)
        # 内层
        self.canvas.create_oval(c - 18, c - 18, c + 18, c + 18,
                                fill='#C8E4FF', outline='')
        # 花瓣高光
        self.canvas.create_oval(c - 14, c - 12, c - 2, c,
                                fill='#FFFFFF', stipple='gray25', outline='')
        # 底部微光
        self.canvas.create_oval(c + 2, c + 6, c + 12, c + 14,
                                fill='#A8D0F0', stipple='gray25', outline='')
        # 文字
        self.canvas.create_text(c, c + 1, text="译",
                               fill='#4A7FB5',
                               font=('Microsoft YaHei', 12, 'bold'))

        # 拖拽
        self.drag_data = {"x": 0, "y": 0}
        self.canvas.bind('<Button-1>', self._on_press)
        self.canvas.bind('<B1-Motion>', self._on_drag)
        self.canvas.bind('<Double-Button-1>', self._on_double_click)
        self.canvas.bind('<Button-3>', self._show_menu)
        self.win.bind('<Escape>', lambda e: self.close())

        self.trans_win = None

    def show(self):
        self.win.deiconify()
        self.win.lift()

    def close(self):
        self.win.destroy()
        if self._own_root:
            self._own_root.destroy()

    def hide(self):
        self.win.withdraw()

    def _on_press(self, event):
        self.drag_data["x"] = event.x_root - self.win.winfo_x()
        self.drag_data["y"] = event.y_root - self.win.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self.drag_data["x"]
        y = event.y_root - self.drag_data["y"]
        self.win.geometry(f"+{x}+{y}")

    def _show_menu(self, event):
        menu = tk.Menu(self.win, tearoff=0)
        menu.add_command(label="翻译", command=self._start_translate)
        menu.add_command(label="退出", command=self.close)
        menu.tk_popup(event.x_root, event.y_root)

    def _on_double_click(self, event):
        self._start_translate()

    def _start_translate(self):
        """启动截图"""
        self.hide()
        self.win.update_idletasks()

        try:
            from backend.screen_translate.screenshot import ScreenshotCapture
            sc = ScreenshotCapture(self._on_captured, root=self.root)
            sc.show()
        except Exception as e:
            print(f"[划屏翻译] 启动截图失败: {e}")
            self.show()

    def _on_captured(self, image_path: str):
        """截屏完成回调——OCR + 翻译"""
        if not image_path:
            self.show()
            return

        # ── 加载提示 ──
        loading = tk.Toplevel(self.root)
        loading.overrideredirect(True)
        loading.attributes('-topmost', True)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        loading.geometry(f"200x50+{sw//2-100}+{sh//2-25}")
        canvas = tk.Canvas(loading, width=200, height=50, highlightthickness=0, bg='#F0F6FF')
        canvas.pack()
        canvas.create_text(100, 25, text="⏳ 翻译处理中...", fill='#4A7FB5',
                          font=('Microsoft YaHei', 11))
        loading.update()

        try:
            from backend.screen_translate.translator import Translator
            from backend.screen_translate.translate_window import TranslateWindow

            translator = Translator()

            # ── 直接读图翻译: 本地 Unlimited-OCR 模型在本机加载即崩进程, 跳过 OCR ──
            canvas.create_text(100, 42, text="AI 识别翻译...", fill='#8AB5D5',
                              font=('Microsoft YaHei', 8))
            loading.update()

            direct = translator.translate_image(image_path)
            print(f"[翻译] 直接读图翻译 {len(direct)} 行", flush=True)

            if not direct:
                raise Exception("图片翻译未返回结果")
            if any(d.get("translated", "").startswith(("[翻译失败", "[图片读取失败")) for d in direct):
                raise Exception(direct[0].get("translated", "翻译失败"))

            source_lines = [{"text": d.get("source", "")} for d in direct]
            translated = [{"source": d.get("source", ""), "translated": d.get("translated", ""),
                           "bbox": {}} for d in direct]
            print(f"[翻译] 翻译完成 {len(translated)} 行", flush=True)
            self.trans_win = TranslateWindow(source_lines, translated, root=self.root)
            self.trans_win.show()
        except ImportError as e:
            print(f"[划屏翻译] 模块未就绪: {e}")
        except Exception as e:
            print(f"[划屏翻译] 错误: {e}")
        finally:
            try:
                loading.destroy()
            except Exception:
                pass
            self.show()
