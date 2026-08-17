"""
桌面应用启动器 — tkinter 版（轻量，无需 PyQt5）

用法:
  python run_desktop.py              # 同时启动划屏翻译 + 桌宠
  python run_desktop.py translate    # 仅启动划屏翻译
  python run_desktop.py pet          # 仅启动桌宠
  python run_desktop.py --help       # 帮助

关闭与重开:
  - Esc / 右键关闭 = 仅隐藏窗口, 可从右上角控制条 [译][宠] 或全局热键重开
  - 控制条 [✕] 或 Ctrl+Alt+Q = 完全退出
  - 全局热键: Ctrl+Alt+T 划屏翻译 / Ctrl+Alt+P 桌宠 / Ctrl+Alt+Q 退出
"""
import sys
import os

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    show_help = "-h" in sys.argv or "--help" in sys.argv

    if show_help:
        print(__doc__)
        return

    mode = args[0] if args else "all"
    if mode not in ("all", "translate", "pet"):
        print(f"未知模式: {mode}")
        print(__doc__)
        return

    from backend.desktop_manager import DesktopManager

    mgr = DesktopManager(mode)

    if mode in ("all", "translate"):
        mgr.show_window("translate")
        print("[桌面] 划屏翻译已启动")

    if mode in ("all", "pet"):
        mgr.show_window("pet")
        print("[桌面] Q版桌宠已启动(含提醒)")

    mgr.run()


if __name__ == "__main__":
    main()
