"""
翻译结果窗口 — tkinter 双栏显示(原文 | 翻译)
"""
import tkinter as tk
from tkinter import scrolledtext


class TranslateWindow:
    """双栏翻译结果窗口"""

    def __init__(self, source_lines: list, translated_lines: list, root=None):
        if root is None:
            try:
                root = tk._default_root
            except Exception:
                pass
            if root is None:
                self._own_root = tk.Tk()
                self._own_root.withdraw()
                root = self._own_root
        else:
            self._own_root = None
        self.root = root

        self.win = tk.Toplevel(root)
        self.win.title("划屏翻译")
        self.win.attributes('-topmost', True)
        self.win.geometry("800x500+300+200")
        self.win.minsize(500, 300)

        # 原文内容
        if source_lines and isinstance(source_lines[0], dict):
            src_content = "\n\n".join([s.get("text", "") for s in source_lines])
        else:
            src_content = "\n".join(source_lines) if source_lines else ""

        # 译文内容（Translator 返回的 key 是 "translated"）
        if translated_lines and isinstance(translated_lines[0], dict):
            tgt_content = "\n\n".join([t.get("translated", "") for t in translated_lines])
        elif isinstance(translated_lines, list):
            tgt_content = "\n".join(translated_lines)
        else:
            tgt_content = str(translated_lines) if translated_lines else ""

        # ── 整体布局 ──
        main_frame = tk.Frame(self.win)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        # 双栏等宽 grid 布局
        main_frame.grid_columnconfigure(0, weight=1, uniform='col')
        main_frame.grid_columnconfigure(1, weight=1, uniform='col')
        main_frame.grid_rowconfigure(0, weight=1)

        # ── 左侧：原文 ──
        left_frame = tk.Frame(main_frame)
        left_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))

        tk.Label(left_frame, text="📖 原文", font=('Microsoft YaHei', 11, 'bold'),
                fg='#4A7FB5').pack(anchor='w', pady=(0, 4))

        src_text = scrolledtext.ScrolledText(left_frame, wrap='word',
                                             font=('Microsoft YaHei', 10),
                                             width=1, height=1)  # width/height 由 grid 控制
        src_text.pack(fill='both', expand=True)
        src_text.insert('1.0', src_content)
        src_text.config(state='disabled')

        # ── 右侧：翻译 ──
        right_frame = tk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 0))

        tk.Label(right_frame, text="🌐 翻译", font=('Microsoft YaHei', 11, 'bold'),
                fg='#6AAF5C').pack(anchor='w', pady=(0, 4))

        tgt_text = scrolledtext.ScrolledText(right_frame, wrap='word',
                                             font=('Microsoft YaHei', 10),
                                             width=1, height=1)
        tgt_text.pack(fill='both', expand=True)
        tgt_text.insert('1.0', tgt_content)
        tgt_text.config(state='disabled')

        # ── 底部按钮 ──
        btn_frame = tk.Frame(self.win)
        btn_frame.pack(fill='x', padx=10, pady=(0, 10))

        tk.Button(btn_frame, text="关闭 (Esc)", command=self.close,
                 bg='#F0F0F0', relief='flat', padx=24, pady=4,
                 font=('Microsoft YaHei', 9)).pack(side='right')

        self.win.bind('<Escape>', lambda e: self.close())
        self.win.protocol("WM_DELETE_WINDOW", self.close)

    def show(self):
        self.win.deiconify()
        self.win.lift()

    def close(self):
        self.win.destroy()
        if self._own_root:
            self._own_root.destroy()
