"""Matplotlib：n(r), ε(r), Vf(r) 与工艺/指标文本。"""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class GrinPlotPanel(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(7, 6), layout="tight")
        super().__init__(self.fig)
        self.setParent(parent)
        try:
            self.fig.patch.set_facecolor("#fafafa")
        except Exception:
            pass
        self.ax_n = self.fig.add_subplot(2, 2, 1)
        self.ax_eps = self.fig.add_subplot(2, 2, 2)
        self.ax_vf = self.fig.add_subplot(2, 2, 3)
        self.ax_txt = self.fig.add_subplot(2, 2, 4)
        for ax in (self.ax_n, self.ax_eps, self.ax_vf):
            ax.grid(True, alpha=0.3)

    def update_curves(
        self,
        r_mm: np.ndarray,
        n_r: np.ndarray,
        eps_r: np.ndarray,
        vf_r: np.ndarray,
        a_mm: float | None,
        d_c_mm: float | None,
        angular: dict | None,
        lambda_mm: float | None,
        size_over_lambda: float | None,
        target_eff_pct: float | None,
    ):
        self.ax_n.clear()
        self.ax_eps.clear()
        self.ax_vf.clear()
        self.ax_txt.clear()
        self.ax_n.grid(True, alpha=0.3)
        self.ax_eps.grid(True, alpha=0.3)
        self.ax_vf.grid(True, alpha=0.3)

        self.ax_n.plot(r_mm, n_r, color="#1565c0")
        self.ax_n.set_xlabel("r (mm)")
        self.ax_n.set_ylabel("n(r)")

        self.ax_eps.plot(r_mm, eps_r, color="#2e7d32")
        self.ax_eps.set_xlabel("r (mm)")
        self.ax_eps.set_ylabel("ε(r)")

        self.ax_vf.plot(r_mm, vf_r, color="#c62828")
        self.ax_vf.set_xlabel("r (mm)")
        self.ax_vf.set_ylabel("Vf(r) (EMT)")
        self.ax_vf.set_ylim(0, 1.05)

        lines = []
        if lambda_mm is not None:
            lines.append(f"真空波长 λ0≈{lambda_mm:.4f} mm（c/f）")
        if size_over_lambda is not None:
            lines.append(f"尺寸/λ0（半径）≈ {size_over_lambda:.2f}")
        if a_mm is not None:
            lines.append(f"胞元尺度 a ≈ {a_mm:.4f} mm（粗估）")
        if d_c_mm is not None:
            lines.append(f"最小线径约束 d_c = {d_c_mm:.4f} mm")
        if target_eff_pct is not None:
            lines.append(f"目标效率（相对理想透镜）: {target_eff_pct:.1f} %（记录用）")
        if angular and angular.get("cv") is not None:
            lines.append(f"角向均匀性 CV(φ) ≈ {angular['cv']:.4f}（顶点方位分箱，占位）")
        if not lines:
            lines.append("生成网格后更新工艺与角向指标。")
        self.ax_txt.axis("off")
        self.ax_txt.text(
            0.02,
            0.98,
            "\n".join(lines),
            transform=self.ax_txt.transAxes,
            va="top",
            fontsize=9,
            family="sans-serif",
        )
        self.draw()
