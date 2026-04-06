"""Matplotlib 在 Windows 下显示中文与负号。"""

from __future__ import annotations


def configure_matplotlib_fonts() -> None:
    import matplotlib

    # 优先常见中文字体，避免信息框出现 □□□
    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "Noto Sans CJK SC",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False
