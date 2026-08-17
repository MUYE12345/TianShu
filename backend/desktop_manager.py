"""
桌面应用管理器 — 统一管理 划屏翻译 + 桌宠 窗口生命周期

解决痛点: 窗口按 Esc/右键关闭后, 进程仍在但没有重开入口。
本管理器提供两种重开方式(均不依赖被关掉的窗口):
  1. 控制条(屏幕右上角, 始终置顶): [译] 重开划屏翻译 / [宠] 重开桌宠 / [✕] 完全退出
  2. 全局热键(需 keyboard 库, 失败自动降级仅保留控制条):
       Ctrl+Alt+T  显示/隐藏 划屏翻译
       Ctrl+Alt+P  显示/隐藏 桌宠
       Ctrl+Alt+Q  完全退出

窗口语义: Esc/右键关闭 只隐藏窗口(可随时重开); 完全退出只能通过 [✕] 或 Ctrl+Alt+Q。
"""
import tkinter as tk


class DesktopManager:
    """桌面窗口生命周期管理器"""

    def __init__(self, mode: str = "all"):
        self.mode = mode
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Tianshu Desktop")
        self._windows = {}      # name -> 窗口实例(可能已被 destroy)
        self._control = None
        self._hotkeys = []
        self._drag = {"x": 0, "y": 0}
        self._build_control()
        self._register_hotkeys()

    # ── 窗口生命周期 ──

    def _create(self, name):
        """按名称创建窗口实例(窗口被 destroy 后重开需要重建)"""
        try:
            if name == "translate":
                from backend.screen_translate.floating_window import FloatingWindow
                return FloatingWindow(self.root)
            if name == "pet":
                from backend.companion.pet.pet_window import PetWindow
                return PetWindow(self.root)
        except Exception as e:  # noqa: BLE001
            print(f"[桌面] 创建窗口 {name} 失败: {e}")
        return None

    @staticmethod
    def _alive(win):
        try:
            return win is not None and win.win.winfo_exists()
        except Exception:  # noqa: BLE001
            return False

    def show_window(self, name: str):
        """确保窗口存在并显示(已销毁则重建)"""
        win = self._windows.get(name)
        if not self._alive(win):
            win = self._create(name)
            self._windows[name] = win
            if win is None:
                return
        try:
            win.show()
        except Exception as e:  # noqa: BLE001
            print(f"[桌面] 显示窗口 {name} 失败: {e}")

    def toggle_window(self, name: str):
        """显示/隐藏切换; 已销毁则重建并显示"""
        win = self._windows.get(name)
        if self._alive(win):
            try:
                if win.win.winfo_viewable():
                    win.hide()
                else:
                    win.show()
                return
            except Exception:  # noqa: BLE001
                pass
        self.show_window(name)

    def quit(self):
        """完全退出: 关闭全部窗口 + 解绑热键 + 销毁主循环"""
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:  # noqa: BLE001
            pass
        for name, win in list(self._windows.items()):
            try:
                win.close()
            except Exception:  # noqa: BLE001
                pass
        self._windows.clear()
        try:
            if self._control is not None:
                self._control.destroy()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    # ── 控制条(始终置顶, 可拖动) ──

    def _build_control(self):
        bar = tk.Toplevel(self.root)
        bar.overrideredirect(True)
        bar.attributes('-topmost', True)
        bar.attributes('-toolwindow', True)
        sw = self.root.winfo_screenwidth()
        bar.geometry(f"150x32+{sw - 165}+40")
        frame = tk.Frame(bar, bg='#2B3A4A')
        frame.pack(fill='both', expand=True)

        def _btn(text, cmd, color='#4A7FB5'):
            tk.Button(frame, text=text, command=cmd, relief='flat', bd=0,
                      bg=color, fg='white', activebackground=color,
                      font=('Microsoft YaHei', 9, 'bold'), cursor='hand2',
                      width=3).pack(side='left', padx=2, pady=2, fill='y', expand=True)

        _btn('译', lambda: self.toggle_window('translate'))
        _btn('宠', lambda: self.toggle_window('pet'))
        _btn('✕', self.quit, '#C0392B')

        frame.bind('<Button-1>', self._on_bar_press)
        frame.bind('<B1-Motion>', self._on_bar_drag)
        self._control = bar

    def _on_bar_press(self, event):
        self._drag["x"] = event.x_root - self._control.winfo_x()
        self._drag["y"] = event.y_root - self._control.winfo_y()

    def _on_bar_drag(self, event):
        self._control.geometry(f"+{event.x_root - self._drag['x']}+{event.y_root - self._drag['y']}")

    # ── 全局热键(可选) ──

    def _register_hotkeys(self):
        try:
            import keyboard
            self._hotkeys = [
                keyboard.add_hotkey('ctrl+alt+t', lambda: self.toggle_window('translate')),
                keyboard.add_hotkey('ctrl+alt+p', lambda: self.toggle_window('pet')),
                keyboard.add_hotkey('ctrl+alt+q', self.quit),
            ]
            print("[桌面] 全局热键已启用: Ctrl+Alt+T 翻译 / Ctrl+Alt+P 桌宠 / Ctrl+Alt+Q 退出")
        except Exception as e:  # noqa: BLE001
            print(f"[桌面] 全局热键不可用(仍可用右上角控制条): {e}")
            self._hotkeys = []

    # ── 启动 ──

    def run(self):
        print("[桌面] 控制条在屏幕右上角: [译][宠] 重开窗口, [✕] 完全退出")
        self.root.mainloop()
